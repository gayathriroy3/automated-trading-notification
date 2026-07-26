# """
# Tests for the config-driven news resource system: building sources from a
# config dict, enabling/disabling/adding/removing resources, dedupe/limit
# behavior, one resource failing not blocking the others, and registering a
# brand-new resource type at runtime.
# """
# from __future__ import annotations
# import json
# import tempfile
# import unittest
# from pathlib import Path

# from agents.sentiment.aggregator import NewsAggregator, available_source_types, register_source_type
# from agents.news.base import NewsItem, NewsSource
# from tests.fakes import FailingNewsSource, FakeNewsSource


# class _CountingSource(NewsSource):
#     """A custom third-party-style resource used only to prove the registry
#     can be extended without editing aggregator.py."""
#     call_count = 0

#     def __init__(self, config: dict):
#         self.config = config

#     def fetch(self, instrument: str, limit: int) -> list[NewsItem]:
#         _CountingSource.call_count += 1
#         return [NewsItem(title=f"custom headline for {instrument}", source="counting_source")]


# class TestBuildingFromExplicitSourceList(unittest.TestCase):
#     """Exercises the aggregator's fetch/dedupe/limit logic directly, without
#     going through a config file."""

#     def test_fetches_across_all_enabled_sources(self):
#         agg = NewsAggregator(sources=[
#             (FakeNewsSource(["Headline A"], name="s1"), 5),
#             (FakeNewsSource(["Headline B"], name="s2"), 5),
#         ])
#         headlines = agg.fetch_headlines("AAPL")
#         self.assertEqual(set(headlines), {"Headline A", "Headline B"})

#     def test_dedupes_identical_titles_across_sources(self):
#         agg = NewsAggregator(sources=[
#             (FakeNewsSource(["Same headline"], name="s1"), 5),
#             (FakeNewsSource(["same headline"], name="s2"), 5),  # different case, same story
#         ], dedupe=True)
#         headlines = agg.fetch_headlines("AAPL")
#         self.assertEqual(len(headlines), 1)

#     def test_dedupe_can_be_disabled(self):
#         agg = NewsAggregator(sources=[
#             (FakeNewsSource(["Same headline"], name="s1"), 5),
#             (FakeNewsSource(["Same headline"], name="s2"), 5),
#         ], dedupe=False)
#         self.assertEqual(len(agg.fetch_headlines("AAPL")), 2)

#     def test_max_total_caps_combined_output(self):
#         agg = NewsAggregator(sources=[
#             (FakeNewsSource([f"H{i}" for i in range(10)], name="s1"), 10),
#         ], max_total=3)
#         self.assertEqual(len(agg.fetch_headlines("AAPL")), 3)

#     def test_per_source_limit_is_respected_before_aggregation(self):
#         agg = NewsAggregator(sources=[
#             (FakeNewsSource([f"H{i}" for i in range(10)], name="s1"), 2),
#         ], max_total=100)
#         self.assertEqual(len(agg.fetch_headlines("AAPL")), 2)

#     def test_one_failing_source_does_not_block_the_others(self):
#         agg = NewsAggregator(sources=[
#             (FailingNewsSource(), 5),
#             (FakeNewsSource(["Still works"], name="s2"), 5),
#         ])
#         self.assertEqual(agg.fetch_headlines("AAPL"), ["Still works"])

#     def test_no_sources_returns_empty(self):
#         agg = NewsAggregator(sources=[])
#         self.assertEqual(agg.fetch_headlines("AAPL"), [])


# class TestBuildingFromConfig(unittest.TestCase):
#     """Exercises NewsAggregator.from_config() -- this is the path that
#     makes 'add/remove a resource in config, agent behavior changes'
#     actually true end to end."""

#     def _write_config(self, data: dict) -> Path:
#         tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
#         json.dump(data, tmp)
#         tmp.close()
#         return Path(tmp.name)

#     def test_disabled_source_is_not_included(self):
#         static_path = self._write_static_fixture({"AAPL": ["Should not appear"]})
#         config = {
#             "news_sources": [
#                 {"type": "static_file", "path": str(static_path), "enabled": False},
#             ]
#         }
#         agg = NewsAggregator.from_config(config=config)
#         self.assertEqual(agg.fetch_headlines("AAPL"), [])

#     def test_enabled_source_is_included(self):
#         static_path = self._write_static_fixture({"AAPL": ["Should appear"]})
#         config = {
#             "news_sources": [
#                 {"type": "static_file", "path": str(static_path), "enabled": True},
#             ]
#         }
#         agg = NewsAggregator.from_config(config=config)
#         self.assertEqual(agg.fetch_headlines("AAPL"), ["Should appear"])

#     def test_removing_a_source_from_config_stops_it_being_used(self):
#         static_path = self._write_static_fixture({"AAPL": ["From static file"]})
#         with_source = NewsAggregator.from_config(config={
#             "news_sources": [{"type": "static_file", "path": str(static_path)}]
#         })
#         without_source = NewsAggregator.from_config(config={"news_sources": []})

#         self.assertEqual(with_source.fetch_headlines("AAPL"), ["From static file"])
#         self.assertEqual(without_source.fetch_headlines("AAPL"), [])

#     def test_unknown_source_type_is_skipped_not_fatal(self):
#         config = {"news_sources": [{"type": "does_not_exist"}]}
#         agg = NewsAggregator.from_config(config=config)  # should not raise
#         self.assertEqual(agg.fetch_headlines("AAPL"), [])

#     def test_aggregation_settings_are_applied(self):
#         static_path = self._write_static_fixture({"AAPL": ["H1", "H2", "H3"]})
#         config = {
#             "news_sources": [{"type": "static_file", "path": str(static_path), "limit": 5}],
#             "aggregation": {"max_total_headlines": 2, "dedupe": True},
#         }
#         agg = NewsAggregator.from_config(config=config)
#         self.assertEqual(len(agg.fetch_headlines("AAPL")), 2)

#     def _write_static_fixture(self, data: dict) -> Path:
#         tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
#         json.dump(data, tmp)
#         tmp.close()
#         return Path(tmp.name)


# class TestCustomResourceRegistration(unittest.TestCase):
#     def setUp(self):
#         _CountingSource.call_count = 0
#         register_source_type("counting_source", lambda: _CountingSource)

#     def tearDown(self):
#         from agents.sentiment import aggregator as agg_module
#         agg_module._SOURCE_LOADERS.pop("counting_source", None)

#     def test_custom_resource_type_participates_in_aggregation(self):
#         agg = NewsAggregator.from_config(config={
#             "news_sources": [{"type": "counting_source", "enabled": True}]
#         })
#         headlines = agg.fetch_headlines("TSLA")
#         self.assertEqual(headlines, ["custom headline for TSLA"])
#         self.assertEqual(_CountingSource.call_count, 1)

#     def test_custom_resource_type_is_listed_as_available(self):
#         self.assertIn("counting_source", available_source_types())


# if __name__ == "__main__":
#     unittest.main()