from __future__ import annotations

from contextlib import closing
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class LegacyRemindersAdapter:
    def __init__(self, backend_root: Path) -> None:
        self.backend_root = Path(backend_root)
        self.path = self.backend_root / "data" / "jarvis.db"

    def status(self) -> dict[str, Any]:
        return {
            "name": "legacy_reminders",
            "available": self.path.exists(),
            "path": str(self.path),
            "count": self.pending_count()["total"] if self.path.exists() else 0,
        }

    def list_all(self, limit: int = 50) -> dict[str, Any]:
        if not self.path.exists():
            return {"reminders": [], "count": 0, "available": False}
        with closing(self._conn()) as conn:
            rows = conn.execute(
                """
                SELECT r.id, r.title, r.description, r.remind_at, r.repeat, r.is_done, r.created_at,
                       u.uid, u.email, u.display_name
                FROM reminders r
                LEFT JOIN users u ON u.id = r.user_id
                ORDER BY r.remind_at ASC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
        reminders = [self._row_to_dict(row) for row in rows]
        return {"reminders": reminders, "count": len(reminders), "available": True}

    def pending_count(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"total": 0, "available": False}
        now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat(sep=" ")
        with closing(self._conn()) as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM reminders WHERE is_done = 0 AND remind_at >= ?",
                (now,),
            ).fetchone()
        return {"total": int(row[0] if row else 0), "available": True}

    def create(
        self,
        *,
        title: str,
        remind_at: str,
        description: str = "",
        repeat: str = "none",
        user_uid: str = "legacy-default",
        email: str = "legacy@example.com",
        display_name: str = "Legacy User",
    ) -> dict[str, Any]:
        remind_at_value = self._normalize_datetime(remind_at)
        created_at = datetime.utcnow().isoformat(sep=" ")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._conn()) as conn:
            self._ensure_schema(conn)
            user_id = self._ensure_user(conn, user_uid=user_uid, email=email, display_name=display_name)
            cursor = conn.execute(
                """
                INSERT INTO reminders (user_id, title, description, remind_at, repeat, is_done, created_at)
                VALUES (?, ?, ?, ?, ?, 0, ?)
                """,
                (user_id, title, description, remind_at_value, repeat, created_at),
            )
            reminder_id = int(cursor.lastrowid)
            row = conn.execute(
                """
                SELECT r.id, r.title, r.description, r.remind_at, r.repeat, r.is_done, r.created_at,
                       u.uid, u.email, u.display_name
                FROM reminders r
                LEFT JOIN users u ON u.id = r.user_id
                WHERE r.id = ?
                """,
                (reminder_id,),
            ).fetchone()
            conn.commit()
        return {"created": True, "reminder": self._row_to_dict(row), "path": str(self.path)}

    def delete(self, reminder_id: int) -> dict[str, Any]:
        if not self.path.exists():
            return {"deleted": False, "path": str(self.path), "reason": "database missing"}
        with closing(self._conn()) as conn:
            row = conn.execute(
                """
                SELECT r.id, r.title, r.description, r.remind_at, r.repeat, r.is_done, r.created_at,
                       u.uid, u.email, u.display_name
                FROM reminders r
                LEFT JOIN users u ON u.id = r.user_id
                WHERE r.id = ?
                """,
                (int(reminder_id),),
            ).fetchone()
            if row is None:
                return {"deleted": False, "path": str(self.path), "reason": "reminder not found"}
            conn.execute("DELETE FROM reminders WHERE id = ?", (int(reminder_id),))
            conn.commit()
        return {"deleted": True, "reminder": self._row_to_dict(row), "path": str(self.path)}

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                uid TEXT UNIQUE,
                email TEXT UNIQUE,
                display_name TEXT,
                created_at TEXT,
                last_seen TEXT,
                preferences TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                remind_at TEXT NOT NULL,
                repeat TEXT,
                is_done INTEGER DEFAULT 0,
                created_at TEXT,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """
        )

    def _ensure_user(self, conn: sqlite3.Connection, *, user_uid: str, email: str, display_name: str) -> int:
        row = conn.execute("SELECT id FROM users WHERE uid = ? OR email = ?", (user_uid, email)).fetchone()
        if row is not None:
            return int(row["id"])
        created_at = datetime.utcnow().isoformat(sep=" ")
        cursor = conn.execute(
            "INSERT INTO users (uid, email, display_name, created_at) VALUES (?, ?, ?, ?)",
            (user_uid, email, display_name, created_at),
        )
        return int(cursor.lastrowid)

    def _normalize_datetime(self, value: str) -> str:
        text = value.strip()
        for parser in (
            lambda item: datetime.fromisoformat(item.replace("Z", "+00:00")),
            lambda item: datetime.strptime(item, "%Y-%m-%d %H:%M:%S"),
            lambda item: datetime.strptime(item, "%Y-%m-%dT%H:%M:%S"),
        ):
            try:
                parsed = parser(text)
                if parsed.tzinfo is not None:
                    parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
                return parsed.isoformat(sep=" ")
            except ValueError:
                continue
        raise ValueError(f"unsupported remind_at format: {value}")

    def _row_to_dict(self, row: sqlite3.Row | None) -> dict[str, Any]:
        if row is None:
            return {}
        return {
            "id": int(row["id"]),
            "title": row["title"],
            "description": row["description"] or "",
            "remind_at": row["remind_at"],
            "repeat": row["repeat"] or "none",
            "is_done": bool(row["is_done"]),
            "created_at": row["created_at"] or "",
            "user_uid": row["uid"] or "",
            "email": row["email"] or "",
            "display_name": row["display_name"] or "",
        }
