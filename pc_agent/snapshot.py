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
import os
import shutil
import sqlite3
import tempfile
import time
from pathlib import Path
from typing import Optional


class SystemSnapshot:
    """Filesystem + registry snapshot before PC control execution. Supports rollback.

    Layer 3 of the 3-layer PC Control Safety Architecture:
      Layer 1: Risk Classifier (GovernanceValidator)
      Layer 2: Confirmation Gate (interpreter.auto_run)
      Layer 3: Snapshot + Rollback (this module)
    """

    def __init__(self, db_path: str = "data/jarvis_os_world.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._snapshot_dir: Optional[str] = None
        self._backup_paths: list[str] = []
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_id TEXT UNIQUE,
                instruction TEXT,
                created_at REAL,
                rolled_back_at REAL,
                path_count INTEGER,
                status TEXT DEFAULT 'active'
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS snapshot_paths (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_id TEXT,
                path TEXT,
                backup_path TEXT,
                is_dir INTEGER DEFAULT 0
            )
        """)
        conn.commit()
        conn.close()

    def create(self, instruction: str, watch_paths: list[str] | None = None) -> str:
        """Snapshot current state of watched paths before execution."""
        snapshot_id = f"snap_{int(time.time())}_{abs(hash(instruction)) % 10000}"
        self._snapshot_dir = tempfile.mkdtemp(prefix="jarvis_snapshot_")
        self._backup_paths = []

        paths = watch_paths or [
            os.path.expanduser("~/Desktop"),
            os.path.expanduser("~/Documents"),
            os.getcwd(),
        ]

        conn = sqlite3.connect(self.db_path)
        for base_path in paths:
            if not os.path.exists(base_path):
                continue
            base = Path(base_path).resolve()
            backup_dir = os.path.join(self._snapshot_dir, base.name)
            os.makedirs(backup_dir, exist_ok=True)

            if base.is_file():
                dest = os.path.join(backup_dir, base.name)
                shutil.copy2(str(base), dest)
                self._backup_paths.append(str(base))
                conn.execute(
                    "INSERT INTO snapshot_paths (snapshot_id, path, backup_path, is_dir) VALUES (?, ?, ?, 0)",
                    (snapshot_id, str(base), dest),
                )
            else:
                for item in base.iterdir():
                    if item.is_file() and item.suffix in (".py", ".txt", ".md", ".json", ".yaml", ".html", ".css", ".js", ".ts"):
                        dest = os.path.join(backup_dir, item.name)
                        shutil.copy2(str(item), dest)
                        self._backup_paths.append(str(item))
                        conn.execute(
                            "INSERT INTO snapshot_paths (snapshot_id, path, backup_path, is_dir) VALUES (?, ?, ?, 0)",
                            (snapshot_id, str(item), dest),
                        )

        conn.execute(
            "INSERT INTO snapshots (snapshot_id, instruction, created_at, path_count, status) VALUES (?, ?, ?, ?, 'active')",
            (snapshot_id, instruction, time.time(), len(self._backup_paths)),
        )
        conn.commit()
        conn.close()

        return snapshot_id

    def rollback(self, snapshot_id: str) -> int:
        """Restore all files from snapshot. Returns number of files restored."""
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute(
            "SELECT path, backup_path FROM snapshot_paths WHERE snapshot_id = ?", (snapshot_id,)
        ).fetchall()
        conn.execute(
            "UPDATE snapshots SET rolled_back_at = ?, status = 'rolled_back' WHERE snapshot_id = ?",
            (time.time(), snapshot_id),
        )
        conn.commit()
        conn.close()

        restored = 0
        for original_path, backup_path in rows:
            if os.path.exists(backup_path):
                os.makedirs(os.path.dirname(original_path), exist_ok=True)
                shutil.copy2(backup_path, original_path)
                restored += 1

        if self._snapshot_dir and os.path.exists(self._snapshot_dir):
            shutil.rmtree(self._snapshot_dir, ignore_errors=True)
            self._snapshot_dir = None

        return restored

    def clean_old(self, max_age_hours: int = 24):
        """Remove snapshot records and temp dirs older than max_age_hours."""
        cutoff = time.time() - (max_age_hours * 3600)
        conn = sqlite3.connect(self.db_path)
        old = conn.execute(
            "SELECT snapshot_id FROM snapshots WHERE created_at < ?", (cutoff,)
        ).fetchall()
        for (sid,) in old:
            conn.execute("DELETE FROM snapshot_paths WHERE snapshot_id = ?", (sid,))
        conn.execute("DELETE FROM snapshots WHERE created_at < ?", (cutoff,))
        conn.commit()
        conn.close()


snapshot_manager = SystemSnapshot()
