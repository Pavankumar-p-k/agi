# Copyright (c) 2024-2026 JARVIS Project
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from __future__ import annotations

import json
import logging
import sqlite3
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class PluginStateStore:
    def __init__(self, db_path: str | Path | None = None):
        if db_path is None:
            from core.storage import SYSTEM_DB
            db_path = Path(SYSTEM_DB)
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(str(self._db_path))
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA synchronous=NORMAL")
        return self._local.conn

    def _init_db(self) -> None:
        conn = self._get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS plugin_state (
                plugin_name TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (plugin_name, key)
            )
        """)
        conn.commit()

    def get(self, plugin_name: str, key: str, default: Any = None) -> Any:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT value FROM plugin_state WHERE plugin_name = ? AND key = ?",
            (plugin_name, key),
        ).fetchone()
        if row is None:
            return default
        try:
            return json.loads(row["value"])
        except (json.JSONDecodeError, TypeError):
            return row["value"]

    def set(self, plugin_name: str, key: str, value: Any) -> None:
        conn = self._get_conn()
        serialized = json.dumps(value, default=str)
        conn.execute(
            """INSERT INTO plugin_state (plugin_name, key, value, updated_at)
               VALUES (?, ?, ?, datetime('now'))
               ON CONFLICT(plugin_name, key) DO UPDATE SET
                   value = excluded.value,
                   updated_at = datetime('now')""",
            (plugin_name, key, serialized),
        )
        conn.commit()

    def delete(self, plugin_name: str, key: str) -> bool:
        conn = self._get_conn()
        cur = conn.execute(
            "DELETE FROM plugin_state WHERE plugin_name = ? AND key = ?",
            (plugin_name, key),
        )
        conn.commit()
        return cur.rowcount > 0

    def list_keys(self, plugin_name: str) -> list[dict]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT key, created_at, updated_at FROM plugin_state WHERE plugin_name = ? ORDER BY key",
            (plugin_name,),
        ).fetchall()
        return [dict(r) for r in rows]

    def list_plugins(self) -> list[str]:
        conn = self._get_conn()
        rows = conn.execute("SELECT DISTINCT plugin_name FROM plugin_state ORDER BY plugin_name").fetchall()
        return [r["plugin_name"] for r in rows]

    def clear(self, plugin_name: str) -> int:
        conn = self._get_conn()
        cur = conn.execute("DELETE FROM plugin_state WHERE plugin_name = ?", (plugin_name,))
        conn.commit()
        return cur.rowcount

    def get_all(self, plugin_name: str) -> dict[str, Any]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT key, value FROM plugin_state WHERE plugin_name = ?", (plugin_name,)
        ).fetchall()
        result = {}
        for r in rows:
            try:
                result[r["key"]] = json.loads(r["value"])
            except (json.JSONDecodeError, TypeError):
                result[r["key"]] = r["value"]
        return result

    def export(self, plugin_name: str) -> dict:
        return {"plugin": plugin_name, "state": self.get_all(plugin_name)}

    def import_state(self, plugin_name: str, data: dict[str, Any]) -> int:
        count = 0
        for key, value in data.items():
            self.set(plugin_name, key, value)
            count += 1
        return count
