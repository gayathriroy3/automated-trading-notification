"""
Provider-agnostic LLM client interface.

Every concrete provider (Gemini, OpenAI, Anthropic/Claude, ...) implements
this one method. Nothing else in the codebase is allowed to import a
provider SDK directly -- agents talk to `LLMClient.generate`, never to
`genai` or `openai` or `anthropic` by name. That's what makes switching
providers a config change instead of a code change.
"""

from __future__ import annotations
from abc import ABC, abstractmethod


class LLMClient(ABC):
    """Minimal contract every provider adapter must satisfy."""

    @abstractmethod
    def generate(self, system: str, user: str) -> str:
        """Send a system+user prompt pair, return the raw text response.

        Implementations should raise agents.exceptions.agent_exception.AgentError
        (not a provider-specific exception) on any failure, so callers never
        need to know which provider is behind the client.
        """
        raise NotImplementedError