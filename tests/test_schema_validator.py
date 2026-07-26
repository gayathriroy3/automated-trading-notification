"""
Deterministic schema validation tests -- this is what stops "hi" (or a
hallucinated field) from ever reaching the database, regardless of what
provider's LLM produced the parse.
"""
from __future__ import annotations
import unittest

from agents.parser.schema_validator import validate_rule_schema


def valid_rule(**overrides) -> dict:
    base = {
        "instrument": "AAPL",
        "condition_type": "entry_buy",
        "logic_operator": "AND",
        "conditions": [{"type": "price", "comparator": ">", "value": 210}],
        "clarification_needed": None,
    }
    base.update(overrides)
    return base


class TestSchemaValidator(unittest.TestCase):
    def test_well_formed_rule_has_no_problems(self):
        self.assertEqual(validate_rule_schema(valid_rule()), [])

    def test_non_trade_input_is_rejected(self):
        rule = valid_rule(instrument=None, condition_type=None, conditions=[],
                          clarification_needed="This doesn't describe a trade condition.")
        problems = validate_rule_schema(rule)
        self.assertTrue(any("instrument" in p.lower() for p in problems))
        self.assertTrue(any("clarification" in p.lower() or "ambiguity" in p.lower() for p in problems))

    def test_non_dict_response_is_rejected(self):
        self.assertEqual(validate_rule_schema("not a dict"), ["Model response wasn't a JSON object."])

    def test_bad_ticker_format_is_rejected(self):
        problems = validate_rule_schema(valid_rule(instrument="this is not a ticker"))
        self.assertTrue(any("ticker" in p.lower() for p in problems))

    def test_unrecognized_condition_type_is_rejected(self):
        problems = validate_rule_schema(valid_rule(condition_type="hold_forever"))
        self.assertTrue(any("condition type" in p.lower() for p in problems))

    def test_empty_conditions_is_rejected(self):
        problems = validate_rule_schema(valid_rule(conditions=[]))
        self.assertTrue(any("no conditions" in p.lower() for p in problems))

    def test_invalid_comparator_is_rejected(self):
        problems = validate_rule_schema(valid_rule(
            conditions=[{"type": "price", "comparator": "roughly", "value": 210}]
        ))
        self.assertTrue(any("comparator" in p.lower() for p in problems))

    def test_between_requires_two_numbers(self):
        problems = validate_rule_schema(valid_rule(
            conditions=[{"type": "price", "comparator": "between", "value": 210}]
        ))
        self.assertTrue(any("between" in p.lower() for p in problems))

    def test_between_with_two_numbers_is_fine(self):
        problems = validate_rule_schema(valid_rule(
            conditions=[{"type": "indicator", "comparator": "between", "value": [40, 70],
                        "indicator_name": "RSI", "indicator_period": 14}]
        ))
        self.assertEqual(problems, [])

    def test_non_numeric_value_is_rejected(self):
        problems = validate_rule_schema(valid_rule(
            conditions=[{"type": "price", "comparator": ">", "value": "high"}]
        ))
        self.assertTrue(any("must be a number" in p.lower() for p in problems))

    def test_unsupported_indicator_is_rejected(self):
        problems = validate_rule_schema(valid_rule(
            conditions=[{"type": "indicator", "comparator": ">", "value": 50,
                        "indicator_name": "MACD"}]
        ))
        self.assertTrue(any("indicator" in p.lower() for p in problems))


if __name__ == "__main__":
    unittest.main()