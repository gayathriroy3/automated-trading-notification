"""
Deterministic rule evaluation engine.

Maintains incremental technical indicators per instrument and evaluates
trader-confirmed rules against each new price bar. Emits a TriggerEvent
only on a false -> true transition, so a condition that stays true for
many bars in a row fires exactly once. No LLM calls happen anywhere in
this file -- the agents in agents.py only touch this system before the
rule exists (parsing) and after it fires (explaining).
"""

from __future__ import annotations
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional, Union


class Comparator(str, Enum):
    GT = ">"
    LT = "<"
    GTE = ">="
    LTE = "<="
    BETWEEN = "between"


class ConditionType(str, Enum):
    PRICE = "price"
    INDICATOR = "indicator"


@dataclass
class Condition:
    type: ConditionType
    comparator: Comparator
    value: Union[float, tuple]
    indicator_name: Optional[str] = None   # "EMA" | "RSI"
    indicator_period: Optional[int] = None

    def __post_init__(self):
        # Defense in depth: even if upstream validation (agents.py's
        # validate_rule_schema) is somehow bypassed, a malformed condition
        # should fail loudly here rather than corrupt evaluation later.
        if self.comparator == Comparator.BETWEEN:
            if not (isinstance(self.value, (tuple, list)) and len(self.value) == 2):
                raise ValueError("BETWEEN comparator requires a (low, high) pair.")
        elif not isinstance(self.value, (int, float)):
            raise ValueError(f"{self.comparator} comparator requires a numeric value, got {self.value!r}.")
        if self.type == ConditionType.INDICATOR and self.indicator_name not in {"EMA", "RSI"}:
            raise ValueError(f"Unsupported indicator: {self.indicator_name!r}")


@dataclass
class Rule:
    instrument: str
    condition_type: str          # "entry_buy" | "entry_sell" | "stop_loss" | "target"
    conditions: list
    logic_operator: str = "AND"  # "AND" | "OR"
    linked_rule_ids: list = field(default_factory=list)
    rule_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: str = "active"       # "active" | "triggered" | "cancelled" | "expired"
    raw_input: str = ""          # original plain-English text, kept for audit

    def __post_init__(self):
        if not self.instrument:
            raise ValueError("Rule requires a non-empty instrument.")
        if not self.conditions:
            raise ValueError("Rule requires at least one condition.")


class EMA:
    def __init__(self, period: int):
        self.k = 2 / (period + 1)
        self.value: Optional[float] = None

    def update(self, price: float) -> float:
        self.value = price if self.value is None else price * self.k + self.value * (1 - self.k)
        return self.value


class RSI:
    """Wilder's smoothing method."""
    def __init__(self, period: int = 14):
        self.period = period
        self.avg_gain: Optional[float] = None
        self.avg_loss: Optional[float] = None
        self.prev_price: Optional[float] = None
        self.value: Optional[float] = None

    def update(self, price: float) -> Optional[float]:
        if self.prev_price is None:
            self.prev_price = price
            return None
        change = price - self.prev_price
        gain, loss = max(change, 0), max(-change, 0)
        if self.avg_gain is None:
            self.avg_gain, self.avg_loss = gain, loss
        else:
            self.avg_gain = (self.avg_gain * (self.period - 1) + gain) / self.period
            self.avg_loss = (self.avg_loss * (self.period - 1) + loss) / self.period
        self.prev_price = price
        rs = self.avg_gain / self.avg_loss if self.avg_loss else float("inf")
        self.value = 100 - (100 / (1 + rs))
        return self.value


class IndicatorState:
    """Per-instrument bag of live indicator values, lazily created per period."""
    def __init__(self):
        self._emas: dict = {}
        self._rsis: dict = {}
        self.last_price: Optional[float] = None
        self.last_volume: float = 0.0

    def on_bar(self, price: float, volume: float):
        self.last_price = price
        self.last_volume = volume
        for ema in self._emas.values():
            ema.update(price)
        for rsi in self._rsis.values():
            rsi.update(price)

    def ema(self, period: int) -> Optional[float]:
        self._emas.setdefault(period, EMA(period))
        return self._emas[period].value

    def rsi(self, period: int = 14) -> Optional[float]:
        self._rsis.setdefault(period, RSI(period))
        return self._rsis[period].value


@dataclass
class TriggerEvent:
    rule: Rule
    instrument: str
    matched_at: float
    matched_values: dict


class RuleEngine:
    def __init__(self, on_trigger: Callable[[TriggerEvent], None]):
        self.rules: dict = {}
        self.states: dict = {}
        self._was_true: dict = {}
        self.on_trigger = on_trigger

    def add_rule(self, rule: Rule):
        self.rules[rule.rule_id] = rule
        self._was_true[rule.rule_id] = False

    def on_tick(self, instrument: str, price: float, volume: float):
        """Feed one new price bar (or tick) for an instrument through the engine."""
        state = self.states.setdefault(instrument, IndicatorState())
        state.on_bar(price, volume)

        for rule in self.rules.values():
            if rule.instrument != instrument or rule.status != "active":
                continue

            matched, values = self._evaluate(rule, state, price)
            was_true = self._was_true[rule.rule_id]

            if matched and not was_true:
                rule.status = "triggered"
                event = TriggerEvent(
                    rule=rule, instrument=instrument,
                    matched_at=time.time(), matched_values=values,
                )
                self.on_trigger(event)
                self._cancel_linked(rule)

            self._was_true[rule.rule_id] = matched

    def _evaluate(self, rule: Rule, state: IndicatorState, price: float):
        results, values = [], {}
        for cond in rule.conditions:
            ok, val = self._check_condition(cond, state, price)
            results.append(ok)
            values.update(val)
        matched = all(results) if rule.logic_operator == "AND" else any(results)
        return matched, values

    def _check_condition(self, cond: Condition, state: IndicatorState, price: float):
        if cond.type == ConditionType.PRICE:
            actual, key = price, "price"
        else:
            key = cond.indicator_name
            if cond.indicator_name == "EMA":
                actual = state.ema(cond.indicator_period)
            else:
                actual = state.rsi(cond.indicator_period or 14)

        if actual is None:
            return False, {}

        if cond.comparator == Comparator.GT:
            return actual > cond.value, {key: actual}
        if cond.comparator == Comparator.LT:
            return actual < cond.value, {key: actual}
        if cond.comparator == Comparator.BETWEEN:
            lo, hi = cond.value
            return lo <= actual <= hi, {key: actual}
        return False, {key: actual}

    def _cancel_linked(self, rule: Rule):
        """OCO-style: an entry/SL/target firing cancels its sibling rules."""
        for linked_id in rule.linked_rule_ids:
            linked = self.rules.get(linked_id)
            if linked and linked.status == "active":
                linked.status = "cancelled"


    def status_snapshot(self, instrument: str | None = None) -> dict:
        """Deterministic, no-LLM snapshot of how close each active rule is
        to firing, computed straight from current indicator state. This is
        what powers the live 'why hasn't this fired yet' view -- it's cheap
        arithmetic, so it's safe to recompute on every poll cycle, unlike
        an LLM call which would be both slow and needless here."""
        snapshot = {}
        for rule in self.rules.values():
            if rule.status != "active":
                continue
            if instrument and rule.instrument != instrument:
                continue
            state = self.states.get(rule.instrument)
            if state is None:
                continue
            cond_statuses = [self._condition_gap(cond, state) for cond in rule.conditions]
            snapshot[rule.rule_id] = {
                "instrument": rule.instrument,
                "condition_type": rule.condition_type,
                "logic_operator": rule.logic_operator,
                "conditions": cond_statuses,
                "all_met": (all(c["met"] for c in cond_statuses) if rule.logic_operator == "AND"
                            else any(c["met"] for c in cond_statuses)),
            }
        return snapshot

    def _condition_gap(self, cond: Condition, state: IndicatorState) -> dict:
        label = cond.indicator_name or "price"
        target_desc = (f"{label} between {cond.value[0]} and {cond.value[1]}"
                        if cond.comparator == Comparator.BETWEEN else
                        f"{label} {cond.comparator.value} {cond.value}")

        if cond.type == ConditionType.PRICE:
            current = state.last_price
        elif cond.indicator_name == "EMA":
            current = state.ema(cond.indicator_period)
        else:
            current = state.rsi(cond.indicator_period or 14)

        if current is None:
            return {"met": False, "current": None, "target": target_desc, "distance": None, "indicator": label}

        if cond.comparator in (Comparator.GT, Comparator.GTE):
            met, distance = current > cond.value, max(0, cond.value - current)
        elif cond.comparator in (Comparator.LT, Comparator.LTE):
            met, distance = current < cond.value, max(0, current - cond.value)
        elif cond.comparator == Comparator.BETWEEN:
            lo, hi = cond.value
            met = lo <= current <= hi
            distance = 0 if met else ((lo - current) if current < lo else (current - hi))
        else:
            met, distance = False, None

        return {"met": met, "current": round(current, 4), "target": target_desc,
                "distance": round(distance, 4) if distance is not None else None, "indicator": label}


if __name__ == "__main__":
    def handle_trigger(event: TriggerEvent):
        print(f"[TRIGGER] {event.instrument} / {event.rule.condition_type} "
              f"matched with {event.matched_values}")

    engine = RuleEngine(on_trigger=handle_trigger)
    buy_rule = Rule(
        instrument="AAPL",
        condition_type="entry_buy",
        conditions=[
            Condition(ConditionType.PRICE, Comparator.GT, 210),
            Condition(ConditionType.INDICATOR, Comparator.BETWEEN, (40, 70),
                      indicator_name="RSI", indicator_period=14),
        ],
        raw_input="Buy AAPL if price breaks above 210 and RSI is between 40-70",
    )
    engine.add_rule(buy_rule)

    prices = [205, 206, 205.5, 207, 206.2, 208, 207.1, 209, 208.3, 209.8]  # stops below the 210 threshold
    for price in prices:
        engine.on_tick("AAPL", price=price, volume=1_000_000)

    print("\nlive status (not yet triggered):")
    for rule_id, status in engine.status_snapshot("AAPL").items():
        print(f"  {status['instrument']} {status['condition_type']} -- all_met={status['all_met']}")
        for c in status["conditions"]:
            print(f"    {c['target']}: current={c['current']}, met={c['met']}, distance={c['distance']}")