"""
Provider-agnostic LLM call helper used by every agent.

_call_llm() used to import a Gemini client by name. It now goes through
agents.llm.factory.get_llm_client(), which builds whatever provider
config/llm_config.yaml selects (Gemini, Claude, OpenAI, or anything else
registered). No agent file needs to change when the provider changes.
"""

import json
import logging

from agents.exceptions.agent_exception import AgentError
from agents.llm.factory import get_llm_client

logger = logging.getLogger(__name__)


def _call_llm(system: str, user: str) -> str:
    client = get_llm_client()
    return client.generate(system, user)


def _parse_json_response(raw: str) -> dict:
    """LLMs occasionally wrap JSON in markdown fences despite instructions
    not to -- strip those defensively, then fail loudly (not silently) on
    genuinely unparseable output."""
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        logger.warning("Model returned non-JSON output: %r", (raw or "")[:200])
        raise AgentError("Model did not return valid JSON -- try rephrasing the condition.") from exc