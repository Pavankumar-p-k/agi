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

"""core.cloud.cloud_memory — async key/value memory with SQLite local backend."""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

import core.cloud.supabase_client as supabase_client


class CloudMemory:
    """Key/value memory. Uses Supabase when connected, else a local SQLite DB."""

    def __init__(self, local_db_path: str | Path = "cloud_memory.db") -> None:
        self.local_db_path = str(local_db_path)
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self) -> None:
        with self._lock:
            conn = sqlite3.connect(self.local_db_path)
            conn.execute(
                "CREATE TABLE IF NOT EXISTS memory ("
                " key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )
            conn.commit()
            conn.close()

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.local_db_path)

    # ── async API ───────────────────────────────────────────────────────────
    async def set(self, key: str, value: Any) -> None:
        encoded = json.dumps(value)
        if supabase_client._connected and supabase_client._client is not None:
            client = supabase_client._client
            client.table("memory").upsert({"key": key, "value": encoded}).execute()
            return
        with self._lock:
            conn = self._conn()
            conn.execute(
                "INSERT INTO memory (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, encoded),
            )
            conn.commit()
            conn.close()

    async def get(self, key: str) -> Any | None:
        if supabase_client._connected and supabase_client._client is not None:
            resp = supabase_client._client.table("memory").select("value").eq("key", key).execute()
            rows = getattr(resp, "data", []) or []
            if not rows:
                return None
            return json.loads(rows[0]["value"])
        with self._lock:
            conn = self._conn()
            row = conn.execute("SELECT value FROM memory WHERE key = ?", (key,)).fetchone()
            conn.close()
        return json.loads(row[0]) if row else None

    async def delete(self, key: str) -> None:
        if supabase_client._connected and supabase_client._client is not None:
            supabase_client._client.table("memory").delete().eq("key", key).execute()
            return
        with self._lock:
            conn = self._conn()
            conn.execute("DELETE FROM memory WHERE key = ?", (key,))
            conn.commit()
            conn.close()

    async def list(self, prefix: str = "") -> list[dict[str, Any]]:
        if supabase_client._connected and supabase_client._client is not None:
            rows = supabase_client._client.table("memory").select("*").execute().data or []
        else:
            with self._lock:
                conn = self._conn()
                rows = conn.execute("SELECT key, value FROM memory").fetchall()
                conn.close()
        return [
            {"key": k, "value": json.loads(v)}
            for k, v in rows
            if k.startswith(prefix)
        ]

    async def search(self, query: str) -> list[dict[str, Any]]:
        results = []
        for row in await self.list():
            if query.lower() in json.dumps(row["value"]).lower() or query.lower() in row["key"].lower():
                results.append(row)
        return results


__all__ = ["CloudMemory"]
