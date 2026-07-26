"""
OpenRouter provider.

Uses OpenRouter's OpenAI-compatible API.

base_url = https://openrouter.ai/api/v1

Recommended model:
    openrouter/auto

which automatically routes to an available model.
"""

from __future__ import annotations

import logging
import os

from openai import OpenAI

from agents.exceptions.agent_exception import AgentError
from agents.llm.provider.base import LLMClient

logger = logging.getLogger(__name__)


class OpenRouterProvider(LLMClient):
    def __init__(self, config: dict):
        api_key = os.getenv("OPENROUTER_API_KEY")

        if not api_key:
            raise AgentError(
                "OPENROUTER_API_KEY environment variable is not set."
            )

        self.model = config.get("model", "openrouter/auto")
        self.temperature = config.get("temperature", 0)
        self.max_tokens = config.get("max_tokens")

        self._client = OpenAI(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
        )

    def generate(self, system: str, user: str) -> str:
        try:
            kwargs = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            }

            if self.temperature is not None:
                kwargs["temperature"] = self.temperature

            if self.max_tokens is not None:
                kwargs["max_tokens"] = self.max_tokens

            response = self._client.chat.completions.create(**kwargs)

            return response.choices[0].message.content.strip()

        except Exception as exc:
            logger.exception("OpenRouter call failed")
            raise AgentError(f"OpenRouter call failed: {exc}") from exc