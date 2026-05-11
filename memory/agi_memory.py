import sqlite3, json, time
from pathlib import Path
from typing import List, Dict, Any
from dataclasses import asdict

DB_PATH = Path("data/jarvis_agi.db")

class AGIMemory:

    def __init__(self):
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self._loop_count = 0
        print("[AGIMemory] Database ready ✓")

    def _conn(self):
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self):
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS agi_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    type TEXT, content TEXT, intent TEXT,
                    emotion TEXT, user_id TEXT,
                    hour INTEGER, day INTEGER,
                    timestamp REAL
                );
                CREATE TABLE IF NOT EXISTS agi_decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    action TEXT, tool TEXT, reasoning TEXT,
                    confidence REAL, success INTEGER,
                    latency_ms INTEGER, state_hour INTEGER,
                    state_mood TEXT, timestamp REAL
                );
                CREATE TABLE IF NOT EXISTS agi_goals (
                    id TEXT PRIMARY KEY, description TEXT,
                    steps TEXT, current_step INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'active', context TEXT,
                    created_at REAL
                );
                CREATE TABLE IF NOT EXISTS agi_patterns (
                    key TEXT PRIMARY KEY, data TEXT, updated_at REAL
                );
                CREATE TABLE IF NOT EXISTS agi_reflections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    data TEXT, timestamp REAL
                );
                CREATE TABLE IF NOT EXISTS agi_solve_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    problem TEXT, steps_total INTEGER, steps_done INTEGER,
                    success INTEGER, duration_s REAL, timestamp REAL
                );
                CREATE INDEX IF NOT EXISTS idx_events_ts ON agi_events(timestamp DESC);
                CREATE INDEX IF NOT EXISTS idx_decisions_ts ON agi_decisions(timestamp DESC);
            """)

    async def save_event(self, event: dict):
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO agi_events (type,content,intent,emotion,user_id,hour,day,timestamp) VALUES (?,?,?,?,?,?,?,?)",
                (event.get("type",""), event.get("content",""),
                 event.get("intent",""), event.get("emotion",""),
                 event.get("user_id","pavan"), event.get("hour",0),
                 event.get("day",0), event.get("timestamp",time.time()))
            )

    async def save_decision(self, d: dict):
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO agi_decisions (action,tool,reasoning,confidence,success,latency_ms,state_hour,state_mood,timestamp) VALUES (?,?,?,?,?,?,?,?,?)",
                (d.get("action",""), d.get("tool",""), d.get("reasoning",""),
                 d.get("confidence",0), 1 if d.get("success") else 0,
                 d.get("latency_ms",0), d.get("state_hour",0),
                 d.get("state_mood",""), d.get("timestamp",time.time()))
            )

    async def save_goal(self, goal: dict):
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO agi_goals (id,description,steps,current_step,status,context,created_at) VALUES (?,?,?,?,?,?,?)",
                (goal["id"], goal["description"], json.dumps(goal["steps"]),
                 goal.get("current_step",0), goal.get("status","active"),
                 json.dumps(goal.get("context",{})), goal.get("created_at",time.time()))
            )

    async def update_goal(self, goal_id: str, current_step: int, status: str):
        with self._conn() as conn:
            conn.execute("UPDATE agi_goals SET current_step=?,status=? WHERE id=?",
                        (current_step, status, goal_id))

    async def save_patterns(self, patterns: dict, sequences):
        with self._conn() as conn:
            conn.execute("INSERT OR REPLACE INTO agi_patterns (key,data,updated_at) VALUES (?,?,?)",
                        ("patterns", json.dumps(patterns), time.time()))
            conn.execute("INSERT OR REPLACE INTO agi_patterns (key,data,updated_at) VALUES (?,?,?)",
                        ("sequences", json.dumps(dict(sequences.most_common(100))), time.time()))

    async def save_reflection(self, reflection: dict):
        with self._conn() as conn:
            conn.execute("INSERT INTO agi_reflections (data,timestamp) VALUES (?,?)",
                        (json.dumps(reflection), time.time()))

    async def save_solve_result(self, result: dict):
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO agi_solve_results (problem,steps_total,steps_done,success,duration_s,timestamp) VALUES (?,?,?,?,?,?)",
                (result["problem"],result["steps_total"],result["steps_done"],
                 1 if result["success"] else 0, result["duration_s"],result["timestamp"])
            )

    async def get_recent_events(self, n: int = 10) -> list:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM agi_events ORDER BY timestamp DESC LIMIT ?", (n,)
            ).fetchall()
        return [dict(r) for r in rows]

    async def get_latest_mood(self) -> str:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT emotion FROM agi_events WHERE emotion != '' AND emotion != 'neutral' ORDER BY timestamp DESC LIMIT 1"
            ).fetchone()
        return row["emotion"] if row else "neutral"

    async def get_stats(self) -> dict:
        with self._conn() as conn:
            events    = conn.execute("SELECT COUNT(*) FROM agi_events").fetchone()[0]
            decisions = conn.execute("SELECT COUNT(*) FROM agi_decisions").fetchone()[0]
            successes = conn.execute("SELECT COUNT(*) FROM agi_decisions WHERE success=1").fetchone()[0]
            goals     = conn.execute("SELECT COUNT(*) FROM agi_goals").fetchone()[0]
            reflections = conn.execute("SELECT COUNT(*) FROM agi_reflections").fetchone()[0]
        return {
            "events":       events,
            "decisions":    decisions,
            "success_rate": round(successes/decisions,2) if decisions else 0,
            "goals":        goals,
            "reflections":  reflections,
        }
