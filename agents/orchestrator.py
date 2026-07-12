"""
Multi-agent orchestration layer.
 
Three narrowly-scoped agents, each with one job, coordinated by an
Orchestrator:
 
  ConditionParserAgent  -- plain English -> structured Rule JSON
  ValidationAgent        -- checks a new rule against the trader's other
                            active rules for conflicts/duplicates (semantic,
                            soft check -- the trader can override this one)
  ExplanationAgent        -- turns a deterministic TriggerEvent's matched
                            values into a plain-language reason
 
Critically, none of these are trusted blindly. validate_rule_schema() below
is a plain, deterministic function that runs on every parsed rule regardless
of what the LLM returned -- it's what actually stops something like "hi"
(or a hallucinated field) from ever reaching the database. The LLM proposes;
this function, and later yahoo_feed.verify_ticker(), dispose.
"""

import logging
import os
import re
from dotenv import load_dotenv
from google import genai
import json
import streamlit as st
from dataclasses import dataclass, field
from backend.rule_engine.conflict_checker import check_deterministic_conflicts

load_dotenv()

class AgentError(Exception):
    """Raised when an LLM agent call fails or returns output we can't use."""

api_key = st.secrets.get("GEMINI_API_KEY", os.getenv("GEMINI_API_KEY"))
client = genai.Client(api_key=api_key)
logger = logging.getLogger(__name__)

MODEL = st.secrets.get("GEMINI_MODEL", os.getenv("GEMINI_MODEL"))

def _call_llm(system: str, user: str) -> str:
    response = client.models.generate_content(
        model=MODEL,
        contents=f"""
System:
{system}

User:
{user}
"""
    )

    return response.text

def _parse_json_response(raw: str) -> dict:
    """LLMs occasionally wrap JSON in markdown fences despite instructions
    not to -- strip those defensively, then fail loudly (not silently) on
    genuinely unparseable output."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        logger.warning("Model returned non-JSON output: %r", raw[:200])
        raise AgentError("Model did not return valid JSON -- try rephrasing the condition.") from exc
 
 
# ---------------------------------------------------------------------------
# Deterministic schema validation -- the fix for "hi" getting saved.
# Runs on every parsed rule regardless of what the LLM claims about it.
# ---------------------------------------------------------------------------
 
VALID_CONDITION_TYPES = {"entry_buy", "entry_sell", "stop_loss", "target"}
VALID_COMPARATORS = {">", "<", ">=", "<=", "between"}
VALID_INDICATORS = {"EMA", "RSI"}
TICKER_PATTERN = re.compile(r"^[A-Z0-9]{1,10}(\.[A-Z]{1,5})?$")
 
 
def validate_rule_schema(rule: dict) -> list[str]:
    """Returns a list of problems; an empty list means the rule is
    structurally usable (not that it's a *good* trade, and not that the
    ticker actually exists -- see yahoo_feed.verify_ticker for that)."""
    problems: list[str] = []
 
    if not isinstance(rule, dict):
        return ["Model response wasn't a JSON object."]
 
    instrument = rule.get("instrument")
    if not instrument or not isinstance(instrument, str):
        problems.append("No instrument/ticker was extracted -- this input may not describe a trade condition at all.")
    elif not TICKER_PATTERN.match(instrument.upper()):
        problems.append(f"'{instrument}' doesn't look like a valid ticker symbol.")
 
    if rule.get("condition_type") not in VALID_CONDITION_TYPES:
        problems.append(f"Unrecognized or missing condition type: {rule.get('condition_type')!r}")
 
    conditions = rule.get("conditions")
    if not conditions or not isinstance(conditions, list):
        problems.append("No conditions were extracted -- there's nothing here to evaluate against the market.")
    else:
        for i, cond in enumerate(conditions, start=1):
            if not isinstance(cond, dict):
                problems.append(f"Condition {i}: not a valid object.")
                continue
            comparator = cond.get("comparator")
            value = cond.get("value")
            if comparator not in VALID_COMPARATORS:
                problems.append(f"Condition {i}: invalid comparator {comparator!r}")
                continue
            if comparator == "between":
                if not (isinstance(value, (list, tuple)) and len(value) == 2
                        and all(isinstance(v, (int, float)) for v in value)):
                    problems.append(f"Condition {i}: 'between' requires two numbers [low, high].")
            elif not isinstance(value, (int, float)):
                problems.append(f"Condition {i}: value must be a number, got {value!r}")
 
            if cond.get("type") == "indicator" and cond.get("indicator_name") not in VALID_INDICATORS:
                problems.append(f"Condition {i}: unsupported indicator {cond.get('indicator_name')!r}")
 
    if rule.get("clarification_needed"):
        problems.append(f"Model flagged ambiguity: {rule['clarification_needed']}")
 
    return problems
 
 
# ---------------------------------------------------------------------------
# 1. Condition Parser Agent
# ---------------------------------------------------------------------------
 
PARSER_SYSTEM_PROMPT = """You convert a trader's plain-English intraday trade condition into strict JSON matching this schema. Return ONLY JSON -- no prose, no markdown fences, no explanation.
 
{
  "instrument": string | null,
  "condition_type": "entry_buy" | "entry_sell" | "stop_loss" | "target" | null,
  "logic_operator": "AND" | "OR",
  "conditions": [
    {
      "type": "price" | "indicator",
      "comparator": ">" | "<" | "between",
      "value": number | [low, high],
      "indicator_name": "EMA" | "RSI" | null,
      "indicator_period": number | null
    }
  ],
  "clarification_needed": string | null
}
 
Rules:
- If the input does NOT describe a trade condition at all (greetings, random text, unrelated questions), return instrument: null, condition_type: null, conditions: [], and set clarification_needed to a short note that this isn't a trade condition. Do not invent a plausible-looking rule for non-trading input.
- Every condition needs a concrete numeric threshold the trader actually implied. Never invent a number.
- If the trader gives a stop loss or target as a bare price (e.g. "SL at 2900"), use type "price" with the appropriate comparator (stop_loss defaults to "<", target defaults to ">").
- If you're unsure about the ticker or any required field, still return your best-effort JSON but set clarification_needed to a specific question.
"""
 
 
class ConditionParserAgent:
    """Turns plain English into a structured rule the deterministic engine can evaluate."""
 
    def parse(self, raw_text: str) -> dict:
        if not raw_text or not raw_text.strip():
            raise AgentError("Empty input -- nothing to parse.")
        raw = _call_llm(PARSER_SYSTEM_PROMPT, raw_text)
        return _parse_json_response(raw)
 
 
# ---------------------------------------------------------------------------
# 2. Validation Agent (semantic -- see validate_rule_schema above for the
#    deterministic structural check that runs first)
# ---------------------------------------------------------------------------
 
VALIDATOR_SYSTEM_PROMPT = """You review one newly parsed trade rule against the trader's other currently active rules for the same trading day. You are a sanity check, not a trading advisor -- flag structural/logical problems only:
 
- Duplicate rules (same instrument, same condition_type, same or near-identical thresholds)
- Contradictions (e.g. two entry_buy rules on the same instrument with overlapping/conflicting price conditions)
- A stop_loss whose comparator or value puts it on the wrong side of a linked entry price
 
Return ONLY JSON: {"approved": bool, "issues": [string, ...]}"""
 
 
class ValidationAgent:
    """Sanity-checks a new rule against the existing active rule set. Soft
    check -- the trader can see the flagged issue and choose to save anyway."""
 
    def validate(self, new_rule: dict, existing_rules: list) -> dict:
        payload = json.dumps({"new_rule": new_rule, "existing_active_rules": existing_rules})
        raw = _call_llm(VALIDATOR_SYSTEM_PROMPT, payload)
        result = _parse_json_response(raw)
        if not isinstance(result, dict) or "approved" not in result:
            raise AgentError("Validation agent returned an unexpected shape.")
        return result
 
 
# ---------------------------------------------------------------------------
# 3. Explanation Agent
# ---------------------------------------------------------------------------
 
EXPLAINER_SYSTEM_PROMPT = """You write ONE short, plain-language sentence explaining why a trade condition just fired, using ONLY the values provided to you. Never invent a number. Be concrete: name the instrument, the condition type, and the specific values that matched. Return plain text, no preamble."""
 
 
class ExplanationAgent:
    """Turns a deterministic trigger event's matched values into a human-
    readable reason. Narrates a fact the rule engine already established --
    it cannot decide whether a rule fired, only describe why."""
 
    def explain(self, instrument: str, condition_type: str, matched_values: dict) -> str:
        payload = (
            f"Instrument: {instrument}\n"
            f"Condition type: {condition_type}\n"
            f"Matched values: {json.dumps(matched_values)}"
        )
        try:
            return _call_llm(EXPLAINER_SYSTEM_PROMPT, payload).strip()
        except AgentError as exc:
            # The trigger already happened deterministically -- a failed
            # narration step shouldn't cause the alert itself to be lost.
            logger.error("Explanation agent failed: %s", exc)
            return (f"{instrument}: {condition_type} condition matched "
                    f"{matched_values} (explanation unavailable: {exc})")
 
 
# ---------------------------------------------------------------------------
# 4. News Sentiment Agent
# ---------------------------------------------------------------------------
 
NEWS_SENTIMENT_SYSTEM_PROMPT = """You are a financial news sentiment classifier. Given recent headlines for one stock, classify the OVERALL sentiment based ONLY on those headlines -- do not speculate beyond what's given, and do not predict price direction. Return ONLY JSON:
 
{"sentiment": "strongly_negative" | "negative" | "neutral" | "positive" | "strongly_positive", "summary": string}
 
"summary" is one short sentence naming what's driving the sentiment."""
 
 
class NewsSentimentAgent:
    """Classifies recent news sentiment for an instrument. Runs only at
    trigger time (not on every poll) -- this is a cold-path enrichment
    step, same as ExplanationAgent, not part of the deterministic hot path."""
 
    def analyze(self, instrument: str, headlines: list[str]) -> dict:
        if not headlines:
            return {"sentiment": "neutral", "summary": "No recent news found."}
        payload = f"Instrument: {instrument}\nHeadlines:\n" + "\n".join(f"- {h}" for h in headlines)
        try:
            raw = _call_llm(NEWS_SENTIMENT_SYSTEM_PROMPT, payload)
            result = _parse_json_response(raw)
            if "sentiment" not in result:
                raise AgentError("News sentiment agent returned an unexpected shape.")
            return result
        except AgentError as exc:
            logger.error("News sentiment agent failed: %s", exc)
            return {"sentiment": "unknown", "summary": f"Sentiment check unavailable: {exc}"}
 
 
def sentiment_contradicts_direction(condition_type: str, sentiment: str) -> bool:
    """A buy/long signal firing into negative news, or a sell/short signal
    firing into positive news, is worth flagging -- not blocking, the
    trader decides, but they should see it before acting."""
    if condition_type == "entry_buy":
        return sentiment in {"negative", "strongly_negative"}
    if condition_type == "entry_sell":
        return sentiment in {"positive", "strongly_positive"}
    return False
 
 
# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------
 
@dataclass
class OrchestrationResult:
    rule: dict
    schema_problems: list = field(default_factory=list)
    conflicts: list = field(default_factory=list)   # deterministic, provable -- hard block
    approved: bool = False
    issues: list = field(default_factory=list)       # LLM semantic -- soft warning, can override
 
    @property
    def is_valid(self) -> bool:
        """Structurally valid AND free of provable conflicts = safe to
        construct a Rule from. Does NOT mean the ticker exists on Yahoo --
        check that separately before saving."""
        return not self.schema_problems and not self.conflicts
 
 
class Orchestrator:
    """Coordinates the pre-market agent pipeline: parse -> structural
    validation -> deterministic conflict check -> semantic validation. The
    trader still confirms before anything is saved (see app.py)."""
 
    def __init__(self):
        self.parser = ConditionParserAgent()
        self.validator = ValidationAgent()
        self.explainer = ExplanationAgent()
        self.news_agent = NewsSentimentAgent()
 
    def process_new_condition(self, raw_text: str, existing_rules: list) -> OrchestrationResult:
        parsed = self.parser.parse(raw_text)
        schema_problems = validate_rule_schema(parsed)
        if schema_problems:
            return OrchestrationResult(rule=parsed, schema_problems=schema_problems)
 
        # Provable contradictions (RSI>70 AND RSI<40, SL on the wrong side
        # of entry) are caught deterministically before spending an LLM
        # call on the fuzzier semantic check.
        conflicts = check_deterministic_conflicts(parsed, existing_rules)
        if conflicts:
            return OrchestrationResult(rule=parsed, conflicts=conflicts)
 
        validation = self.validator.validate(parsed, existing_rules)
        return OrchestrationResult(
            rule=parsed,
            approved=validation.get("approved", False),
            issues=validation.get("issues", []),
        )
 
 
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    orchestrator = Orchestrator()
    for sample in ["hi", "Buy AAPL if price breaks above 210 and RSI is between 40 and 70, SL at 205"]:
        try:
            result = orchestrator.process_new_condition(sample, existing_rules=[])
            print(f"\ninput: {sample!r}")
            print("valid:", result.is_valid, "problems:", result.schema_problems)
        except AgentError as exc:
            print(f"\ninput: {sample!r} -> AgentError: {exc}")