from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from .schema import AgentCheckpoint
from .graph import ExecutionGraph

logger = logging.getLogger("jarvis.persistence.store")


class CheckpointStore:
    """SQLite-backed persistence store for AgentCheckpoint + ExecutionGraph.

    Uses WAL mode for concurrent read performance and auto-compact
    to keep only the most recent N checkpoints per session.
    """

    def __init__(self, db_path: str = ""):
        if not db_path:
            home = os.path.expanduser("~")
            os.makedirs(os.path.join(home, ".jarvis"), exist_ok=True)
            db_path = os.path.join(home, ".jarvis", "agent_checkpoints.db")
        self._db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self) -> None:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS checkpoints (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_key TEXT NOT NULL,
                    agent_id TEXT DEFAULT '',
                    task TEXT DEFAULT '',
                    checkpoint_data TEXT NOT NULL,
                    graph_data TEXT,
                    version INTEGER DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_checkpoints_session
                ON checkpoints(session_key, created_at DESC)
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS node_checkpoints (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_key TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    node_name TEXT NOT NULL,
                    round_num INTEGER DEFAULT 0,
                    phase TEXT DEFAULT '',
                    checkpoint_data TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_node_checkpoints_run
                ON node_checkpoints(run_id, created_at DESC)
            """)
            conn.commit()
            conn.close()

    def save(
        self,
        checkpoint: AgentCheckpoint,
        graph: Optional[ExecutionGraph] = None,
    ) -> int:
        """Persist a checkpoint. Returns the row id."""
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            cur = conn.execute(
                """INSERT INTO checkpoints
                   (session_key, agent_id, task, checkpoint_data, graph_data,
                    version, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    checkpoint.session_key,
                    checkpoint.agent_id,
                    checkpoint.task,
                    json.dumps(checkpoint.to_dict(), default=str),
                    json.dumps(graph.to_dict(), default=str) if graph else None,
                    checkpoint.version,
                    checkpoint.created_at,
                    checkpoint.updated_at,
                ),
            )
            row_id = cur.lastrowid
            conn.commit()
            conn.close()
            logger.debug("[PERSIST] Saved checkpoint %d for %s", row_id, checkpoint.session_key)
            return row_id

    def load_latest(self, session_key: str) -> Optional[tuple[AgentCheckpoint, Optional[ExecutionGraph]]]:
        """Load the most recent checkpoint for a session."""
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """SELECT * FROM checkpoints
                   WHERE session_key = ?
                   ORDER BY created_at DESC LIMIT 1""",
                (session_key,),
            ).fetchone()
            conn.close()

        if not row:
            return None

        checkpoint = AgentCheckpoint.from_dict(json.loads(row["checkpoint_data"]))
        graph: Optional[ExecutionGraph] = None
        if row["graph_data"]:
            graph = ExecutionGraph.from_dict(json.loads(row["graph_data"]))
        return (checkpoint, graph)

    def load_by_id(self, checkpoint_id: int) -> Optional[tuple[AgentCheckpoint, Optional[ExecutionGraph]]]:
        """Load a specific checkpoint by id."""
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM checkpoints WHERE id = ?", (checkpoint_id,)
            ).fetchone()
            conn.close()

        if not row:
            return None

        checkpoint = AgentCheckpoint.from_dict(json.loads(row["checkpoint_data"]))
        graph: Optional[ExecutionGraph] = None
        if row["graph_data"]:
            graph = ExecutionGraph.from_dict(json.loads(row["graph_data"]))
        return (checkpoint, graph)

    def list_recent(self, limit: int = 20) -> list[dict[str, Any]]:
        """List recent checkpoints with metadata (no full payload)."""
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT id, session_key, agent_id, task, version,
                          created_at, updated_at
                   FROM checkpoints
                   ORDER BY created_at DESC LIMIT ?""",
                (limit,),
            ).fetchall()
            conn.close()

        return [dict(r) for r in rows]

    def delete_old(self, days: int = 7) -> int:
        """Delete checkpoints older than *days*. Returns count removed."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            cur = conn.execute(
                "DELETE FROM checkpoints WHERE created_at < ?", (cutoff,)
            )
            deleted = cur.rowcount
            conn.commit()
            conn.close()

        if deleted:
            logger.info("[PERSIST] GC: removed %d checkpoints older than %d days", deleted, days)
        return deleted

    def delete_session(self, session_key: str) -> int:
        """Delete all checkpoints for a session. Returns count removed."""
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            cur = conn.execute(
                "DELETE FROM checkpoints WHERE session_key = ?", (session_key,)
            )
            deleted = cur.rowcount
            conn.commit()
            conn.close()
        if deleted:
            logger.info("[PERSIST] Removed %d checkpoints for %s", deleted, session_key)
        return deleted

    def compact(self, max_per_session: int = 10) -> int:
        """Keep only the *max_per_session* most recent per session. Returns total removed."""
        total_removed = 0
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            sessions = conn.execute(
                "SELECT DISTINCT session_key FROM checkpoints"
            ).fetchall()
            for (session_key,) in sessions:
                rows = conn.execute(
                    """SELECT id FROM checkpoints
                       WHERE session_key = ?
                       ORDER BY created_at DESC""",
                    (session_key,),
                ).fetchall()
                if len(rows) > max_per_session:
                    ids_to_delete = [r[0] for r in rows[max_per_session:]]
                    if ids_to_delete:
                        placeholders = ",".join("?" * len(ids_to_delete))
                        conn.execute(
                            f"DELETE FROM checkpoints WHERE id IN ({placeholders})",
                            ids_to_delete,
                        )
                        total_removed += len(ids_to_delete)
            conn.commit()
            conn.close()
        if total_removed:
            logger.info("[PERSIST] Compact: removed %d excess checkpoints", total_removed)
        return total_removed

    def save_agent_state(self, state: Any) -> str:
        """Persist a full AgentState snapshot for pause/resume."""
        from core.graph.state import AgentState as _AgentState
        if not isinstance(state, _AgentState):
            raise TypeError("Expected AgentState instance")
        run_id = state.run_id
        data = json.dumps(state.to_dict(), default=str)
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.execute(
                """INSERT INTO node_checkpoints
                   (session_key, run_id, node_name, round_num, phase, checkpoint_data, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (state.session_id or "default", run_id, "agent_state_snapshot",
                 state.round_num, state.phase.name, data, now),
            )
            conn.commit()
            conn.close()
        logger.debug("[PERSIST] Saved AgentState snapshot for run=%s round=%d", run_id, state.round_num)
        return run_id

    def load_agent_state(self, run_id: str):
        """Load the most recent full AgentState snapshot for a run."""
        from core.graph.state import AgentState as _AgentState
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """SELECT * FROM node_checkpoints
                   WHERE run_id = ? AND node_name = 'agent_state_snapshot'
                   ORDER BY created_at DESC LIMIT 1""",
                (run_id,),
            ).fetchone()
            conn.close()
        if not row:
            return None
        data = json.loads(row["checkpoint_data"])
        return _AgentState.from_dict(data)

    def delete_agent_state(self, run_id: str) -> int:
        """Delete all agent state snapshots for a run."""
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            cur = conn.execute(
                """DELETE FROM node_checkpoints
                   WHERE run_id = ? AND node_name = 'agent_state_snapshot'""",
                (run_id,),
            )
            deleted = cur.rowcount
            conn.commit()
            conn.close()
        logger.debug("[PERSIST] Deleted %d state snapshots for run=%s", deleted, run_id)
        return deleted

    def save_node_checkpoint(self, run_id: str, node_name: str, round_num: int, phase: str,
                              session_key: str = "default", metadata: dict | None = None) -> int:
        """Save a lightweight checkpoint at each node boundary."""
        import time as _time
        now = datetime.now(timezone.utc).isoformat()
        data = json.dumps({
            "run_id": run_id,
            "node": node_name,
            "round": round_num,
            "phase": phase,
            "metadata": metadata or {},
            "ts": _time.time(),
        })
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            cur = conn.execute(
                """INSERT INTO node_checkpoints
                   (session_key, run_id, node_name, round_num, phase, checkpoint_data, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (session_key, run_id, node_name, round_num, phase, data, now),
            )
            row_id = cur.lastrowid
            conn.commit()
            conn.close()
        logger.debug("[PERSIST] Saved node checkpoint %d: %s/%s round=%d", row_id, run_id, node_name, round_num)
        return row_id

    def load_latest_node(self, run_id: str) -> dict | None:
        """Load the most recent node checkpoint for a run (pause/resume)."""
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """SELECT * FROM node_checkpoints
                   WHERE run_id = ?
                   ORDER BY created_at DESC LIMIT 1""",
                (run_id,),
            ).fetchone()
            conn.close()
        if not row:
            return None
        return dict(row)

    @property
    def db_path(self) -> str:
        return self._db_path


checkpoint_store = CheckpointStore()
