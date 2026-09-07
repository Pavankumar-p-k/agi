from __future__ import annotations

import json
import logging
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import MessageDirection, MessageStatus, MessageType, WhatsAppMessage

logger = logging.getLogger(__name__)


class WhatsAppHistory:
    def __init__(self, db_path: str | Path | None = None):
        if db_path is None:
            db_path = Path.home() / ".jarvis" / "whatsapp_history.db"
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._init_db()

    @property
    def _conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(str(self._db_path))
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA foreign_keys=ON")
        return self._local.conn

    def _init_db(self):
        conn = self._conn
        conn.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                phone_number TEXT NOT NULL,
                contact_name TEXT DEFAULT '',
                last_message_at TEXT,
                message_count INTEGER DEFAULT 0,
                metadata TEXT DEFAULT '{}'
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                direction TEXT NOT NULL,
                from_number TEXT NOT NULL,
                to_number TEXT NOT NULL,
                type TEXT NOT NULL,
                text TEXT,
                media_json TEXT,
                location_json TEXT,
                contacts_json TEXT,
                context_message_id TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                timestamp TEXT,
                raw_json TEXT,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_conversation
            ON messages(conversation_id, timestamp)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_from
            ON messages(from_number, timestamp)
        """)
        conn.commit()

    def _conversation_id(self, a: str, b: str) -> str:
        participants = sorted([a, b])
        return f"{participants[0]}_{participants[1]}"

    async def save_message(self, msg: WhatsAppMessage) -> None:
        conv_id = self._conversation_id(msg.from_number, msg.to_number)
        ts = msg.timestamp.isoformat() if msg.timestamp else datetime.utcnow().isoformat()
        conn = self._conn
        conn.execute(
            """INSERT INTO conversations (id, phone_number, last_message_at, message_count)
               VALUES (?, ?, ?, 1)
               ON CONFLICT(id) DO UPDATE SET
                   last_message_at=excluded.last_message_at,
                   message_count=message_count+1""",
            (conv_id, msg.from_number, ts),
        )
        conn.execute(
            """INSERT OR REPLACE INTO messages
               (id, conversation_id, direction, from_number, to_number, type, text,
                media_json, location_json, contacts_json, context_message_id, status, timestamp, raw_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                msg.id,
                conv_id,
                msg.direction.value,
                msg.from_number,
                msg.to_number,
                msg.type.value,
                msg.text,
                json.dumps({"id": msg.media.id, "mime_type": msg.media.mime_type, "sha256": msg.media.sha256, "file_size": msg.media.file_size, "filename": msg.media.filename, "caption": msg.media.caption}) if msg.media else None,
                json.dumps({"latitude": msg.location.latitude, "longitude": msg.location.longitude, "name": msg.location.name, "address": msg.location.address}) if msg.location else None,
                json.dumps([{"name": c.name, "phones": c.phones, "emails": c.emails} for c in msg.contacts]) if msg.contacts else None,
                msg.context_message_id,
                msg.status.value,
                ts,
                json.dumps(msg.raw) if msg.raw else None,
            ),
        )
        conn.commit()

    async def get_conversation(
        self,
        phone_a: str,
        phone_b: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[WhatsAppMessage]:
        conv_id = self._conversation_id(phone_a, phone_b)
        rows = self._conn.execute(
            """SELECT * FROM messages
               WHERE conversation_id = ?
               ORDER BY timestamp DESC
               LIMIT ? OFFSET ?""",
            (conv_id, limit, offset),
        ).fetchall()
        return [self._row_to_message(r) for r in reversed(rows)]

    async def get_recent_conversations(
        self,
        phone_number: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        if phone_number:
            rows = self._conn.execute(
                """SELECT * FROM conversations
                   WHERE phone_number = ?
                   ORDER BY last_message_at DESC
                   LIMIT ?""",
                (phone_number, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                """SELECT * FROM conversations
                   ORDER BY last_message_at DESC
                   LIMIT ?""",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    async def search_messages(
        self,
        query: str,
        limit: int = 20,
    ) -> list[WhatsAppMessage]:
        rows = self._conn.execute(
            """SELECT * FROM messages
               WHERE text LIKE ?
               ORDER BY timestamp DESC
               LIMIT ?""",
            (f"%{query}%", limit),
        ).fetchall()
        return [self._row_to_message(r) for r in rows]

    async def update_message_status(self, message_id: str, status: MessageStatus) -> None:
        self._conn.execute(
            "UPDATE messages SET status = ? WHERE id = ?",
            (status.value, message_id),
        )
        self._conn.commit()

    async def delete_conversation(self, phone_a: str, phone_b: str) -> None:
        conv_id = self._conversation_id(phone_a, phone_b)
        self._conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conv_id,))
        self._conn.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
        self._conn.commit()

    async def message_count(self, phone_a: str, phone_b: str) -> int:
        conv_id = self._conversation_id(phone_a, phone_b)
        row = self._conn.execute(
            "SELECT message_count FROM conversations WHERE id = ?", (conv_id,)
        ).fetchone()
        return row["message_count"] if row else 0

    def _row_to_message(self, row: sqlite3.Row) -> WhatsAppMessage:
        from .models import WhatsAppContact, WhatsAppLocation, WhatsAppMedia

        media = None
        if row["media_json"]:
            md = json.loads(row["media_json"])
            media = WhatsAppMedia(**md)

        location = None
        if row["location_json"]:
            ld = json.loads(row["location_json"])
            location = WhatsAppLocation(**ld)

        contacts = []
        if row["contacts_json"]:
            for cd in json.loads(row["contacts_json"]):
                contacts.append(WhatsAppContact(**cd))

        ts = None
        if row["timestamp"]:
            try:
                ts = datetime.fromisoformat(row["timestamp"])
            except (ValueError, TypeError):
                pass

        return WhatsAppMessage(
            id=row["id"],
            direction=MessageDirection(row["direction"]),
            from_number=row["from_number"],
            to_number=row["to_number"],
            type=MessageType(row["type"]),
            text=row["text"],
            media=media,
            location=location,
            contacts=contacts,
            context_message_id=row["context_message_id"],
            status=MessageStatus(row["status"]),
            timestamp=ts,
            raw=json.loads(row["raw_json"]) if row["raw_json"] else {},
        )

    def close(self):
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close()
            self._local.conn = None
