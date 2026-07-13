import json
from agents.exceptions.agent_exception import AgentError
from agents.llm.llm_utils import _call_llm, _parse_json_response
from prompts.validator_prompt import VALIDATOR_SYSTEM_PROMPT

# ---------------------------------------------------------------------------
# Validation Agent (semantic -- see validate_rule_schema above for the
# deterministic structural check that runs first)
# ---------------------------------------------------------------------------

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
 
 