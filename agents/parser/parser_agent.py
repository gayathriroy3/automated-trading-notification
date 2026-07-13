from agents.exceptions.agent_exception import AgentError
from agents.llm.llm_utils import _call_llm, _parse_json_response
from prompts.parser_prompt import PARSER_SYSTEM_PROMPT

 
# ---------------------------------------------------------------------------
# Condition Parser Agent
# ---------------------------------------------------------------------------

class ConditionParserAgent:
    """Turns plain English into a structured rule the deterministic engine can evaluate."""
 
    def parse(self, raw_text: str) -> dict:
        if not raw_text or not raw_text.strip():
            raise AgentError("Empty input -- nothing to parse.")
        raw = _call_llm(PARSER_SYSTEM_PROMPT, raw_text)
        return _parse_json_response(raw)
 
 