"""Cross-session AgentState persistence.

SQLite-backed store that saves AgentState snapshots on each tool-call round
and provides lookup so setup_node can load relevant context from prior sessions.
"""

import json
import logging
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

from core.storage import USER_DB

logger = logging.getLogger(__name__)

_DB_PATH: Path | None = None
_CONN: sqlite3.Connection | None = None


def _get_db_path() -> Path:
    global _DB_PATH
    if _DB_PATH is None:
        _DB_PATH = Path(USER_DB)
        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return _DB_PATH


def _get_conn() -> sqlite3.Connection:
    global _CONN
    if _CONN is None:
        _CONN = sqlite3.connect(str(_get_db_path()))
        _CONN.execute("PRAGMA journal_mode=WAL")
        _CONN.execute("PRAGMA synchronous=NORMAL")
        _init_schema(_CONN)
    return _CONN


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS agent_state_snapshots (
            snapshot_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            run_id TEXT NOT NULL,
            round_num INTEGER NOT NULL,
            state_json TEXT NOT NULL,
            summary TEXT NOT NULL DEFAULT '',
            created_at REAL NOT NULL
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_snapshots_session
        ON agent_state_snapshots(session_id, created_at DESC)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_snapshots_run
        ON agent_state_snapshots(run_id, round_num DESC)
    """)
    conn.commit()


def _make_summary(state: Any) -> str:
    """Build a one-line summary from AgentState for context injection."""
    parts = []
    messages = getattr(state, "messages", [])
    last_user = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            last_user = m.get("content", "")[:200]
            break
    if last_user:
        parts.append(f"user: {last_user}")
    tool_events = getattr(state, "tool_events", [])
    if tool_events:
        last_tool = tool_events[-1]
        tool_name = last_tool.get("tool", "")
        tool_out = str(last_tool.get("output", ""))[:150]
        parts.append(f"tool: {tool_name} => {tool_out}")
    total_calls = getattr(state, "total_tool_calls", 0)
    round_num = getattr(state, "round_num", 0)
    parts.append(f"rounds={round_num} calls={total_calls}")
    return " | ".join(parts)


def save_snapshot(state: Any) -> str:
    """Persist an AgentState snapshot to SQLite. Returns snapshot_id."""
    sid = uuid.uuid4().hex[:12]
    state_dict = getattr(state, "to_dict", lambda: {})()
    if not state_dict:
        return ""
    state_json = json.dumps(state_dict, default=str)
    summary = _make_summary(state)
    session_id = getattr(state, "session_id", "") or ""
    run_id = getattr(state, "run_id", "") or ""
    round_num = getattr(state, "round_num", 0)
    created_at = time.time()
    try:
        conn = _get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO agent_state_snapshots "
            "(snapshot_id, session_id, run_id, round_num, state_json, summary, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (sid, session_id, run_id, round_num, state_json, summary, created_at),
        )
        conn.commit()
    except Exception as e:
        logger.warning("save_snapshot failed: %s", e)
        return ""
    return sid


def get_recent_snapshots(
    session_id: str | None = None,
    limit: int = 10,
    exclude_session: str | None = None,
) -> list[dict]:
    """Return recent snapshots, optionally excluding the current session."""
    conn = _get_conn()
    if exclude_session:
        rows = conn.execute(
            "SELECT session_id, run_id, round_num, summary, created_at "
            "FROM agent_state_snapshots "
            "WHERE session_id != ? "
            "ORDER BY created_at DESC LIMIT ?",
            (exclude_session, limit),
        ).fetchall()
    elif session_id:
        rows = conn.execute(
            "SELECT session_id, run_id, round_num, summary, created_at "
            "FROM agent_state_snapshots "
            "WHERE session_id = ? "
            "ORDER BY created_at DESC LIMIT ?",
            (session_id, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT session_id, run_id, round_num, summary, created_at "
            "FROM agent_state_snapshots "
            "ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [
        {
            "session_id": r[0],
            "run_id": r[1],
            "round_num": r[2],
            "summary": r[3],
            "created_at": r[4],
        }
        for r in rows
    ]


def close() -> None:
    global _CONN
    if _CONN is not None:
        try:
            _CONN.close()
        except Exception:
            pass
        _CONN = None
