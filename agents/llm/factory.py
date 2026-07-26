"""
LLM provider factory.

This is the one place that knows how to turn config/llm_config.yaml into a
concrete LLMClient. Every agent calls agents.llm.llm_utils._call_llm(), which
goes through get_llm_client() here -- nothing else in the codebase names a
provider SDK. Switching from Gemini to Claude to OpenAI-to-a-local-server is
therefore a config edit, not a code change.

Adding a brand-new provider (say, a self-hosted model) means writing one
class that implements agents.llm.base.LLMClient and calling
register_provider("my_provider", lambda: MyProviderClass) -- no edits
needed here or in any agent.
"""

from __future__ import annotations
import logging
import os
import threading
from pathlib import Path
from typing import Callable, Optional

import yaml

from agents.exceptions.agent_exception import AgentError
from agents.llm.provider.base import LLMClient

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "llm_config.yaml"


# ---------------------------------------------------------------------------
# Provider registry -- lazy loaders so choosing one provider never forces
# every other provider's SDK to be installed.
# ---------------------------------------------------------------------------


def _load_openrouter_provider():
    from agents.llm.provider.openai_provider import OpenRouterProvider
    return OpenRouterProvider


_PROVIDER_LOADERS: dict[str, Callable[[], type]] = {
    "openrouter": _load_openrouter_provider
}


def register_provider(name: str, loader: Callable[[], type]) -> None:
    """Plug in a new backend without touching this file, e.g.:

        register_provider("ollama", lambda: OllamaProvider)

    `loader` is called only when that provider is actually selected in
    config, so it's fine for it to import a package that may not be
    installed.
    """
    _PROVIDER_LOADERS[name.lower()] = loader


def available_providers() -> list[str]:
    return sorted(_PROVIDER_LOADERS)


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def load_llm_config(path: Optional[str | os.PathLike] = None) -> dict:
    """Reads config/llm_config.yaml (or LLM_CONFIG_PATH / an explicit path).
    Accepts either a top-level {"llm": {...}} document or a bare mapping,
    so a config file can be as simple as `provider: gemini\\nmodel: ...`."""
    config_path = Path(path) if path else Path(os.getenv("LLM_CONFIG_PATH", DEFAULT_CONFIG_PATH))
    if not config_path.exists():
        raise AgentError(f"LLM config file not found: {config_path}")
    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    llm_config = data.get("llm", data)
    if not isinstance(llm_config, dict) or "provider" not in llm_config:
        raise AgentError(f"'{config_path}' is missing a required 'llm.provider' key.")
    return llm_config


def build_llm_client(config: Optional[dict] = None, config_path: Optional[str | os.PathLike] = None) -> LLMClient:
    """Builds a fresh client from config -- no caching. Most callers want
    get_llm_client() below instead, which caches this for the process."""
    config = config or load_llm_config(config_path)
    provider_name = str(config.get("provider", "")).lower()
    loader = _PROVIDER_LOADERS.get(provider_name)
    if loader is None:
        raise AgentError(
            f"Unknown LLM provider '{provider_name}'. Known providers: "
            f"{available_providers()}. Register custom ones with "
            f"agents.llm.factory.register_provider()."
        )
    provider_cls = loader()
    logger.info("Building LLM client for provider=%s model=%s", provider_name, config.get("model"))
    return provider_cls(config)


# ---------------------------------------------------------------------------
# Process-wide singleton + test hooks
# ---------------------------------------------------------------------------

_client_lock = threading.Lock()
_client: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    """Lazily builds (once) and returns the configured LLM client. Lazy on
    purpose: importing agent modules should never require an API key to be
    set -- only actually calling the LLM should."""
    global _client
    with _client_lock:
        if _client is None:
            _client = build_llm_client()
        return _client


def set_llm_client(client: LLMClient) -> None:
    """Injects a client directly, bypassing config entirely. This is how
    tests swap in a fake/mock LLM -- see tests/fakes.py."""
    global _client
    with _client_lock:
        _client = client


def reset_llm_client() -> None:
    """Drops the cached singleton so the next get_llm_client() call rebuilds
    it from config. Call in test teardown after set_llm_client()."""
    global _client
    with _client_lock:
        _client = None