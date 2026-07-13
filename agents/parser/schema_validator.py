# ---------------------------------------------------------------------------
# Deterministic schema validation -- the fix for "hi" getting saved.
# Runs on every parsed rule regardless of what the LLM claims about it.
# ---------------------------------------------------------------------------
 
import re


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