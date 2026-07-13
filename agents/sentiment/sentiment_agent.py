# ---------------------------------------------------------------------------
# News Sentiment Agent
# ---------------------------------------------------------------------------

 
from agents.exceptions.agent_exception import AgentError
from agents.llm.llm_utils import _call_llm, _parse_json_response
from prompts.sentiment_prompt import NEWS_SENTIMENT_SYSTEM_PROMPT
import logging
logger = logging.getLogger(__name__)


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