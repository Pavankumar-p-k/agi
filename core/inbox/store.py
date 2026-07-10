"""InboxStore — SQLite-backed inbox for everything MJ wants to tell the user.

Items are chronological messages with read/unread state, categories,
and optional action buttons. The InboxStore subscribes to the EventBus
and auto-creates inbox items for key events.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from core.storage import SYSTEM_DB
from core.workflow.events import (
    ERROR,
    GOAL_COMPLETED,
    GOAL_FAILED,
    MILESTONE,
    NEED_INPUT,
    NODE_FAILED,
    NODE_SKIPPED,
    WARNING,
    get_bus,
)

logger = logging.getLogger(__name__)

_DEFAULT_DB = SYSTEM_DB

INBOX_CATEGORIES = ("finished", "approval", "error", "suggestion", "update")


class InboxItem:
    """A single inbox message."""

    def __init__(
        self,
        message: str,
        category: str = "update",
        session_id: str | None = None,
        goal_id: str | None = None,
        action_label: str | None = None,
        action_data: dict | None = None,
        item_id: str | None = None,
        read: bool = False,
        created_at: str | None = None,
    ) -> None:
        self.item_id = item_id or f"in_{uuid.uuid4().hex[:10]}"
        self.message = message
        self.category = category if category in INBOX_CATEGORIES else "update"
        self.session_id = session_id
        self.goal_id = goal_id
        self.action_label = action_label
        self.action_data = action_data or {}
        self.read = read
        self.created_at = created_at or datetime.utcnow().isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "message": self.message,
            "category": self.category,
            "session_id": self.session_id,
            "goal_id": self.goal_id,
            "action_label": self.action_label,
            "action_data": self.action_data,
            "read": self.read,
            "created_at": self.created_at,
        }


class InboxStore:
    """Persistent, SQLite-backed inbox."""

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path or _DEFAULT_DB
        self._lock = threading.Lock()
        self._init_db()
        self._subscribe_to_events()

    def _init_db(self) -> None:
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS inbox_items (
                    item_id TEXT PRIMARY KEY,
                    message TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT 'update',
                    session_id TEXT,
                    goal_id TEXT,
                    action_label TEXT,
                    action_data TEXT DEFAULT '{}',
                    read INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_inbox_read ON inbox_items(read);
                CREATE INDEX IF NOT EXISTS idx_inbox_category ON inbox_items(category);
                CREATE INDEX IF NOT EXISTS idx_inbox_created ON inbox_items(created_at);
            """)

    def _subscribe_to_events(self) -> None:
        bus = get_bus()
        bus.on(GOAL_COMPLETED, lambda e: self._auto_insert(
            message=f"Task completed: {e.payload.get('goal', '')}",
            category="finished",
            session_id=e.session_id,
            goal_id=e.goal_id,
        ))
        bus.on(GOAL_FAILED, lambda e: self._auto_insert(
            message=f"Task failed: {e.payload.get('goal', '')} — {e.payload.get('error', '')}",
            category="error",
            session_id=e.session_id,
            goal_id=e.goal_id,
        ))
        bus.on(NEED_INPUT, lambda e: self._auto_insert(
            message=e.payload.get("message", "I need your input"),
            category="approval",
            session_id=e.session_id,
            goal_id=e.goal_id,
            action_label=e.payload.get("action_label", "Respond"),
            action_data=e.payload.get("action_data", {}),
        ))
        bus.on(WARNING, lambda e: self._auto_insert(
            message=e.payload.get("message", ""),
            category="error",
            session_id=e.session_id,
            goal_id=e.goal_id,
        ))
        bus.on(ERROR, lambda e: self._auto_insert(
            message=e.payload.get("message", "An error occurred"),
            category="error",
            session_id=e.session_id,
            goal_id=e.goal_id,
        ))
        bus.on(MILESTONE, lambda e: self._auto_insert(
            message=e.payload.get("message", ""),
            category="update",
            session_id=e.session_id,
            goal_id=e.goal_id,
        ))
        bus.on(NODE_FAILED, lambda e: self._auto_insert(
            message=f"Step failed: {e.payload.get('label', '')}",
            category="error",
            session_id=e.session_id,
            goal_id=e.goal_id,
        ))
        bus.on(NODE_SKIPPED, lambda e: self._auto_insert(
            message=f"Step skipped: {e.payload.get('label', '')}",
            category="update",
            session_id=e.session_id,
            goal_id=e.goal_id,
        ))

    def _auto_insert(
        self,
        message: str,
        category: str = "update",
        session_id: str | None = None,
        goal_id: str | None = None,
        action_label: str | None = None,
        action_data: dict | None = None,
    ) -> str:
        if not message:
            return ""
        item = InboxItem(
            message=message,
            category=category,
            session_id=session_id,
            goal_id=goal_id,
            action_label=action_label,
            action_data=action_data,
        )
        self._insert(item)
        return item.item_id

    def _insert(self, item: InboxItem) -> None:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """INSERT OR IGNORE INTO inbox_items
                   (item_id, message, category, session_id, goal_id,
                    action_label, action_data, read, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    item.item_id,
                    item.message,
                    item.category,
                    item.session_id,
                    item.goal_id,
                    item.action_label,
                    json.dumps(item.action_data),
                    1 if item.read else 0,
                    item.created_at,
                ),
            )

    def add(
        self,
        message: str,
        category: str = "update",
        session_id: str | None = None,
        goal_id: str | None = None,
        action_label: str | None = None,
        action_data: dict | None = None,
    ) -> str:
        item = InboxItem(
            message=message,
            category=category,
            session_id=session_id,
            goal_id=goal_id,
            action_label=action_label,
            action_data=action_data,
        )
        self._insert(item)
        return item.item_id

    def list(
        self,
        limit: int = 50,
        unread_only: bool = False,
        category: str | None = None,
        before: str | None = None,
    ) -> list[dict[str, Any]]:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            parts = ["SELECT * FROM inbox_items"]
            conditions: list[str] = []
            params: list[Any] = []
            if unread_only:
                conditions.append("read = 0")
            if category:
                conditions.append("category = ?")
                params.append(category)
            if before:
                conditions.append("created_at < ?")
                params.append(before)
            if conditions:
                parts.append("WHERE " + " AND ".join(conditions))
            parts.append("ORDER BY created_at DESC LIMIT ?")
            params.append(limit)
            rows = conn.execute(" ".join(parts), params).fetchall()
            return [self._row_to_dict(r) for r in rows]

    def get(self, item_id: str) -> dict[str, Any] | None:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT * FROM inbox_items WHERE item_id = ?", (item_id,)
            ).fetchone()
            return self._row_to_dict(row) if row else None

    def mark_read(self, item_id: str) -> None:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "UPDATE inbox_items SET read = 1 WHERE item_id = ?", (item_id,)
            )

    def mark_all_read(self) -> None:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute("UPDATE inbox_items SET read = 1 WHERE read = 0")

    def unread_count(self) -> int:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM inbox_items WHERE read = 0"
            ).fetchone()
            return row[0] if row else 0

    def delete(self, item_id: str) -> None:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "DELETE FROM inbox_items WHERE item_id = ?", (item_id,)
            )

    def clear(self) -> None:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute("DELETE FROM inbox_items")

    def _row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "item_id": row[0],
            "message": row[1],
            "category": row[2],
            "session_id": row[3],
            "goal_id": row[4],
            "action_label": row[5],
            "action_data": json.loads(row[6]) if row[6] else {},
            "read": bool(row[7]),
            "created_at": row[8],
        }


# ── Global singleton ─────────────────────────────────────────────────────────

_inbox: InboxStore | None = None


def get_inbox() -> InboxStore:
    global _inbox
    if _inbox is None:
        _inbox = InboxStore()
    return _inbox


def reset_inbox() -> None:
    global _inbox
    _inbox = None
