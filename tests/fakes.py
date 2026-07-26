"""
Test doubles shared across the suite.

None of these hit a network or need an API key -- that's the point. They
let the tests exercise the real orchestrator / rule engine / conflict
checker / aggregator logic while standing in for "the LLM said X" and
"this news resource returned Y".
"""

from __future__ import annotations
import json
from typing import Callable, Optional, Union

from agents.llm.provider.base import LLMClient
# from agents.news.base import NewsItem, NewsSource


# ---------------------------------------------------------------------------
# Fake LLM
# ---------------------------------------------------------------------------

Responder = Union[str, list, Callable[[str, str], str]]


class ScriptedLLMClient(LLMClient):
    """Routes each call to a canned response keyed by *which system prompt*
    was used -- one instance can stand in for the parser, validator,
    explainer, and sentiment agents at once in an orchestrator-level test,
    with each agent's behavior configured independently via set_response().
    """

    def __init__(self):
        self.calls: list[tuple[str, str]] = []
        self._responses: dict[str, Responder] = {}

    def set_response(self, system_prompt: str, response: Responder) -> None:
        """response is one of:
          - a plain string: returned every time this prompt is used
          - a callable(system, user) -> str: computed fresh each call
          - a list of strings: consumed one per call, last value repeats
            once exhausted (lets a test simulate the market/news changing
            between two ticks of the same scenario)
        """
        self._responses[system_prompt] = response

    def generate(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        response = self._responses.get(system)
        if response is None:
            raise AssertionError(
                f"ScriptedLLMClient has no response configured for this prompt "
                f"(first 60 chars): {system[:60]!r}"
            )
        if callable(response):
            return response(system, user)
        if isinstance(response, list):
            return response.pop(0) if len(response) > 1 else response[0]
        return response


# ---------------------------------------------------------------------------
# Canned JSON payload builders -- match the schemas each prompt asks for
# (see prompts/*.py) so tests read as "what the model would plausibly say"
# rather than raw JSON strings.
# ---------------------------------------------------------------------------

def parser_json(instrument: Optional[str], condition_type: Optional[str],
                 conditions: list, logic_operator: str = "AND",
                 clarification_needed: Optional[str] = None) -> str:
    return json.dumps({
        "instrument": instrument,
        "condition_type": condition_type,
        "logic_operator": logic_operator,
        "conditions": conditions,
        "clarification_needed": clarification_needed,
    })


def validator_json(approved: bool, issues: Optional[list[str]] = None) -> str:
    return json.dumps({"approved": approved, "issues": issues or []})


def sentiment_json(sentiment: str, summary: str) -> str:
    return json.dumps({"sentiment": sentiment, "summary": summary})


# ---------------------------------------------------------------------------
# Fake news sources
# ---------------------------------------------------------------------------

# class FakeNewsSource(NewsSource):
#     """Returns a fixed, pre-scripted list of headlines regardless of
#     instrument -- for tests that only care about "the sentiment agent got
#     these headlines", not about any real resource."""

#     def __init__(self, headlines: list[str], name: str = "fake_source"):
#         self.name = name
#         self._headlines = headlines

#     def fetch(self, instrument: str, limit: int) -> list[NewsItem]:
#         return [NewsItem(title=h, source=self.name) for h in self._headlines[:limit]]


# class FailingNewsSource(NewsSource):
#     """Always raises -- used to prove one broken resource can't take down
#     the rest of the aggregation."""

#     name = "failing_source"

#     def fetch(self, instrument: str, limit: int) -> list[NewsItem]:
#         raise RuntimeError("simulated resource outage")