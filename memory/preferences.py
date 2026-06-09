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
import sqlite3
from pathlib import Path
from datetime import datetime


class PreferenceStore:
    DB_PATH = Path.home() / ".jarvis" / "preferences.db"

    def __init__(self):
        self.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.DB_PATH) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS preferences (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    count INTEGER DEFAULT 1,
                    last_seen TEXT
                )
            """)

    def record(self, key: str, value: str) -> None:
        with sqlite3.connect(self.DB_PATH) as conn:
            conn.execute("""
                INSERT INTO preferences (key, value, count, last_seen)
                VALUES (?, ?, 1, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    count = count + 1,
                    last_seen = excluded.last_seen
            """, (key, value, datetime.utcnow().isoformat()))

    def get_all(self) -> dict[str, str]:
        with sqlite3.connect(self.DB_PATH) as conn:
            rows = conn.execute("SELECT key, value FROM preferences ORDER BY count DESC").fetchall()
        return {k: v for k, v in rows}

    def forget(self, key: str) -> None:
        with sqlite3.connect(self.DB_PATH) as conn:
            conn.execute("DELETE FROM preferences WHERE key = ?", (key,))

    def forget_all(self) -> None:
        with sqlite3.connect(self.DB_PATH) as conn:
            conn.execute("DELETE FROM preferences")

    def as_context_string(self) -> str:
        prefs = self.get_all()
        if not prefs:
            return ""
        lines = [f"- {k}: {v}" for k, v in prefs.items()]
        return "KNOWN PREFERENCES:\n" + "\n".join(lines)


preference_store = PreferenceStore()
