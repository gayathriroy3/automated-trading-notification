"""
Deterministic conflict-detection tests -- interval arithmetic, no LLM.
"""
from __future__ import annotations
import unittest

from backend.rule_engine.conflict_checker import (
    check_deterministic_conflicts, check_linked_ordering, check_self_contradiction,
)


class TestSelfContradiction(unittest.TestCase):
    def test_rsi_impossible_and_range_is_flagged(self):
        rule = {"logic_operator": "AND", "conditions": [
            {"type": "indicator", "indicator_name": "RSI", "comparator": ">", "value": 70},
            {"type": "indicator", "indicator_name": "RSI", "comparator": "<", "value": 40},
        ]}
        problems = check_self_contradiction(rule)
        self.assertEqual(len(problems), 1)
        self.assertIn("RSI", problems[0])

    def test_same_impossible_range_with_or_logic_is_not_flagged(self):
        """OR semantics mean the two ranges don't need to overlap."""
        rule = {"logic_operator": "OR", "conditions": [
            {"type": "indicator", "indicator_name": "RSI", "comparator": ">", "value": 70},
            {"type": "indicator", "indicator_name": "RSI", "comparator": "<", "value": 40},
        ]}
        self.assertEqual(check_self_contradiction(rule), [])

    def test_overlapping_and_range_is_not_flagged(self):
        rule = {"logic_operator": "AND", "conditions": [
            {"type": "indicator", "indicator_name": "RSI", "comparator": ">", "value": 40},
            {"type": "indicator", "indicator_name": "RSI", "comparator": "<", "value": 70},
        ]}
        self.assertEqual(check_self_contradiction(rule), [])

    def test_single_condition_cannot_self_contradict(self):
        rule = {"logic_operator": "AND", "conditions": [
            {"type": "price", "comparator": ">", "value": 210},
        ]}
        self.assertEqual(check_self_contradiction(rule), [])


class TestLinkedOrdering(unittest.TestCase):
    def test_stop_loss_above_long_entry_is_backwards(self):
        entry = {"instrument": "X", "condition_type": "entry_buy",
                  "conditions": [{"type": "price", "comparator": ">", "value": 2500}]}
        bad_sl = {"instrument": "X", "condition_type": "stop_loss",
                  "conditions": [{"type": "price", "comparator": "<", "value": 2600}]}
        problems = check_linked_ordering(bad_sl, [entry])
        self.assertEqual(len(problems), 1)
        self.assertIn("stop loss", problems[0].lower())

    def test_stop_loss_below_long_entry_is_fine(self):
        entry = {"instrument": "X", "condition_type": "entry_buy",
                  "conditions": [{"type": "price", "comparator": ">", "value": 2500}]}
        good_sl = {"instrument": "X", "condition_type": "stop_loss",
                   "conditions": [{"type": "price", "comparator": "<", "value": 2450}]}
        self.assertEqual(check_linked_ordering(good_sl, [entry]), [])

    def test_stop_loss_below_short_entry_is_backwards(self):
        entry = {"instrument": "X", "condition_type": "entry_sell",
                  "conditions": [{"type": "price", "comparator": "<", "value": 2500}]}
        bad_sl = {"instrument": "X", "condition_type": "stop_loss",
                  "conditions": [{"type": "price", "comparator": "<", "value": 2400}]}
        problems = check_linked_ordering(bad_sl, [entry])
        self.assertEqual(len(problems), 1)

    def test_target_below_long_entry_is_backwards(self):
        entry = {"instrument": "X", "condition_type": "entry_buy",
                  "conditions": [{"type": "price", "comparator": ">", "value": 2500}]}
        bad_target = {"instrument": "X", "condition_type": "target",
                      "conditions": [{"type": "price", "comparator": ">", "value": 2450}]}
        problems = check_linked_ordering(bad_target, [entry])
        self.assertEqual(len(problems), 1)
        self.assertIn("target", problems[0].lower())

    def test_unrelated_instrument_is_ignored(self):
        entry = {"instrument": "X", "condition_type": "entry_buy",
                  "conditions": [{"type": "price", "comparator": ">", "value": 2500}]}
        other_sl = {"instrument": "Y", "condition_type": "stop_loss",
                    "conditions": [{"type": "price", "comparator": "<", "value": 999999}]}
        self.assertEqual(check_linked_ordering(other_sl, [entry]), [])


class TestCombinedDeterministicConflicts(unittest.TestCase):
    def test_aggregates_both_checks(self):
        new_rule = {
            "instrument": "X", "condition_type": "entry_buy", "logic_operator": "AND",
            "conditions": [
                {"type": "indicator", "indicator_name": "RSI", "comparator": ">", "value": 70},
                {"type": "indicator", "indicator_name": "RSI", "comparator": "<", "value": 40},
            ],
        }
        self.assertEqual(len(check_deterministic_conflicts(new_rule, [])), 1)

    def test_clean_rule_against_clean_history_has_no_conflicts(self):
        new_rule = {"instrument": "X", "condition_type": "entry_buy",
                    "conditions": [{"type": "price", "comparator": ">", "value": 210}]}
        existing = [{"instrument": "X", "condition_type": "stop_loss",
                    "conditions": [{"type": "price", "comparator": "<", "value": 200}]}]
        self.assertEqual(check_deterministic_conflicts(new_rule, existing), [])


if __name__ == "__main__":
    unittest.main()