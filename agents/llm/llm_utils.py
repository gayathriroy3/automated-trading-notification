import logging
import json
from agents.exceptions.agent_exception import AgentError
from gemini_client import client,MODEL
logger = logging.getLogger(__name__)


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
 
 