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
# core/cloud/cloud_memory.py
# CloudMemory — Supabase-backed key/value store with SQLite fallback.
from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3

from core.storage import MEMORY_DB
from .supabase_client import get_client, is_connected

logger = logging.getLogger("jarvis.cloud.memory")

_DEFAULT_USER = "local"


class CloudMemory:
    """
    Async memory store.
    - Primary:  Supabase (jarvis_memories table)
    - Fallback: SQLite at *local_db_path*
    """

    def __init__(self, user_id: str = _DEFAULT_USER, local_db_path: str | None = None):
        self._user_id = user_id
        self._db_path = local_db_path or MEMORY_DB
        self._ensure_local_schema()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    async def get(self, key: str) -> dict | None:
        if is_connected():
            try:
                return await asyncio.to_thread(self._sb_get, key)
            except Exception as exc:
                logger.warning("Supabase get failed, using SQLite: %s", exc)
        return self._sql_get(key)

    async def set(self, key: str, value: dict) -> bool:
        if is_connected():
            try:
                ok = await asyncio.to_thread(self._sb_set, key, value)
                if ok:
                    return True
            except Exception as exc:
                logger.warning("Supabase set failed, writing to SQLite: %s", exc)
        return self._sql_set(key, value)

    async def delete(self, key: str) -> bool:
        if is_connected():
            try:
                await asyncio.to_thread(self._sb_delete, key)
            except Exception as exc:
                logger.warning("Supabase delete failed: %s", exc)
        return self._sql_delete(key)

    async def list(self, prefix: str = "") -> list[dict]:
        if is_connected():
            try:
                return await asyncio.to_thread(self._sb_list, prefix)
            except Exception as exc:
                logger.warning("Supabase list failed, using SQLite: %s", exc)
        return self._sql_list(prefix)

    async def search(self, query: str) -> list[dict]:
        """Full-text search via Supabase; falls back to SQLite LIKE."""
        if is_connected():
            try:
                return await asyncio.to_thread(self._sb_search, query)
            except Exception as exc:
                logger.warning("Supabase search failed, using SQLite: %s", exc)
        return self._sql_search(query)

    # ------------------------------------------------------------------ #
    # Sync helpers
    # ------------------------------------------------------------------ #

    async def sync_from_local(self, local_db_path: str | None = None) -> int:
        """Push local SQLite rows → Supabase. Returns number of rows synced."""
        path = local_db_path or self._db_path
        if not is_connected():
            logger.warning("sync_from_local: Supabase not connected")
            return 0
        rows = self._sql_all(path)
        count = 0
        for row in rows:
            try:
                await asyncio.to_thread(self._sb_set, row["key"], row["value"])
                count += 1
            except Exception as exc:
                logger.error("Failed to sync row %s: %s", row["key"], exc)
        logger.info("Synced %d rows → Supabase", count)
        return count

    async def sync_to_local(self, local_db_path: str | None = None) -> int:
        """Pull Supabase rows → SQLite. Returns number of rows synced."""
        path = local_db_path or self._db_path
        if not is_connected():
            logger.warning("sync_to_local: Supabase not connected")
            return 0
        rows = await asyncio.to_thread(self._sb_list, "")
        self._ensure_local_schema(path)
        count = 0
        for row in rows:
            try:
                self._sql_set(row["key"], row["value"], db_path=path)
                count += 1
            except Exception as exc:
                logger.error("Failed to write local row %s: %s", row["key"], exc)
        logger.info("Pulled %d rows ← Supabase", count)
        return count

    # ------------------------------------------------------------------ #
    # Supabase backend
    # ------------------------------------------------------------------ #

    def _sb_get(self, key: str) -> dict | None:
        client = get_client()
        res = (
            client.table("jarvis_memories")
            .select("value")
            .eq("user_id", self._user_id)
            .eq("key", key)
            .single()
            .execute()
        )
        if res.data:
            return res.data.get("value")
        return None

    def _sb_set(self, key: str, value: dict) -> bool:
        client = get_client()
        client.table("jarvis_memories").upsert(
            {"user_id": self._user_id, "key": key, "value": value},
            on_conflict="user_id,key",
        ).execute()
        return True

    def _sb_delete(self, key: str) -> None:
        client = get_client()
        client.table("jarvis_memories").delete().eq("user_id", self._user_id).eq("key", key).execute()

    def _sb_list(self, prefix: str) -> list[dict]:
        client = get_client()
        q = client.table("jarvis_memories").select("key, value").eq("user_id", self._user_id)
        if prefix:
            q = q.like("key", f"{prefix}%")
        res = q.execute()
        return [{"key": r["key"], "value": r["value"]} for r in (res.data or [])]

    def _sb_search(self, query: str) -> list[dict]:
        client = get_client()
        res = (
            client.table("jarvis_memories")
            .select("key, value")
            .eq("user_id", self._user_id)
            .text_search("value", query)
            .execute()
        )
        return [{"key": r["key"], "value": r["value"]} for r in (res.data or [])]

    # ------------------------------------------------------------------ #
    # SQLite backend
    # ------------------------------------------------------------------ #

    def _ensure_local_schema(self, db_path: str | None = None) -> None:
        path = db_path or self._db_path
        with sqlite3.connect(path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS jarvis_memories (
                    key        TEXT PRIMARY KEY,
                    value_json TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
            """)
            conn.commit()

    def _sql_get(self, key: str) -> dict | None:
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT value_json FROM jarvis_memories WHERE key=?", (key,)
            ).fetchone()
        if row:
            try:
                return json.loads(row[0])
            except Exception as _e:
                logger.debug("cloud_memory _sql_get json parse failed: %s", _e)
                return {"raw": row[0]}
        return None

    def _sql_set(self, key: str, value: dict, db_path: str | None = None) -> bool:
        path = db_path or self._db_path
        with sqlite3.connect(path) as conn:
            conn.execute("""
                INSERT INTO jarvis_memories (key, value_json)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json,
                    updated_at=datetime('now')
            """, (key, json.dumps(value)))
            conn.commit()
        return True

    def _sql_delete(self, key: str) -> bool:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("DELETE FROM jarvis_memories WHERE key=?", (key,))
            conn.commit()
        return True

    def _sql_list(self, prefix: str) -> list[dict]:
        with sqlite3.connect(self._db_path) as conn:
            if prefix:
                rows = conn.execute(
                    "SELECT key, value_json FROM jarvis_memories WHERE key LIKE ?",
                    (f"{prefix}%",)
                ).fetchall()
            else:
                rows = conn.execute("SELECT key, value_json FROM jarvis_memories").fetchall()
        result = []
        for key, vj in rows:
            try:
                result.append({"key": key, "value": json.loads(vj)})
            except Exception as _e:
                logger.debug("cloud_memory _sql_list json parse failed: %s", _e)
                result.append({"key": key, "value": {"raw": vj}})
        return result

    def _sql_all(self, db_path: str) -> list[dict]:
        """Read every row from an arbitrary SQLite db file."""
        if not os.path.exists(db_path):
            return []
        with sqlite3.connect(db_path) as conn:
            rows = conn.execute("SELECT key, value_json FROM jarvis_memories").fetchall()
        result = []
        for key, vj in rows:
            try:
                result.append({"key": key, "value": json.loads(vj)})
            except Exception as _e:
                logger.debug("cloud_memory _sql_all json parse failed: %s", _e)
                result.append({"key": key, "value": {"raw": vj}})
        return result

    def _sql_search(self, query: str) -> list[dict]:
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                "SELECT key, value_json FROM jarvis_memories WHERE key LIKE ? OR value_json LIKE ?",
                (f"%{query}%", f"%{query}%")
            ).fetchall()
        result = []
        for key, vj in rows:
            try:
                result.append({"key": key, "value": json.loads(vj)})
            except Exception as _e:
                logger.debug("cloud_memory _sql_search json parse failed: %s", _e)
                result.append({"key": key, "value": {"raw": vj}})
        return result
