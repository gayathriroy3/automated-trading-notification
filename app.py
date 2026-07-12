"""
Streamlit UI for the trade discipline system.

Four tabs:
  1. Set conditions   -- plain English text box. A new condition for the
                          same instrument+type replaces the old one as a
                          new strategy version (not a silent overwrite --
                          the trader sees "this replaces v3" before saving).
                          Validation order: schema check -> deterministic
                          conflict check (hard block, provable) -> ticker
                          verification (hard block) -> semantic LLM check
                          (soft warning, overridable).
  2. Live monitor      -- starts/stops the background polling thread.
  3. Why not yet        -- live, continuously-updating gap between current
                          market state and each active rule's conditions,
                          computed deterministically every poll cycle.
  4. History            -- every notification, sortable/filterable by date,
                          each one showing exactly which strategy version
                          fired it and any news-sentiment caution attached.
"""

from __future__ import annotations
import json
import logging
import os
import threading

import pandas as pd
import streamlit as st

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from agents.orchestrator import AgentError, Orchestrator, sentiment_contradicts_direction
from backend.database.db import (
    DatabaseError, init_db, save_rule, get_active_rules, mark_rule_status,
    save_notification, get_notifications, update_notification_action,
    default_strategy_key, get_active_rule_for_strategy, get_rule_by_id,
    get_rule_history, save_rule_status, get_rule_statuses,
)
from backend.rule_engine.rule_engine import Rule, Condition, ConditionType, Comparator, RuleEngine
from backend.market_data.yahoo_feed import YahooFeed, verify_ticker, fetch_recent_news

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

st.set_page_config(page_title="Trade Discipline Agent", layout="wide")
init_db()

for key, default in [
    ("poller_stop_event", None), ("orchestrator", None),
    ("pending_result", None), ("ticker_check", None),
]:
    if key not in st.session_state:
        st.session_state[key] = default
if st.session_state.orchestrator is None:
    st.session_state.orchestrator = Orchestrator()

if not os.environ.get("GEMINI_API_KEY"):
    st.warning(
        "GEMINI_API_KEY is not set. The condition parser, validator, "
        "explanation, and news-sentiment agents all need it -- the History "
        "and Why not yet tabs will still work without it."
    )


def dict_to_rule(d: dict, raw_text: str, rule_id: str | None = None) -> Rule:
    """rule_id must be passed through from the DB row -- without it, Rule's
    default factory mints a NEW random id, which silently breaks every
    lookup that joins back to the rules table (status snapshots, mark
    triggered, and the notification's "which version fired this" trace)."""
    conditions = [
        Condition(
            type=ConditionType(c["type"]),
            comparator=Comparator(c["comparator"]),
            value=tuple(c["value"]) if isinstance(c["value"], list) else c["value"],
            indicator_name=c.get("indicator_name"),
            indicator_period=c.get("indicator_period"),
        )
        for c in d["conditions"]
    ]
    kwargs = dict(
        instrument=d["instrument"], condition_type=d["condition_type"],
        conditions=conditions, logic_operator=d.get("logic_operator", "AND"),
        raw_input=raw_text,
    )
    if rule_id:
        kwargs["rule_id"] = rule_id
    return Rule(**kwargs)


def run_poller(symbols: list[str], stop_event: threading.Event, poll_seconds: int = 60):
    """Background thread. Doesn't touch st.session_state (not reliably
    thread-safe across reruns) -- only talks to the DB and a plain Event.
    Every stage is wrapped so one bad rule or one failed call can't kill
    the whole loop silently."""
    feed = YahooFeed(symbols)
    orchestrator = Orchestrator()

    def on_trigger(event):
        try:
            reason = orchestrator.explainer.explain(
                event.instrument, event.rule.condition_type, event.matched_values
            )

            caution = None
            if event.rule.condition_type in {"entry_buy", "entry_sell"}:
                headlines = fetch_recent_news(event.instrument)
                sentiment = orchestrator.news_agent.analyze(event.instrument, headlines)
                if sentiment_contradicts_direction(event.rule.condition_type, sentiment["sentiment"]):
                    caution = (f"Trade setup satisfied, but recent news sentiment is "
                               f"{sentiment['sentiment'].replace('_', ' ')}: {sentiment['summary']} "
                               f"Proceed carefully.")

            save_notification(
                instrument=event.instrument, condition_type=event.rule.condition_type,
                matched_values=event.matched_values, reason=reason,
                triggered_at=event.matched_at, rule_id=event.rule.rule_id, caution=caution,
            )
            mark_rule_status(event.rule.rule_id, "triggered")
        except Exception:
            logger.exception("Failed to handle trigger for %s", event.instrument)

    engine = RuleEngine(on_trigger=on_trigger)
    for row in get_active_rules():
        try:
            engine.add_rule(dict_to_rule(json.loads(row["rule_json"]), row["raw_input"], rule_id=row["rule_id"]))
        except Exception:
            logger.exception("Skipping malformed stored rule %s", row.get("rule_id"))

    logger.info("Poller started for symbols: %s", symbols)
    while not stop_event.is_set():
        try:
            for bar in feed.poll():
                engine.on_tick(bar.symbol, price=bar.close, volume=bar.volume)
            # Deterministic, cheap -- safe to recompute every cycle, unlike
            # an LLM call which would be both slow and unnecessary here.
            for rule_id, status in engine.status_snapshot().items():
                save_rule_status(rule_id, status)
        except Exception:
            logger.exception("Poller loop iteration failed -- continuing")
        stop_event.wait(poll_seconds)
    logger.info("Poller stopped.")


tab_setup, tab_monitor, tab_pending, tab_history = st.tabs(
    ["Set conditions", "Live monitor", "Why not yet", "History"]
)

# ---------------------------------------------------------------------------
# Tab 1 -- plain English condition input, with versioning + full validation
# ---------------------------------------------------------------------------
with tab_setup:
    st.subheader("Describe your trade condition in plain English")
    raw_text = st.text_area(
        "Condition",
        placeholder="Buy Nifty above 25000",
        height=100,
        label_visibility="collapsed",
    )

    if st.button("Parse & validate", type="primary", disabled=not raw_text.strip()):
        st.session_state.pending_result = None
        st.session_state.ticker_check = None
        try:
            with st.spinner("Parsing condition..."):
                existing = [json.loads(r["rule_json"]) for r in get_active_rules()]
                result = st.session_state.orchestrator.process_new_condition(raw_text, existing)
            st.session_state.pending_result = result
            if result.is_valid:
                with st.spinner(f"Verifying '{result.rule['instrument']}' on Yahoo Finance..."):
                    st.session_state.ticker_check = verify_ticker(result.rule["instrument"])
        except AgentError as exc:
            st.error(f"Couldn't process that condition: {exc}")

    result = st.session_state.pending_result
    if result is not None:
        st.markdown("**Parsed rule**")
        st.json(result.rule)

        if result.schema_problems:
            st.error("This doesn't look like a valid, complete trade condition:")
            for p in result.schema_problems:
                st.write(f"- {p}")
            st.caption("Nothing was saved. Rephrase with a specific instrument, condition, and threshold.")
        elif result.conflicts:
            st.error("This rule contradicts itself or an existing linked rule:")
            for c in result.conflicts:
                st.write(f"- {c}")
            st.caption("Nothing was saved. This isn't a judgment call -- the logic is provably inconsistent.")
        else:
            ticker_ok, ticker_msg = st.session_state.ticker_check or (False, "Not checked yet.")
            if not ticker_ok:
                st.error(f"Ticker check failed: {ticker_msg}")
                st.caption("Nothing was saved -- fix the ticker and re-parse.")
            else:
                st.success(f"'{result.rule['instrument']}' verified on Yahoo Finance.")

                strategy_key = default_strategy_key(result.rule["instrument"], result.rule["condition_type"])
                existing_version = get_active_rule_for_strategy(strategy_key)
                if existing_version:
                    st.info(
                        f"This will replace your active **v{existing_version['version']}** rule "
                        f"for {strategy_key} (\"{existing_version['raw_input']}\") -- "
                        f"this becomes **v{existing_version['version'] + 1}**."
                    )

                override = True
                if result.issues:
                    st.warning("Validation agent flagged: " + "; ".join(result.issues))
                    override = st.checkbox("I understand the flagged issue(s) and want to save anyway")
                else:
                    st.success("No conflicts found against your existing active rules.")

                col1, col2 = st.columns(2)
                if col1.button("Confirm & save", disabled=not override):
                    try:
                        save_rule(result.rule, raw_text, strategy_key=strategy_key)
                        st.success(f"Saved rule for {result.rule['instrument']}.")
                        st.session_state.pending_result = None
                        st.session_state.ticker_check = None
                        st.rerun()
                    except DatabaseError as exc:
                        st.error(f"Couldn't save rule: {exc}")
                if col2.button("Discard"):
                    st.session_state.pending_result = None
                    st.session_state.ticker_check = None
                    st.rerun()

# ---------------------------------------------------------------------------
# Tab 2 -- live monitor
# ---------------------------------------------------------------------------
with tab_monitor:
    st.subheader("Live monitoring")
    active = get_active_rules()
    symbols = sorted({json.loads(r["rule_json"])["instrument"] for r in active})

    if symbols:
        st.write(f"{len(active)} active rule(s) across: {', '.join(symbols)}")
    else:
        st.info("No active rules yet -- add one in the 'Set conditions' tab first.")

    is_running = st.session_state.poller_stop_event is not None
    col1, col2 = st.columns(2)
    if col1.button("Start monitoring", disabled=is_running or not symbols):
        stop_event = threading.Event()
        st.session_state.poller_stop_event = stop_event
        threading.Thread(target=run_poller, args=(symbols, stop_event), daemon=True).start()
        st.rerun()
    if col2.button("Stop monitoring", disabled=not is_running):
        st.session_state.poller_stop_event.set()
        st.session_state.poller_stop_event = None
        st.rerun()
    if is_running:
        st.success("Poller running in the background.")  
    else:
        st.caption("Monitoring is stopped.")

# ---------------------------------------------------------------------------
# Tab 3 -- "why not yet": live, continuously-updating gap to each rule
# ---------------------------------------------------------------------------
with tab_pending:
    st.subheader("Why hasn't this fired yet?")
    st.caption(
        "Updated by the background poller every cycle. This is plain arithmetic against "
        "live market data, not an LLM call -- refresh to see the latest snapshot."
    )
    if st.button("Refresh"):
        st.rerun()

    active = get_active_rules()
    statuses = get_rule_statuses([r["rule_id"] for r in active])

    if not active:
        st.info("No active rules to track.")
    elif not statuses:
        st.info("No status yet -- start monitoring in the 'Live monitor' tab.")
    else:
        for rule in active:
            status = statuses.get(rule["rule_id"])
            if not status:
                continue
            header = f"{status['instrument']} — {status['condition_type']} (v{rule['version']})"
            with st.expander(header, expanded=not status["all_met"]):
                for c in status["conditions"]:
                    icon = "✅" if c["met"] else "⏳"
                    if c["current"] is None:
                        st.write(f"{icon} {c['target']} -- waiting on first price data")
                    elif c["met"]:
                        st.write(f"{icon} {c['target']} -- currently {c['current']} (met)")
                    else:
                        st.write(f"{icon} {c['target']} -- currently {c['current']}, "
                                 f"{c['distance']} away")

# ---------------------------------------------------------------------------
# Tab 4 -- notification history, with version + news-sentiment caution
# ---------------------------------------------------------------------------
with tab_history:
    st.subheader("Notification history")

    col1, col2 = st.columns([1, 1])
    use_date_filter = col1.checkbox("Filter by date")
    date_filter = col1.date_input("Date") if use_date_filter else None
    sort_order = col2.selectbox("Sort", ["Newest first", "Oldest first"])

    rows = get_notifications(date_filter=date_filter, ascending=(sort_order == "Oldest first"))

    if not rows:
        st.info("No notifications yet.")
    else:
        for row in rows:
            rule = get_rule_by_id(row["rule_id"])
            version_label = f"v{rule['version']}" if rule else "unknown version"
            when = pd.to_datetime(row["triggered_at"], unit="s").strftime("%Y-%m-%d %H:%M")

            with st.container(border=True):
                st.markdown(f"**{row['instrument']} — {row['condition_type']}** · {when} · {version_label}")
                st.write(row["reason"])
                if row.get("caution"):
                    st.warning(row["caution"])
                if rule:
                    st.caption(f"Triggered by: \"{rule['raw_input']}\"")
                    with st.expander("Version history for this strategy"):
                        for v in get_rule_history(rule["strategy_key"]):
                            marker = " (this one)" if v["rule_id"] == rule["rule_id"] else ""
                            st.write(f"v{v['version']} [{v['status']}]: \"{v['raw_input']}\"{marker}")

                action = st.selectbox(
                    "Action", ["", "took_trade", "skipped"],
                    index=["", "took_trade", "skipped"].index(row["action"]),
                    key=f"action_{row['id']}",
                )
                if action != row["action"]:
                    try:
                        update_notification_action(row["id"], action)
                        st.rerun()
                    except DatabaseError as exc:
                        st.error(f"Couldn't update action: {exc}")