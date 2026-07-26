# """
# News Sentiment Agent tests -- different "news behaviour" scenarios
# (positive / negative / neutral / no news / malformed model output), plus
# the sentiment_contradicts_direction() logic that decides whether a trigger
# gets a caution attached.
# """
# from __future__ import annotations
# import unittest

# from agents.llm import factory
# from agents.sentiment.sentiment_agent import NewsAggregator
# from agents.sentiment.sentiment_agent import NewsSentimentAgent, sentiment_contradicts_direction
# from prompts.sentiment_prompt import NEWS_SENTIMENT_SYSTEM_PROMPT
# from tests.fakes import FakeNewsSource, ScriptedLLMClient, sentiment_json


# class TestSentimentClassificationWithExplicitHeadlines(unittest.TestCase):
#     """headlines= bypasses the aggregator entirely -- tests the
#     classification step in isolation."""

#     def setUp(self):
#         self.llm = ScriptedLLMClient()
#         factory.set_llm_client(self.llm)
#         self.agent = NewsSentimentAgent()

#     def tearDown(self):
#         factory.reset_llm_client()

#     def test_no_headlines_returns_neutral_without_calling_the_llm(self):
#         result = self.agent.analyze("AAPL", headlines=[])
#         self.assertEqual(result["sentiment"], "neutral")
#         self.assertEqual(self.llm.calls, [])  # short-circuited before any LLM call

#     def test_positive_headlines_classified_positive(self):
#         self.llm.set_response(NEWS_SENTIMENT_SYSTEM_PROMPT,
#                                sentiment_json("positive", "Strong earnings beat."))
#         result = self.agent.analyze("AAPL", headlines=["Apple beats earnings estimates"])
#         self.assertEqual(result["sentiment"], "positive")

#     def test_negative_headlines_classified_negative(self):
#         self.llm.set_response(NEWS_SENTIMENT_SYSTEM_PROMPT,
#                                sentiment_json("negative", "Regulatory probe announced."))
#         result = self.agent.analyze("AAPL", headlines=["Apple faces antitrust probe"])
#         self.assertEqual(result["sentiment"], "negative")

#     def test_malformed_llm_output_degrades_to_unknown_not_a_crash(self):
#         self.llm.set_response(NEWS_SENTIMENT_SYSTEM_PROMPT, "not valid json at all")
#         result = self.agent.analyze("AAPL", headlines=["Some headline"])
#         self.assertEqual(result["sentiment"], "unknown")

#     def test_response_missing_sentiment_key_degrades_to_unknown(self):
#         self.llm.set_response(NEWS_SENTIMENT_SYSTEM_PROMPT, '{"summary": "no sentiment field"}')
#         result = self.agent.analyze("AAPL", headlines=["Some headline"])
#         self.assertEqual(result["sentiment"], "unknown")


# class TestSentimentAgentPullsFromConfiguredResources(unittest.TestCase):
#     """The production path: analyze(instrument) with no headlines override
#     pulls from whatever resources the injected aggregator is built from --
#     standing in for config/news_sources_config.yaml."""

#     def setUp(self):
#         self.llm = ScriptedLLMClient()
#         factory.set_llm_client(self.llm)

#     def tearDown(self):
#         factory.reset_llm_client()

#     def test_pulls_headlines_from_every_source_in_the_aggregator(self):
#         aggregator = NewsAggregator(sources=[
#             (FakeNewsSource(["Headline from resource A"], name="a"), 5),
#             (FakeNewsSource(["Headline from resource B"], name="b"), 5),
#         ])
#         self.llm.set_response(NEWS_SENTIMENT_SYSTEM_PROMPT, sentiment_json("neutral", "Mixed coverage."))
#         agent = NewsSentimentAgent(aggregator=aggregator)

#         agent.analyze("AAPL")

#         self.assertEqual(len(self.llm.calls), 1)
#         _, user_prompt = self.llm.calls[0]
#         self.assertIn("Headline from resource A", user_prompt)
#         self.assertIn("Headline from resource B", user_prompt)

#     def test_removing_all_resources_yields_neutral_with_no_llm_call(self):
#         agent = NewsSentimentAgent(aggregator=NewsAggregator(sources=[]))
#         result = agent.analyze("AAPL")
#         self.assertEqual(result["sentiment"], "neutral")
#         self.assertEqual(self.llm.calls, [])


# class TestSentimentContradictsDirection(unittest.TestCase):
#     """The caution-flagging logic: buy signal + bad news, sell signal +
#     good news -- everything else should NOT be flagged."""

#     def test_buy_flagged_on_negative(self):
#         self.assertTrue(sentiment_contradicts_direction("entry_buy", "negative"))

#     def test_buy_flagged_on_strongly_negative(self):
#         self.assertTrue(sentiment_contradicts_direction("entry_buy", "strongly_negative"))

#     def test_buy_not_flagged_on_positive_or_neutral(self):
#         self.assertFalse(sentiment_contradicts_direction("entry_buy", "positive"))
#         self.assertFalse(sentiment_contradicts_direction("entry_buy", "neutral"))

#     def test_sell_flagged_on_positive(self):
#         self.assertTrue(sentiment_contradicts_direction("entry_sell", "positive"))

#     def test_sell_not_flagged_on_negative_or_neutral(self):
#         self.assertFalse(sentiment_contradicts_direction("entry_sell", "negative"))
#         self.assertFalse(sentiment_contradicts_direction("entry_sell", "neutral"))

#     def test_stop_loss_and_target_are_never_flagged(self):
#         for sentiment in ("positive", "negative", "strongly_positive", "strongly_negative", "unknown"):
#             self.assertFalse(sentiment_contradicts_direction("stop_loss", sentiment))
#             self.assertFalse(sentiment_contradicts_direction("target", sentiment))

#     def test_unknown_sentiment_is_never_flagged(self):
#         """A failed sentiment check (see test above) shouldn't itself read
#         as a caution -- 'unknown' isn't evidence of anything."""
#         self.assertFalse(sentiment_contradicts_direction("entry_buy", "unknown"))
#         self.assertFalse(sentiment_contradicts_direction("entry_sell", "unknown"))


# if __name__ == "__main__":
#     unittest.main()