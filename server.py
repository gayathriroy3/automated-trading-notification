"""
HTTP adapter for the React dashboard.

This file is the ONLY new backend code. It imports the existing
orchestrator / rule engine / database / market-data modules exactly as
app.py (the Streamlit UI) did, and exposes them over REST + one
Server-Sent-Events stream so a separate frontend process can talk to them.
No file under agents/ or backend/ is modified.

Run with:  uvicorn server:app --reload --port 8000
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
from dataclasses import asdict
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from agents.orchestrator import AgentError, Orchestrator
from backend.database.db import (
    DatabaseError, init_db, save_rule, get_active_rules, mark_rule_status,
    save_notification, get_notifications, update_notification_action,
    default_strategy_key, get_active_rule_for_strategy, get_rule_by_id,
    get_rule_history, save_rule_status, get_rule_statuses,
)
from backend.rule_engine.rule_engine import Rule, Condition, ConditionType, Comparator, RuleEngine
from backend.market_data.yahoo_feed import YahooFeed, verify_ticker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

init_db()
orchestrator = Orchestrator()

app = FastAPI(
    title="Trade Discipline API",
    version="0.1.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Same rule (de)serialization app.py used, unmodified in logic.
# ---------------------------------------------------------------------------
def dict_to_rule(d: dict, raw_text: str, rule_id: str | None = None) -> Rule:
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


# ---------------------------------------------------------------------------
# Background poller -- process-global instead of Streamlit session_state,
# since a stateless HTTP API has no per-session slot to hold it in. Same
# run_poller body as app.py.
# ---------------------------------------------------------------------------
_poller_lock = threading.Lock()
_poller_stop_event: Optional[threading.Event] = None
_poller_symbols: list[str] = []


def run_poller(symbols: list[str], stop_event: threading.Event, poll_seconds: int = 60):
    feed = YahooFeed(symbols)
    poller_orchestrator = Orchestrator()

    def on_trigger(event):
        try:
            reason = poller_orchestrator.explainer.explain(
                event.instrument, event.rule.condition_type, event.matched_values
            )
            save_notification(
                instrument=event.instrument, condition_type=event.rule.condition_type,
                matched_values=event.matched_values, reason=reason,
                triggered_at=event.matched_at, rule_id=event.rule.rule_id, caution=None,
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
            for rule_id, status in engine.status_snapshot().items():
                save_rule_status(rule_id, status)
        except Exception:
            logger.exception("Poller loop iteration failed -- continuing")
        stop_event.wait(poll_seconds)
    logger.info("Poller stopped.")


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------
class ParseRequest(BaseModel):
    raw_text: str


class SaveRuleRequest(BaseModel):
    rule: dict
    raw_text: str
    strategy_key: Optional[str] = None


class ActionRequest(BaseModel):
    action: str


# ---------------------------------------------------------------------------
# Startup / config
# ---------------------------------------------------------------------------
@app.get("/api/config/status")
def config_status():
    try:
        from agents.llm.factory import load_llm_config
        cfg = load_llm_config()
        api_key_env = cfg.get("api_key_env", "")
        key_set = bool(api_key_env and os.environ.get(api_key_env))
        return {
            "provider": cfg.get("provider"),
            "api_key_env": api_key_env,
            "key_set": key_set,
            "warning": None if key_set else (
                f"config/llm_config.yaml selects provider '{cfg.get('provider')}' but "
                f"'{api_key_env}' is not set. Parser/validator/explainer/news-sentiment "
                "agents need it -- History and live status still work without it."
            ),
        }
    except AgentError as exc:
        return {"provider": None, "api_key_env": None, "key_set": False, "warning": f"LLM config problem: {exc}"}


# ---------------------------------------------------------------------------
# Tab 1 -- conditions
# ---------------------------------------------------------------------------
@app.post("/api/conditions/parse")
def parse_condition(req: ParseRequest):
    if not req.raw_text.strip():
        raise HTTPException(400, "Condition text is required.")
    try:
        existing = [json.loads(r["rule_json"]) for r in get_active_rules()]
        result = orchestrator.process_new_condition(req.raw_text, existing)
    except AgentError as exc:
        raise HTTPException(422, f"Couldn't process that condition: {exc}")

    payload = {
        "rule": result.rule,
        "schema_problems": result.schema_problems,
        "conflicts": result.conflicts,
        "is_valid": result.is_valid,
        "issues": result.issues,
        "approved": result.approved,
        "ticker_check": None,
        "existing_version": None,
    }
    if result.is_valid:
        ok, msg = verify_ticker(result.rule["instrument"])
        payload["ticker_check"] = {"ok": ok, "message": msg}
        if ok:
            strategy_key = default_strategy_key(result.rule["instrument"], result.rule["condition_type"])
            payload["strategy_key"] = strategy_key
            existing_version = get_active_rule_for_strategy(strategy_key)
            if existing_version:
                payload["existing_version"] = {
                    "version": existing_version["version"],
                    "raw_input": existing_version["raw_input"],
                }
    return payload


@app.post("/api/conditions/save")
def save_condition(req: SaveRuleRequest):
    try:
        rule_id = save_rule(req.rule, req.raw_text, strategy_key=req.strategy_key)
    except DatabaseError as exc:
        raise HTTPException(400, f"Couldn't save rule: {exc}")
    return {"rule_id": rule_id}


@app.get("/api/rules/active")
def list_active_rules():
    rows = get_active_rules()
    if rows is None:
        return []
    return [
        {
            "rule_id": r["rule_id"],
            "strategy_key": r["strategy_key"],
            "version": r["version"],
            "instrument": r["instrument"],
            "rule": json.loads(r["rule_json"]),
            "raw_input": r["raw_input"],
            "status": r["status"],
            "created_at": r["created_at"],
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Tab 2 -- live monitor
# ---------------------------------------------------------------------------
@app.post("/api/monitor/start")
def start_monitor():
    global _poller_stop_event, _poller_symbols
    with _poller_lock:
        if _poller_stop_event is not None:
            raise HTTPException(409, "Monitoring is already running.")
        active = get_active_rules()
        symbols = sorted({json.loads(r["rule_json"])["instrument"] for r in active})
        if not symbols:
            raise HTTPException(400, "No active rules yet -- add one first.")
        stop_event = threading.Event()
        _poller_stop_event = stop_event
        _poller_symbols = symbols
        threading.Thread(target=run_poller, args=(symbols, stop_event), daemon=True).start()
    return {"running": True, "symbols": symbols}


@app.post("/api/monitor/stop")
def stop_monitor():
    global _poller_stop_event, _poller_symbols
    with _poller_lock:
        if _poller_stop_event is None:
            raise HTTPException(409, "Monitoring is not running.")
        _poller_stop_event.set()
        _poller_stop_event = None
        _poller_symbols = []
    return {"running": False}


@app.get("/api/monitor/status")
def monitor_status():
    with _poller_lock:
        running = _poller_stop_event is not None
        symbols = list(_poller_symbols)

    active = get_active_rules()
    statuses = get_rule_statuses([r["rule_id"] for r in active]) if running else {}

    rules_out = []
    for row in active:
        rule = json.loads(row["rule_json"])
        status = statuses.get(row["rule_id"])
        rules_out.append({
            "rule_id": row["rule_id"],
            "instrument": rule["instrument"],
            "raw_input": row["raw_input"],
            "version": row["version"],
            "status": status,
        })

    return {"running": running, "symbols": symbols, "active_count": len(active), "rules": rules_out}


# ---------------------------------------------------------------------------
# Tab 3 -- history
# ---------------------------------------------------------------------------
@app.get("/api/notifications")
def list_notifications(date: Optional[str] = None, order: str = "desc"):
    date_filter = None
    if date:
        from datetime import date as date_cls
        date_filter = date_cls.fromisoformat(date)
    rows = get_notifications(date_filter=date_filter, ascending=(order == "asc"))

    out = []
    for row in rows:
        rule = get_rule_by_id(row["rule_id"])
        history = get_rule_history(rule["strategy_key"]) if rule else []
        out.append({
            **row,
            "matched_values": json.loads(row["matched_values"]) if row.get("matched_values") else {},
            "rule": {
                "version": rule["version"],
                "raw_input": rule["raw_input"],
                "strategy_key": rule["strategy_key"],
            } if rule else None,
            "version_history": [
                {"version": v["version"], "status": v["status"], "raw_input": v["raw_input"],
                 "is_this_one": v["rule_id"] == row["rule_id"] if rule and v["rule_id"] == rule["rule_id"] else False}
                for v in history
            ],
        })
    return out


@app.post("/api/notifications/{notif_id}/action")
def submit_action(notif_id: str, req: ActionRequest):
    if req.action not in ("took_trade", "skipped"):
        raise HTTPException(400, "action must be 'took_trade' or 'skipped'.")
    try:
        update_notification_action(notif_id, req.action)
    except DatabaseError as exc:
        raise HTTPException(400, f"Couldn't save outcome: {exc}")
    return {"ok": True}