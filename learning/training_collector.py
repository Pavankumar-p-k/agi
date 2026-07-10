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

"""Log every interaction for fine-tuning. Auto-label accepted/rejected."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


class TrainingCollector:
    def __init__(self):
        from core.storage import SYSTEM_DB
        self.DB_PATH = Path(SYSTEM_DB)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.DB_PATH) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS training_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    input TEXT NOT NULL,
                    output TEXT NOT NULL,
                    grade_score REAL,
                    accepted BOOLEAN DEFAULT NULL,
                    correction_history TEXT DEFAULT '[]',
                    domain TEXT,
                    created_at TEXT
                )
            """)

    def log(self, input: str, output: str, grade: float,
            accepted: bool, domain: str,
            corrections: list[str] | None = None) -> int:
        if corrections is None:
            corrections = []
        with sqlite3.connect(self.DB_PATH) as conn:
            cursor = conn.execute("""
                INSERT INTO training_log
                (input, output, grade_score, accepted, correction_history, domain, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (input, output, grade, int(accepted),
                  json.dumps(corrections), domain,
                  datetime.now(timezone.utc).isoformat()))
            return cursor.lastrowid

    def export_for_training(self,
                             min_score: float = 85.0,
                             accepted_only: bool = True,
                             domain: str | None = None) -> list[dict]:
        query = "SELECT input, output FROM training_log WHERE grade_score >= ?"
        params = [min_score]
        if accepted_only:
            query += " AND accepted = 1"
        if domain:
            query += " AND domain = ?"
            params.append(domain)
        with sqlite3.connect(self.DB_PATH) as conn:
            rows = conn.execute(query, params).fetchall()
        return [{"instruction": r[0], "output": r[1]} for r in rows]

    def count(self, domain: str | None = None) -> int:
        query = "SELECT COUNT(*) FROM training_log"
        params = []
        if domain:
            query += " WHERE domain = ?"
            params.append(domain)
        with sqlite3.connect(self.DB_PATH) as conn:
            return conn.execute(query, params).fetchone()[0]
