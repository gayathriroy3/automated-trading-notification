"""
Deterministic conflict detection for trade rules.

Some contradictions can be *proven* wrong with plain interval arithmetic --
"RSI > 70 AND RSI < 40" has no value that satisfies both, full stop. There's
no reason to spend an LLM call (and accept a nonzero hallucination risk) on
something this mechanical. This module handles the checks that reduce to
clean numeric logic. agents.ValidationAgent still handles fuzzier cases that
don't reduce cleanly (duplicate phrasing, ambiguous intent) -- but anything
caught here is caught with certainty, not a judgment call.
"""

from __future__ import annotations
import math


def _interval(cond: dict) -> tuple[float, float]:
    """The (low, high) range of values that satisfy one condition."""
    comparator, value = cond.get("comparator"), cond.get("value")
    if comparator in (">", ">="):
        return (value, math.inf)
    if comparator in ("<", "<="):
        return (-math.inf, value)
    if comparator == "between":
        lo, hi = value
        return (lo, hi)
    return (-math.inf, math.inf)


def check_self_contradiction(rule: dict) -> list[str]:
    """Catches AND'd conditions on the same signal whose ranges can never
    overlap -- e.g. RSI > 70 AND RSI < 40. Only meaningful for AND logic;
    the same ranges joined by OR are not a contradiction."""
    if rule.get("logic_operator", "AND") != "AND":
        return []

    problems = []
    groups: dict[tuple, list[dict]] = {}
    for cond in rule.get("conditions", []):
        key = (cond.get("type"), cond.get("indicator_name"))
        groups.setdefault(key, []).append(cond)

    for (ctype, indicator), conds in groups.items():
        if len(conds) < 2:
            continue
        low, high = -math.inf, math.inf
        for cond in conds:
            c_low, c_high = _interval(cond)
            low, high = max(low, c_low), min(high, c_high)
        if low > high:
            label = indicator or ctype
            problems.append(
                f"Conflict detected: the {label} conditions in this rule can never "
                f"all be true at the same time (combined range is empty)."
            )
    return problems


def _first_price_value(rule: dict) -> float | None:
    for cond in rule.get("conditions", []):
        if cond.get("type") == "price" and isinstance(cond.get("value"), (int, float)):
            return cond["value"]
    return None


def check_linked_ordering(new_rule: dict, existing_rules: list) -> list[str]:
    """Catches a stop loss or target that sits on the wrong side of its
    entry -- e.g. a long entry above 2500 paired with a stop loss above
    2600 (the stop is *higher* than the entry, backwards for a long)."""
    problems: list[str] = []
    instrument = new_rule.get("instrument")
    new_type = new_rule.get("condition_type")
    new_price = _first_price_value(new_rule)
    if new_price is None or new_type not in {"entry_buy", "entry_sell", "stop_loss", "target"}:
        return problems

    for other in existing_rules:
        if other.get("instrument") != instrument:
            continue
        other_type = other.get("condition_type")
        other_price = _first_price_value(other)
        if other_price is None:
            continue

        entry_price = entry_dir = exit_price = exit_kind = None
        if new_type in {"entry_buy", "entry_sell"} and other_type in {"stop_loss", "target"}:
            entry_price, entry_dir = new_price, new_type
            exit_price, exit_kind = other_price, other_type
        elif other_type in {"entry_buy", "entry_sell"} and new_type in {"stop_loss", "target"}:
            entry_price, entry_dir = other_price, other_type
            exit_price, exit_kind = new_price, new_type
        if entry_price is None:
            continue

        is_long = entry_dir == "entry_buy"
        if exit_kind == "stop_loss":
            if is_long and exit_price >= entry_price:
                problems.append(
                    f"Conflict detected: stop loss ({exit_price}) is not below the "
                    f"long entry price ({entry_price})."
                )
            if not is_long and exit_price <= entry_price:
                problems.append(
                    f"Conflict detected: stop loss ({exit_price}) is not above the "
                    f"short entry price ({entry_price})."
                )
        elif exit_kind == "target":
            if is_long and exit_price <= entry_price:
                problems.append(
                    f"Conflict detected: target ({exit_price}) is not above the "
                    f"long entry price ({entry_price})."
                )
            if not is_long and exit_price >= entry_price:
                problems.append(
                    f"Conflict detected: target ({exit_price}) is not below the "
                    f"short entry price ({entry_price})."
                )
    return problems


def check_deterministic_conflicts(new_rule: dict, existing_rules: list) -> list[str]:
    return check_self_contradiction(new_rule) + check_linked_ordering(new_rule, existing_rules)


if __name__ == "__main__":
    # RSI > 70 AND RSI < 40 -- impossible, no LLM needed to know that.
    r1 = {"logic_operator": "AND", "conditions": [
        {"type": "indicator", "indicator_name": "RSI", "comparator": ">", "value": 70},
        {"type": "indicator", "indicator_name": "RSI", "comparator": "<", "value": 40},
    ]}
    print("RSI>70 AND RSI<40:", check_self_contradiction(r1))

    # Buy above 2500, then a stop loss above 2600 -- backwards for a long.
    entry = {"instrument": "X", "condition_type": "entry_buy",
              "conditions": [{"type": "price", "comparator": ">", "value": 2500}]}
    bad_sl = {"instrument": "X", "condition_type": "stop_loss",
              "conditions": [{"type": "price", "comparator": "<", "value": 2600}]}
    print("Buy>2500 + SL<2600:", check_linked_ordering(bad_sl, [entry]))

    # A sane pair should produce no conflicts.
    good_sl = {"instrument": "X", "condition_type": "stop_loss",
               "conditions": [{"type": "price", "comparator": "<", "value": 2450}]}
    print("Buy>2500 + SL<2450 (sane):", check_linked_ordering(good_sl, [entry]))