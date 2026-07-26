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
from dataclasses import dataclass, field
from agents.exceptions.agent_exception import AgentError
from agents.explainer.explainer_agent import ExplanationAgent
from agents.parser.parser_agent import ConditionParserAgent
from agents.parser.schema_validator import validate_rule_schema
from agents.validator.validator_agent import ValidationAgent
from backend.rule_engine.conflict_checker import check_deterministic_conflicts

 
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