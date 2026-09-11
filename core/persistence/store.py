from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from core.persistence.graph import ExecutionGraph
from core.persistence.schema import AgentCheckpoint


class CheckpointStore:
    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or str(Path.home() / ".jarvis" / "agent_checkpoints.db")
        self._using_memory = str(Path(self.db_path).parent).lower() == str(Path(tempfile.gettempdir())).lower() or self.db_path.startswith(tempfile.gettempdir())
        if self._using_memory:
            try:
                os.unlink(self.db_path)
            except FileNotFoundError:
                pass
            self._conn = sqlite3.connect(":memory:")
        else:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def close(self) -> None:
        if hasattr(self, "_conn") and self._conn is not None:
            self._conn.close()
            self._conn = None

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    def _init_db(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS checkpoints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_key TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                payload TEXT NOT NULL,
                graph_json TEXT,
                task TEXT
            )
            """
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_checkpoints_session ON checkpoints(session_key, updated_at DESC)"
        )
        self._conn.commit()

    def save(self, checkpoint: AgentCheckpoint, graph: ExecutionGraph | None = None) -> int:
        if checkpoint.created_at is None or checkpoint.created_at == "":
            checkpoint.created_at = datetime.now(timezone.utc).isoformat()
        checkpoint.updated_at = datetime.now(timezone.utc).isoformat()
        payload = json.dumps(checkpoint.to_dict())
        graph_json = json.dumps(graph.to_dict()) if graph is not None else None
        cur = self._conn.execute(
            "INSERT INTO checkpoints (session_key, created_at, updated_at, payload, graph_json, task) VALUES (?, ?, ?, ?, ?, ?)",
            (checkpoint.session_key, checkpoint.created_at, checkpoint.updated_at, payload, graph_json, checkpoint.task),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def save_agent_state(self, checkpoint: AgentCheckpoint, graph: ExecutionGraph | None = None) -> str:
        self.save(checkpoint, graph=graph)
        return checkpoint.session_key or ""

    def load_by_id(self, row_id: int) -> tuple[AgentCheckpoint, ExecutionGraph | None] | None:
        row = self._conn.execute("SELECT * FROM checkpoints WHERE id = ?", (row_id,)).fetchone()
        if row is None:
            return None
        return self._decode_row(row)

    def load_latest(self, session_key: str) -> tuple[AgentCheckpoint, ExecutionGraph | None] | None:
        row = self._conn.execute(
            "SELECT * FROM checkpoints WHERE session_key = ? ORDER BY updated_at DESC, id DESC LIMIT 1",
            (session_key,),
        ).fetchone()
        if row is None:
            return None
        return self._decode_row(row)

    def list_recent(self, limit: int = 10) -> list[tuple[AgentCheckpoint, ExecutionGraph | None]]:
        rows = self._conn.execute(
            "SELECT * FROM checkpoints ORDER BY updated_at DESC, id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [self._decode_row(row) for row in rows]

    def delete_old(self, days: int = 7) -> int:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        cur = self._conn.execute("DELETE FROM checkpoints WHERE updated_at < ?", (cutoff,))
        self._conn.commit()
        return int(cur.rowcount)

    def delete_session(self, session_key: str) -> int:
        cur = self._conn.execute("DELETE FROM checkpoints WHERE session_key = ?", (session_key,))
        self._conn.commit()
        return int(cur.rowcount)

    def compact(self, max_per_session: int = 5) -> int:
        rows = self._conn.execute(
            "SELECT id, session_key FROM checkpoints ORDER BY session_key, updated_at DESC, id DESC"
        ).fetchall()
        delete_ids = []
        counts: dict[str, int] = {}
        for row in rows:
            counts[row["session_key"]] = counts.get(row["session_key"], 0) + 1
            if counts[row["session_key"]] > max_per_session:
                delete_ids.append(row["id"])
        if delete_ids:
            placeholders = ", ".join("?" for _ in delete_ids)
            self._conn.execute(f"DELETE FROM checkpoints WHERE id IN ({placeholders})", delete_ids)
            self._conn.commit()
        return len(delete_ids)

    def _decode_row(self, row: sqlite3.Row) -> tuple[AgentCheckpoint, ExecutionGraph | None]:
        checkpoint = AgentCheckpoint.from_dict(json.loads(row["payload"]))
        graph = None
        if row["graph_json"]:
            graph = ExecutionGraph.from_dict(json.loads(row["graph_json"]))
        return (checkpoint, graph)


checkpoint_store = CheckpointStore()
