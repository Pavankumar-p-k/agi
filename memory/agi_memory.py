from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any


DB_PATH = Path("data/jarvis_agi.db")


class AGIMemory:
    """
    Separate AGI memory store:
    events, decisions, goals, patterns, reflections, solver runs.
    """

    def __init__(self):
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self._loop_count = 0

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS agi_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    type TEXT,
                    content TEXT,
                    intent TEXT,
                    emotion TEXT,
                    user_id TEXT,
                    hour INTEGER,
                    day INTEGER,
                    timestamp REAL
                );

                CREATE TABLE IF NOT EXISTS agi_decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    action TEXT,
                    tool TEXT,
                    reasoning TEXT,
                    confidence REAL,
                    success INTEGER,
                    latency_ms INTEGER,
                    state_hour INTEGER,
                    state_mood TEXT,
                    timestamp REAL
                );

                CREATE TABLE IF NOT EXISTS agi_goals (
                    id TEXT PRIMARY KEY,
                    description TEXT,
                    steps TEXT,
                    current_step INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'active',
                    context TEXT,
                    created_at REAL
                );

                CREATE TABLE IF NOT EXISTS agi_patterns (
                    key TEXT PRIMARY KEY,
                    data TEXT,
                    updated_at REAL
                );

                CREATE TABLE IF NOT EXISTS agi_reflections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    data TEXT,
                    timestamp REAL
                );

                CREATE TABLE IF NOT EXISTS agi_solve_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    problem TEXT,
                    steps_total INTEGER,
                    steps_done INTEGER,
                    success INTEGER,
                    duration_s REAL,
                    timestamp REAL
                );

                CREATE TABLE IF NOT EXISTS agi_habits (
                    key TEXT PRIMARY KEY,
                    data TEXT,
                    updated_at REAL
                );

                CREATE INDEX IF NOT EXISTS idx_agi_events_ts
                    ON agi_events(timestamp DESC);
                CREATE INDEX IF NOT EXISTS idx_agi_decisions_ts
                    ON agi_decisions(timestamp DESC);
                """
            )

    async def save_event(self, event: dict[str, Any]) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO agi_events (type,content,intent,emotion,user_id,hour,day,timestamp) VALUES (?,?,?,?,?,?,?,?)",
                (
                    event.get("type", ""),
                    event.get("content", ""),
                    event.get("intent", ""),
                    event.get("emotion", ""),
                    event.get("user_id", "pavan"),
                    int(event.get("hour", 0)),
                    int(event.get("day", 0)),
                    float(event.get("timestamp", time.time())),
                ),
            )

    async def save_decision(self, decision: dict[str, Any]) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO agi_decisions (action,tool,reasoning,confidence,success,latency_ms,state_hour,state_mood,timestamp) VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    decision.get("action", ""),
                    decision.get("tool", ""),
                    decision.get("reasoning", ""),
                    float(decision.get("confidence", 0.0)),
                    1 if decision.get("success") else 0,
                    int(decision.get("latency_ms", 0)),
                    int(decision.get("state_hour", 0)),
                    decision.get("state_mood", ""),
                    float(decision.get("timestamp", time.time())),
                ),
            )

    async def save_goal(self, goal: dict[str, Any]) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO agi_goals (id,description,steps,current_step,status,context,created_at) VALUES (?,?,?,?,?,?,?)",
                (
                    goal.get("id", ""),
                    goal.get("description", ""),
                    json.dumps(goal.get("steps", [])),
                    int(goal.get("current_step", 0)),
                    goal.get("status", "active"),
                    json.dumps(goal.get("context", {})),
                    float(goal.get("created_at", time.time())),
                ),
            )

    async def update_goal(self, goal_id: str, current_step: int, status: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE agi_goals SET current_step=?, status=? WHERE id=?",
                (int(current_step), status, goal_id),
            )

    async def save_patterns(self, patterns: dict[str, Any], sequences: Any) -> None:
        seq_data: dict[str, Any]
        if hasattr(sequences, "most_common"):
            seq_data = dict(sequences.most_common(200))
        elif isinstance(sequences, dict):
            seq_data = sequences
        else:
            seq_data = {}

        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO agi_patterns (key,data,updated_at) VALUES (?,?,?)",
                ("patterns", json.dumps(patterns), time.time()),
            )
            conn.execute(
                "INSERT OR REPLACE INTO agi_patterns (key,data,updated_at) VALUES (?,?,?)",
                ("sequences", json.dumps(seq_data), time.time()),
            )

    async def save_habits(self, habits: dict[str, Any]) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO agi_habits (key,data,updated_at) VALUES (?,?,?)",
                ("habits", json.dumps(habits), time.time()),
            )

    async def save_reflection(self, reflection: dict[str, Any]) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO agi_reflections (data,timestamp) VALUES (?,?)",
                (json.dumps(reflection), time.time()),
            )

    async def save_solve_result(self, result: dict[str, Any]) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO agi_solve_results (problem,steps_total,steps_done,success,duration_s,timestamp) VALUES (?,?,?,?,?,?)",
                (
                    result.get("problem", ""),
                    int(result.get("steps_total", 0)),
                    int(result.get("steps_done", 0)),
                    1 if result.get("success") else 0,
                    float(result.get("duration_s", 0.0)),
                    float(result.get("timestamp", time.time())),
                ),
            )

    async def get_recent_events(self, n: int = 10) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM agi_events ORDER BY timestamp DESC LIMIT ?",
                (max(1, int(n)),),
            ).fetchall()
        return [dict(row) for row in rows]

    async def get_user_messages(self, user_id: str = "pavan", limit: int = 300) -> list[str]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT content
                FROM agi_events
                WHERE type='user_input' AND user_id=? AND content != ''
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (user_id, max(1, int(limit))),
            ).fetchall()
        return [str(r["content"]) for r in rows if r["content"]]

    async def count_events(self, event_type: str) -> int:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM agi_events WHERE type=?",
                (event_type,),
            ).fetchone()
        return int(row[0]) if row else 0

    async def get_latest_mood(self) -> str:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT emotion FROM agi_events WHERE emotion != '' ORDER BY timestamp DESC LIMIT 1"
            ).fetchone()
        if not row:
            return "neutral"
        mood = str(row["emotion"]).strip().lower()
        return mood or "neutral"

    async def get_stats(self) -> dict[str, Any]:
        with self._conn() as conn:
            events = conn.execute("SELECT COUNT(*) FROM agi_events").fetchone()[0]
            decisions = conn.execute("SELECT COUNT(*) FROM agi_decisions").fetchone()[0]
            successes = conn.execute("SELECT COUNT(*) FROM agi_decisions WHERE success=1").fetchone()[0]
            goals = conn.execute("SELECT COUNT(*) FROM agi_goals").fetchone()[0]
            active_goals = conn.execute("SELECT COUNT(*) FROM agi_goals WHERE status='active'").fetchone()[0]
            reflections = conn.execute("SELECT COUNT(*) FROM agi_reflections").fetchone()[0]
            solves = conn.execute("SELECT COUNT(*) FROM agi_solve_results").fetchone()[0]
        return {
            "events": int(events),
            "decisions": int(decisions),
            "success_rate": round((successes / decisions), 3) if decisions else 0.0,
            "goals": int(goals),
            "active_goals": int(active_goals),
            "reflections": int(reflections),
            "solve_runs": int(solves),
        }
