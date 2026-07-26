"""
Tests for the provider-agnostic LLM factory: config loading, the provider
registry (including registering a brand-new provider at runtime, which is
how "add a provider without touching this file" is verified), and the
dependency-injection hooks (set_llm_client/reset_llm_client) tests rely on
everywhere else in the suite.
"""
from __future__ import annotations
import tempfile
import textwrap
import unittest
from pathlib import Path

from agents.exceptions.agent_exception import AgentError
from agents.llm import factory
from agents.llm.provider.base import LLMClient


class _FakeProvider(LLMClient):
    """A minimal third-party-style provider used only to prove the
    registry can be extended without editing factory.py."""

    def __init__(self, config: dict):
        self.config = config

    def generate(self, system: str, user: str) -> str:
        return f"fake-response for provider={self.config.get('provider')}"


class TestConfigLoading(unittest.TestCase):
    def _write_config(self, text: str) -> Path:
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
        tmp.write(textwrap.dedent(text))
        tmp.close()
        return Path(tmp.name)

    def test_loads_nested_llm_block(self):
        path = self._write_config("""
            llm:
              provider: gemini
              model: models/gemini-2.5-flash
              api_key_env: GEMINI_API_KEY
        """)
        config = factory.load_llm_config(path)
        self.assertEqual(config["provider"], "gemini")
        self.assertEqual(config["model"], "models/gemini-2.5-flash")

    def test_loads_bare_mapping_without_llm_key(self):
        path = self._write_config("""
            provider: openai
            model: gpt-4.1-mini
        """)
        config = factory.load_llm_config(path)
        self.assertEqual(config["provider"], "openai")

    def test_missing_provider_key_raises(self):
        path = self._write_config("model: something\n")
        with self.assertRaises(AgentError):
            factory.load_llm_config(path)

    def test_missing_file_raises(self):
        with self.assertRaises(AgentError):
            factory.load_llm_config("/nonexistent/path/does-not-exist.yaml")


class TestProviderRegistry(unittest.TestCase):
    def setUp(self):
        factory.register_provider("fake_test_provider", lambda: _FakeProvider)

    def tearDown(self):
        factory._PROVIDER_LOADERS.pop("fake_test_provider", None)

    def test_registered_provider_is_buildable_from_a_config_dict(self):
        client = factory.build_llm_client(config={"provider": "fake_test_provider", "model": "x"})
        self.assertIsInstance(client, _FakeProvider)
        self.assertEqual(client.generate("s", "u"), "fake-response for provider=fake_test_provider")

    def test_unknown_provider_raises_with_helpful_message(self):
        with self.assertRaises(AgentError) as ctx:
            factory.build_llm_client(config={"provider": "totally_made_up"})
        self.assertIn("totally_made_up", str(ctx.exception))

    def test_provider_name_matching_is_case_insensitive(self):
        client = factory.build_llm_client(config={"provider": "FAKE_TEST_PROVIDER"})
        self.assertIsInstance(client, _FakeProvider)

    def test_available_providers_includes_built_ins(self):
        names = factory.available_providers()
        for expected in ("gemini", "openai", "anthropic", "claude"):
            self.assertIn(expected, names)


class TestSingletonInjectionHooks(unittest.TestCase):
    """These are what let every other test in the suite avoid touching
    config files or real API keys at all."""

    def tearDown(self):
        factory.reset_llm_client()

    def test_set_llm_client_overrides_get_llm_client(self):
        fake = _FakeProvider({"provider": "manual"})
        factory.set_llm_client(fake)
        self.assertIs(factory.get_llm_client(), fake)

    def test_reset_llm_client_clears_the_singleton(self):
        fake = _FakeProvider({"provider": "manual"})
        factory.set_llm_client(fake)
        factory.reset_llm_client()
        # After reset, get_llm_client() would rebuild from config/llm_config.yaml
        # rather than returning the fake -- confirm the fake is no longer cached.
        self.assertIsNot(getattr(factory, "_client"), fake)


if __name__ == "__main__":
    unittest.main()