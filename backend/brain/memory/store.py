from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.config import BASE_DIR

DB_PATH = BASE_DIR / "data" / "jarvis_brain_memory.db"


@dataclass
class MemoryEntry:
    id: int
    user_id: str
    role: str
    content: str
    intent: str
    emotion: str
    model: str
    timestamp: float
    quality: float


class MemoryStore:
    def __init__(self) -> None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    intent TEXT DEFAULT '',
                    emotion TEXT DEFAULT 'neutral',
                    model TEXT DEFAULT '',
                    quality REAL DEFAULT 0.7,
                    timestamp REAL NOT NULL,
                    session TEXT DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS user_facts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    fact TEXT NOT NULL,
                    category TEXT DEFAULT 'general',
                    confidence REAL DEFAULT 1.0,
                    timestamp REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS emotion_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    emotion TEXT NOT NULL,
                    trigger TEXT DEFAULT '',
                    timestamp REAL NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_messages_user_ts ON messages(user_id, timestamp DESC);
                CREATE INDEX IF NOT EXISTS idx_messages_intent ON messages(intent);
                CREATE INDEX IF NOT EXISTS idx_messages_emotion ON messages(emotion);
                CREATE INDEX IF NOT EXISTS idx_facts_user ON user_facts(user_id);
                """
            )

    async def save(self, user_id: str, role: str, content: str, metadata: dict[str, Any] | None = None, session: str = "") -> int:
        meta = metadata or {}
        ts = time.time()
        with self._conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO messages (user_id, role, content, intent, emotion, model, quality, timestamp, session)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    role,
                    content,
                    str(meta.get("intent", "")),
                    str(meta.get("emotion", "neutral")),
                    str(meta.get("model", "")),
                    float(meta.get("quality", 0.7)),
                    ts,
                    session,
                ),
            )
            message_id = int(cur.lastrowid)

        if role == "user" and meta.get("emotion"):
            await self.log_emotion(user_id, str(meta["emotion"]), content[:120])
        return message_id

    async def log_emotion(self, user_id: str, emotion: str, trigger: str = "") -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO emotion_log (user_id, emotion, trigger, timestamp) VALUES (?, ?, ?, ?)",
                (user_id, emotion, trigger, time.time()),
            )

    async def save_fact(self, user_id: str, fact: str, category: str = "general") -> None:
        with self._conn() as conn:
            row = conn.execute("SELECT id FROM user_facts WHERE user_id=? AND fact=?", (user_id, fact)).fetchone()
            if row:
                return
            conn.execute(
                "INSERT INTO user_facts (user_id, fact, category, timestamp) VALUES (?, ?, ?, ?)",
                (user_id, fact, category, time.time()),
            )

    async def get_recent(self, user_id: str, n: int = 10) -> list[MemoryEntry]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM messages WHERE user_id=? ORDER BY timestamp DESC LIMIT ?",
                (user_id, n),
            ).fetchall()
        return [self._row_to_entry(r) for r in reversed(rows)]

    async def search_by_keyword(self, user_id: str, keyword: str, limit: int = 5) -> list[MemoryEntry]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM messages WHERE user_id=? AND content LIKE ? ORDER BY timestamp DESC LIMIT ?",
                (user_id, f"%{keyword}%", limit),
            ).fetchall()
        return [self._row_to_entry(r) for r in rows]

    async def search_by_intent(self, user_id: str, intent: str, limit: int = 3) -> list[MemoryEntry]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM messages WHERE user_id=? AND intent=? ORDER BY timestamp DESC LIMIT ?",
                (user_id, intent, limit),
            ).fetchall()
        return [self._row_to_entry(r) for r in rows]

    async def search_by_emotion(self, user_id: str, emotion: str, limit: int = 3) -> list[MemoryEntry]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM messages WHERE user_id=? AND emotion=? ORDER BY timestamp DESC LIMIT ?",
                (user_id, emotion, limit),
            ).fetchall()
        return [self._row_to_entry(r) for r in rows]

    async def get_user_facts(self, user_id: str) -> list[str]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT fact FROM user_facts WHERE user_id=? ORDER BY timestamp DESC",
                (user_id,),
            ).fetchall()
        return [str(r["fact"]) for r in rows]

    async def get_emotion_trend(self, user_id: str, hours: int = 24) -> dict[str, int]:
        since = time.time() - (hours * 3600)
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT emotion, COUNT(*) as cnt
                FROM emotion_log
                WHERE user_id=? AND timestamp>?
                GROUP BY emotion
                ORDER BY cnt DESC
                """,
                (user_id, since),
            ).fetchall()
        return {str(r["emotion"]): int(r["cnt"]) for r in rows}

    async def get_stats(self, user_id: str) -> dict[str, Any]:
        with self._conn() as conn:
            total = conn.execute("SELECT COUNT(*) FROM messages WHERE user_id=?", (user_id,)).fetchone()[0]
            facts = conn.execute("SELECT COUNT(*) FROM user_facts WHERE user_id=?", (user_id,)).fetchone()[0]
            oldest = conn.execute("SELECT MIN(timestamp) FROM messages WHERE user_id=?", (user_id,)).fetchone()[0]
        return {"total_messages": total, "known_facts": facts, "memory_since": oldest}

    async def clear_user_memory(self, user_id: str) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM messages WHERE user_id=?", (user_id,))
            conn.execute("DELETE FROM user_facts WHERE user_id=?", (user_id,))
            conn.execute("DELETE FROM emotion_log WHERE user_id=?", (user_id,))

    def _row_to_entry(self, row: sqlite3.Row) -> MemoryEntry:
        return MemoryEntry(
            id=int(row["id"]),
            user_id=str(row["user_id"]),
            role=str(row["role"]),
            content=str(row["content"]),
            intent=str(row["intent"]),
            emotion=str(row["emotion"]),
            model=str(row["model"]),
            timestamp=float(row["timestamp"]),
            quality=float(row["quality"]),
        )
