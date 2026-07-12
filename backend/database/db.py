"""
SQLite persistence.

Adds strategy versioning on top of the previous schema: rules are grouped
by strategy_key (instrument + condition_type by default), and replacing an
active rule doesn't delete it -- it's marked 'superseded' and the new rule
gets version = old.version + 1. This is what answers "why did I get this
notification" months later: the notification stores the exact rule_id that
fired, and that row never changes underneath it.
"""

from __future__ import annotations
import json
import logging
import sqlite3
import time
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent / "trade_discipline.db"


class DatabaseError(Exception):
    """Raised on invalid input or a SQLite failure."""


@contextmanager
def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except sqlite3.Error as exc:
        conn.rollback()
        logger.error("SQLite error: %s", exc)
        raise DatabaseError(str(exc)) from exc
    finally:
        conn.close()


def init_db():
    with _conn() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS rules (
            rule_id TEXT PRIMARY KEY,
            strategy_key TEXT NOT NULL,
            version INTEGER NOT NULL,
            instrument TEXT NOT NULL,
            rule_json TEXT NOT NULL,
            raw_input TEXT NOT NULL,
            status TEXT NOT NULL,
            superseded_by TEXT,
            created_at REAL NOT NULL
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS notifications (
            id TEXT PRIMARY KEY,
            rule_id TEXT,
            instrument TEXT NOT NULL,
            condition_type TEXT NOT NULL,
            matched_values TEXT NOT NULL,
            reason TEXT NOT NULL,
            caution TEXT,
            triggered_at REAL NOT NULL,
            action TEXT NOT NULL DEFAULT ''
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS rule_status (
            rule_id TEXT PRIMARY KEY,
            status_json TEXT NOT NULL,
            updated_at REAL NOT NULL
        )""")


def default_strategy_key(instrument: str, condition_type: str) -> str:
    return f"{instrument.upper()}:{condition_type}"


def get_active_rule_for_strategy(strategy_key: str) -> dict | None:
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM rules WHERE strategy_key = ? AND status = 'active'", (strategy_key,)
        ).fetchone()
    return dict(row) if row else None


def save_rule(rule_dict: dict, raw_input: str, strategy_key: str | None = None) -> str:
    instrument = rule_dict.get("instrument")
    conditions = rule_dict.get("conditions")
    condition_type = rule_dict.get("condition_type")
    if not instrument or not isinstance(instrument, str):
        raise DatabaseError("Refusing to save a rule with no instrument.")
    if not conditions:
        raise DatabaseError("Refusing to save a rule with no conditions.")

    strategy_key = strategy_key or default_strategy_key(instrument, condition_type)
    rule_id = str(uuid.uuid4())

    with _conn() as conn:
        prev = conn.execute(
            "SELECT rule_id, version FROM rules WHERE strategy_key = ? AND status = 'active'",
            (strategy_key,),
        ).fetchone()
        version = (prev["version"] + 1) if prev else 1

        conn.execute(
            "INSERT INTO rules VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (rule_id, strategy_key, version, instrument, json.dumps(rule_dict),
             raw_input, "active", None, time.time()),
        )
        if prev:
            conn.execute(
                "UPDATE rules SET status = 'superseded', superseded_by = ? WHERE rule_id = ?",
                (rule_id, prev["rule_id"]),
            )
    return rule_id


def get_active_rules() -> list[dict]:
    with _conn() as conn:
        rows = conn.execute("SELECT * FROM rules WHERE status = 'active'").fetchall()
    return [dict(r) for r in rows]


def get_rule_by_id(rule_id: str) -> dict | None:
    if not rule_id:
        return None
    with _conn() as conn:
        row = conn.execute("SELECT * FROM rules WHERE rule_id = ?", (rule_id,)).fetchone()
    return dict(row) if row else None


def get_rule_history(strategy_key: str) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM rules WHERE strategy_key = ? ORDER BY version ASC", (strategy_key,)
        ).fetchall()
    return [dict(r) for r in rows]


def mark_rule_status(rule_id: str, status: str):
    with _conn() as conn:
        conn.execute("UPDATE rules SET status = ? WHERE rule_id = ?", (status, rule_id))


def save_notification(instrument: str, condition_type: str, matched_values: dict,
                       reason: str, triggered_at: float, rule_id: str = "", caution: str | None = None):
    with _conn() as conn:
        conn.execute(
            "INSERT INTO notifications VALUES (?, ?, ?, ?, ?, ?, ?, ?, '')",
            (str(uuid.uuid4()), rule_id, instrument, condition_type,
             json.dumps(matched_values), reason, caution, triggered_at),
        )


def get_notifications(date_filter=None, ascending: bool = False) -> list[dict]:
    order = "ASC" if ascending else "DESC"
    with _conn() as conn:
        rows = conn.execute(f"SELECT * FROM notifications ORDER BY triggered_at {order}").fetchall()
    result = [dict(r) for r in rows]
    if date_filter:
        target = date_filter.isoformat() if hasattr(date_filter, "isoformat") else str(date_filter)
        result = [r for r in result
                  if datetime.fromtimestamp(r["triggered_at"]).date().isoformat() == target]
    return result


def update_notification_action(notif_id: str, action: str):
    with _conn() as conn:
        conn.execute("UPDATE notifications SET action = ? WHERE id = ?", (action, notif_id))


def save_rule_status(rule_id: str, status_dict: dict):
    with _conn() as conn:
        conn.execute(
            "INSERT INTO rule_status VALUES (?, ?, ?) "
            "ON CONFLICT(rule_id) DO UPDATE SET status_json = excluded.status_json, "
            "updated_at = excluded.updated_at",
            (rule_id, json.dumps(status_dict), time.time()),
        )


def get_rule_statuses(rule_ids: list[str]) -> dict[str, dict]:
    if not rule_ids:
        return {}
    placeholders = ",".join("?" for _ in rule_ids)
    with _conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM rule_status WHERE rule_id IN ({placeholders})", rule_ids
        ).fetchall()
    return {r["rule_id"]: {**json.loads(r["status_json"]), "updated_at": r["updated_at"]} for r in rows}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    init_db()

    r1 = save_rule({"instrument": "NIFTY", "condition_type": "entry_buy",
                     "conditions": [{"type": "price", "comparator": ">", "value": 25000}]},
                    raw_input="Buy Nifty above 25000")
    print("v1:", get_rule_by_id(r1)["version"])

    r2 = save_rule({"instrument": "NIFTY", "condition_type": "entry_buy",
                     "conditions": [{"type": "price", "comparator": ">", "value": 25100}]},
                    raw_input="Buy above 25100")
    print("v2:", get_rule_by_id(r2)["version"], "-- v1 status now:", get_rule_by_id(r1)["status"])

    print("history:", [(r["version"], r["raw_input"], r["status"])
                        for r in get_rule_history(default_strategy_key("NIFTY", "entry_buy"))])