# memory/store.py
#
# JARVIS MEMORY SYSTEM
# ─────────────────────────────────────────────────────────────
#  Stores every conversation turn in SQLite.
#  Retrieves relevant past messages using:
#   1. Exact keyword search
#   2. Recency (always include last N turns)
#   3. Intent matching
#   4. Emotional context matching
#
#  Tables:
#   messages   — every chat turn (user + assistant)
#   summaries  — per-user daily summaries (condensed memory)
#   facts       — extracted facts about the user ("Pavan likes Python")
#   emotions    — emotion history timeline

import sqlite3
import json
import time
import asyncio
from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass

DB_PATH = Path("data/jarvis_memory.db")


@dataclass
class MemoryEntry:
    id:        int
    user_id:   str
    role:      str       # "user" or "assistant"
    content:   str
    intent:    str
    emotion:   str
    model:     str
    timestamp: float
    quality:   float


class MemoryStore:
    def __init__(self):
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        print("[Memory] Database ready")

    def _conn(self):
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")     # concurrent reads
        conn.execute("PRAGMA synchronous=NORMAL")   # faster writes
        return conn

    def _init_db(self):
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS messages (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id   TEXT NOT NULL,
                    role      TEXT NOT NULL,
                    content   TEXT NOT NULL,
                    intent    TEXT DEFAULT '',
                    emotion   TEXT DEFAULT 'neutral',
                    model     TEXT DEFAULT '',
                    quality   REAL DEFAULT 0.7,
                    timestamp REAL NOT NULL,
                    session   TEXT DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS summaries (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id   TEXT NOT NULL,
                    date      TEXT NOT NULL,
                    summary   TEXT NOT NULL,
                    key_facts TEXT DEFAULT '[]',
                    timestamp REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS user_facts (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id   TEXT NOT NULL,
                    fact      TEXT NOT NULL,
                    category  TEXT DEFAULT 'general',
                    confidence REAL DEFAULT 1.0,
                    timestamp REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS emotion_log (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id   TEXT NOT NULL,
                    emotion   TEXT NOT NULL,
                    trigger   TEXT DEFAULT '',
                    timestamp REAL NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_msg_user    ON messages(user_id, timestamp DESC);
                CREATE INDEX IF NOT EXISTS idx_msg_intent  ON messages(intent);
                CREATE INDEX IF NOT EXISTS idx_msg_emotion ON messages(emotion);
                CREATE INDEX IF NOT EXISTS idx_facts_user  ON user_facts(user_id);
            """)

    # ═══════════════════════════════════════════════
    #  SAVE
    # ═══════════════════════════════════════════════

    async def save(self, user_id: str, role: str, content: str,
                   metadata: dict = None, session: str = "") -> int:
        meta = metadata or {}
        ts   = time.time()
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO messages (user_id,role,content,intent,emotion,model,quality,timestamp,session) VALUES (?,?,?,?,?,?,?,?,?)",
                (user_id, role, content,
                 meta.get("intent",""), meta.get("emotion","neutral"),
                 meta.get("model",""), meta.get("quality",0.7), ts, session)
            )
            msg_id = cur.lastrowid

        # Log emotion separately for timeline
        if meta.get("emotion") and role == "user":
            await self.log_emotion(user_id, meta["emotion"], content[:100])

        return msg_id

    async def log_emotion(self, user_id: str, emotion: str, trigger: str = ""):
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO emotion_log (user_id,emotion,trigger,timestamp) VALUES (?,?,?,?)",
                (user_id, emotion, trigger, time.time())
            )

    async def save_fact(self, user_id: str, fact: str, category: str = "general"):
        with self._conn() as conn:
            # Avoid duplicates
            exists = conn.execute(
                "SELECT id FROM user_facts WHERE user_id=? AND fact=?",
                (user_id, fact)).fetchone()
            if not exists:
                conn.execute(
                    "INSERT INTO user_facts (user_id,fact,category,timestamp) VALUES (?,?,?,?)",
                    (user_id, fact, category, time.time())
                )

    # ═══════════════════════════════════════════════
    #  RETRIEVE
    # ═══════════════════════════════════════════════

    async def get_recent(self, user_id: str, n: int = 10) -> List[MemoryEntry]:
        """Get last N messages (both user + assistant)."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM messages WHERE user_id=? ORDER BY timestamp DESC LIMIT ?",
                (user_id, n)
            ).fetchall()
        return [self._row_to_entry(r) for r in reversed(rows)]

    async def search_by_keyword(self, user_id: str, keyword: str,
                                 limit: int = 5) -> List[MemoryEntry]:
        """Find messages containing a keyword."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM messages WHERE user_id=? AND content LIKE ? ORDER BY timestamp DESC LIMIT ?",
                (user_id, f"%{keyword}%", limit)
            ).fetchall()
        return [self._row_to_entry(r) for r in rows]

    async def search_by_intent(self, user_id: str, intent: str,
                                limit: int = 3) -> List[MemoryEntry]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM messages WHERE user_id=? AND intent=? ORDER BY timestamp DESC LIMIT ?",
                (user_id, intent, limit)
            ).fetchall()
        return [self._row_to_entry(r) for r in rows]

    async def search_by_emotion(self, user_id: str, emotion: str,
                                 limit: int = 3) -> List[MemoryEntry]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM messages WHERE user_id=? AND emotion=? ORDER BY timestamp DESC LIMIT ?",
                (user_id, emotion, limit)
            ).fetchall()
        return [self._row_to_entry(r) for r in rows]

    async def get_user_facts(self, user_id: str) -> List[str]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT fact FROM user_facts WHERE user_id=? ORDER BY timestamp DESC",
                (user_id,)
            ).fetchall()
        return [r["fact"] for r in rows]

    async def get_emotion_trend(self, user_id: str, hours: int = 24) -> dict:
        """Get emotion frequency in last N hours."""
        since = time.time() - (hours * 3600)
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT emotion, COUNT(*) as cnt FROM emotion_log WHERE user_id=? AND timestamp > ? GROUP BY emotion ORDER BY cnt DESC",
                (user_id, since)
            ).fetchall()
        return {r["emotion"]: r["cnt"] for r in rows}

    async def get_stats(self, user_id: str) -> dict:
        with self._conn() as conn:
            total = conn.execute("SELECT COUNT(*) FROM messages WHERE user_id=?", (user_id,)).fetchone()[0]
            facts = conn.execute("SELECT COUNT(*) FROM user_facts WHERE user_id=?", (user_id,)).fetchone()[0]
            oldest = conn.execute("SELECT MIN(timestamp) FROM messages WHERE user_id=?", (user_id,)).fetchone()[0]
        return {
            "total_messages": total,
            "known_facts":    facts,
            "memory_since":   oldest,
        }

    async def clear_user_memory(self, user_id: str):
        with self._conn() as conn:
            conn.execute("DELETE FROM messages WHERE user_id=?", (user_id,))
            conn.execute("DELETE FROM user_facts WHERE user_id=?", (user_id,))
            conn.execute("DELETE FROM emotion_log WHERE user_id=?", (user_id,))

    def _row_to_entry(self, r) -> MemoryEntry:
        return MemoryEntry(
            id=r["id"], user_id=r["user_id"], role=r["role"],
            content=r["content"], intent=r["intent"], emotion=r["emotion"],
            model=r["model"], timestamp=r["timestamp"], quality=r["quality"],
        )
