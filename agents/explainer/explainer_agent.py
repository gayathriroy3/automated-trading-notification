# ---------------------------------------------------------------------------
# Explanation Agent
# ---------------------------------------------------------------------------
 
import json
import logging
from agents.exceptions.agent_exception import AgentError
from agents.llm.llm_utils import _call_llm
from prompts.explainer_prompt import EXPLAINER_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

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
 