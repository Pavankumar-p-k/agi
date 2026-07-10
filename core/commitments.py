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

import builtins
import json
import logging
import sqlite3
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from core.storage import USER_DB

logger = logging.getLogger("jarvis.commitments")

DB_PATH = Path(USER_DB)


class CommitmentStore:
    """Tracks user commitments extracted from conversations."""

    def __init__(self):
        self._init_db()

    def _init_db(self):
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS commitments (
                    id TEXT PRIMARY KEY,
                    user_id TEXT,
                    description TEXT,
                    status TEXT DEFAULT 'pending',
                    priority TEXT DEFAULT 'medium',
                    created_at TIMESTAMP,
                    due_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    source_id TEXT
                )
            """)
            conn.commit()

    async def extract(self, user_id: str, user_msg: str, assistant_msg: str, source: str = ""):
        prompt = (
            "Extract commitments, tasks, or deadlines from this exchange. "
            "Return JSON array: [{\"description\":\"...\",\"due_at\":\"ISO8601|null\",\"priority\":\"low|medium|high\"}]\n\n"
            f"User: {user_msg}\nAssistant: {assistant_msg}"
        )
        try:
            from core.pipeline.internal_client import prompt as llm_prompt
            raw = await llm_prompt(prompt, user_id=user_id)
            items = json.loads(raw)
            for item in items:
                    self.add(
                        user_id=user_id,
                        description=item["description"],
                        due_at=item.get("due_at"),
                        priority=item.get("priority", "medium"),
                        source_id=source,
                    )
        except Exception as e:
            logger.warning("Failed to extract commitments: %s", e)

    def add(self, user_id: str, description: str, due_at: str | None = None,
            priority: str = "medium", source_id: str = "") -> str:
        cid = f"cmt_{uuid.uuid4().hex[:8]}"
        now = datetime.now().isoformat()
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "INSERT INTO commitments (id, user_id, description, status, priority, created_at, due_at, source_id) "
                "VALUES (?, ?, ?, 'pending', ?, ?, ?, ?)",
                (cid, user_id, description, priority, now, due_at, source_id),
            )
            conn.commit()
        return cid

    def list(self, user_id: str, status: str = "pending") -> builtins.list[dict[str, Any]]:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM commitments WHERE user_id = ? AND status = ? ORDER BY created_at DESC",
                (user_id, status),
            ).fetchall()
            return [dict(r) for r in rows]

    def complete(self, cid: str):
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "UPDATE commitments SET status = 'completed', completed_at = ? WHERE id = ?",
                (datetime.now().isoformat(), cid),
            )
            conn.commit()

    def upcoming(self, hours: int = 24) -> builtins.list[dict[str, Any]]:
        threshold = (datetime.now() + timedelta(hours=hours)).isoformat()
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM commitments WHERE status = 'pending' AND due_at IS NOT NULL AND due_at <= ?",
                (threshold,),
            ).fetchall()
            return [dict(r) for r in rows]


commitment_store = CommitmentStore()

__all__ = ["commitment_store", "CommitmentStore"]
