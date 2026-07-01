"""ActivityStore — SQLite-backed persistence for the activity graph.

Lives in the same database as workflows (data/workflows.db) so
activity nodes can directly reference workflow_ids, artifact_ids,
and context_ids without cross-database joins.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from core.activity.models import ActivityEdge, ActivityNode, ActivityStatus, NODE_TYPES, EDGE_TYPES

logger = logging.getLogger(__name__)

_DEFAULT_DB = str(Path("data") / "workflow.db")


class ActivityStore:
    """Persistent activity graph storage.

    Creates activity_nodes and activity_edges tables alongside
    the existing workflow_* tables in the same SQLite database.

    Thread-safe via reentrant lock (same pattern as WorkflowStore).
    """

    def __init__(self, db_path: str | None = None, auto_prune_hours: int | None = None):
        self._db_path = db_path or _DEFAULT_DB
        self._lock = threading.Lock()
        self._init_db()
        if auto_prune_hours is not None or auto_prune_hours != 0:
            self.prune_stale_running(hours=auto_prune_hours or 24)

    @property
    def db_path(self) -> str:
        return self._db_path

    def _init_db(self) -> None:
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS activity_nodes (
                    node_id TEXT PRIMARY KEY,
                    parent_id TEXT,
                    activity_id TEXT NOT NULL,
                    node_type TEXT NOT NULL,
                    label TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'PENDING',
                    depth INTEGER NOT NULL DEFAULT 0,
                    agent_id TEXT,
                    origin_node_id TEXT,
                    input_json TEXT DEFAULT '{}',
                    output_json TEXT DEFAULT '{}',
                    artifacts_json TEXT DEFAULT '{}',
                    workflow_id TEXT,
                    started_at TEXT,
                    completed_at TEXT,
                    metadata_json TEXT DEFAULT '{}',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS activity_edges (
                    edge_id TEXT PRIMARY KEY,
                    from_node_id TEXT NOT NULL,
                    to_node_id TEXT NOT NULL,
                    edge_type TEXT NOT NULL DEFAULT 'depends_on',
                    metadata_json TEXT DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (from_node_id) REFERENCES activity_nodes(node_id),
                    FOREIGN KEY (to_node_id) REFERENCES activity_nodes(node_id)
                );

                CREATE INDEX IF NOT EXISTS idx_activity_nodes_activity
                    ON activity_nodes(activity_id);
                CREATE INDEX IF NOT EXISTS idx_activity_nodes_status
                    ON activity_nodes(status);
                CREATE INDEX IF NOT EXISTS idx_activity_nodes_agent
                    ON activity_nodes(agent_id);
                CREATE INDEX IF NOT EXISTS idx_activity_edges_from
                    ON activity_edges(from_node_id);
                CREATE INDEX IF NOT EXISTS idx_activity_edges_to
                    ON activity_edges(to_node_id);
                CREATE INDEX IF NOT EXISTS idx_activity_edges_type
                    ON activity_edges(edge_type);
            """)

    # ── Node CRUD ───────────────────────────────────────────────────────────

    def create_node(self, node: ActivityNode) -> ActivityNode:
        node.created_at = node.created_at or datetime.utcnow()
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """INSERT INTO activity_nodes
                   (node_id, parent_id, activity_id, node_type, label, status, depth,
                    agent_id, origin_node_id, input_json, output_json, artifacts_json,
                    workflow_id, started_at, completed_at, metadata_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    node.node_id, node.parent_id, node.activity_id,
                    node.node_type, node.label, node.status.value, node.depth,
                    node.agent_id, node.origin_node_id,
                    json.dumps(node.input), json.dumps(node.output),
                    json.dumps(node.artifacts),
                    node.workflow_id,
                    _dt(node.started_at), _dt(node.completed_at),
                    json.dumps(node.metadata), _dt(node.created_at),
                ),
            )
        return node

    def get_node(self, node_id: str) -> ActivityNode | None:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM activity_nodes WHERE node_id=?", (node_id,)
            ).fetchone()
            if row is None:
                return None
            return _row_to_node(row)

    def update_node(self, node: ActivityNode) -> None:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """UPDATE activity_nodes SET
                   status=?, label=?, agent_id=?, origin_node_id=?,
                   input_json=?, output_json=?, artifacts_json=?,
                   workflow_id=?, started_at=?, completed_at=?, metadata_json=?
                   WHERE node_id=?""",
                (
                    node.status.value, node.label, node.agent_id, node.origin_node_id,
                    json.dumps(node.input), json.dumps(node.output),
                    json.dumps(node.artifacts),
                    node.workflow_id,
                    _dt(node.started_at), _dt(node.completed_at),
                    json.dumps(node.metadata),
                    node.node_id,
                ),
            )

    def delete_node(self, node_id: str) -> None:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute("DELETE FROM activity_edges WHERE from_node_id=? OR to_node_id=?",
                         (node_id, node_id))
            conn.execute("DELETE FROM activity_nodes WHERE node_id=?", (node_id,))

    # ── Edge CRUD ───────────────────────────────────────────────────────────

    def create_edge(self, edge: ActivityEdge) -> ActivityEdge:
        edge.created_at = edge.created_at or datetime.utcnow()
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """INSERT INTO activity_edges
                   (edge_id, from_node_id, to_node_id, edge_type, metadata_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    edge.edge_id, edge.from_node_id, edge.to_node_id,
                    edge.edge_type, json.dumps(edge.metadata), _dt(edge.created_at),
                ),
            )
        return edge

    def get_edges(self, node_id: str) -> list[ActivityEdge]:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT * FROM activity_edges
                   WHERE from_node_id=? OR to_node_id=?
                   ORDER BY created_at""",
                (node_id, node_id),
            ).fetchall()
            return [_row_to_edge(r) for r in rows]

    def get_outgoing_edges(self, node_id: str) -> list[ActivityEdge]:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT * FROM activity_edges WHERE from_node_id=?
                   ORDER BY created_at""",
                (node_id,),
            ).fetchall()
            return [_row_to_edge(r) for r in rows]

    def get_incoming_edges(self, node_id: str) -> list[ActivityEdge]:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT * FROM activity_edges WHERE to_node_id=?
                   ORDER BY created_at""",
                (node_id,),
            ).fetchall()
            return [_row_to_edge(r) for r in rows]

    def delete_edge(self, edge_id: str) -> None:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute("DELETE FROM activity_edges WHERE edge_id=?", (edge_id,))

    # ── Queries ─────────────────────────────────────────────────────────────

    def get_activity_tree(self, activity_id: str) -> list[ActivityNode]:
        """Return all nodes in an activity tree, ordered by depth."""
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT * FROM activity_nodes
                   WHERE activity_id=?
                   ORDER BY depth ASC, created_at ASC""",
                (activity_id,),
            ).fetchall()
            return [_row_to_node(r) for r in rows]

    def get_activity_timeline(self, activity_id: str) -> list[ActivityNode]:
        """Return all nodes chronologically."""
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT * FROM activity_nodes
                   WHERE activity_id=?
                   ORDER BY COALESCE(started_at, created_at) ASC""",
                (activity_id,),
            ).fetchall()
            return [_row_to_node(r) for r in rows]

    def get_active_activities(self) -> list[ActivityNode]:
        """Return root (depth=0) nodes that are not terminal."""
        non_terminal = [
            s.value for s in ActivityStatus
            if s not in (ActivityStatus.COMPLETED, ActivityStatus.FAILED,
                         ActivityStatus.CANCELLED)
        ]
        placeholders = ",".join("?" for _ in non_terminal)
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                f"""SELECT * FROM activity_nodes
                    WHERE depth=0 AND status IN ({placeholders})
                    ORDER BY created_at DESC""",
                non_terminal,
            ).fetchall()
            return [_row_to_node(r) for r in rows]

    def get_incomplete_leaves(self, activity_id: str) -> list[ActivityNode]:
        """Return nodes that are incomplete and have no incomplete children.

        A node is an "incomplete leaf" when:
        - Its status is PENDING, RUNNING, or SUSPENDED
        - It has no children that are also PENDING, RUNNING, or SUSPENDED

        This correctly handles the case where all children are COMPLETED/FAILED
        but the parent hasn't been marked done yet.
        """
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT * FROM activity_nodes
                   WHERE activity_id=?
                     AND status IN ('PENDING', 'RUNNING', 'SUSPENDED')
                     AND node_id NOT IN (
                       SELECT DISTINCT parent_id FROM activity_nodes
                       WHERE parent_id IS NOT NULL
                         AND status IN ('PENDING', 'RUNNING', 'SUSPENDED')
                     )
                   ORDER BY depth ASC, created_at ASC""",
                (activity_id,),
            ).fetchall()
            return [_row_to_node(r) for r in rows]

    def get_nodes_by_agent(self, agent_id: str, limit: int = 50) -> list[ActivityNode]:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT * FROM activity_nodes
                   WHERE agent_id=?
                   ORDER BY created_at DESC LIMIT ?""",
                (agent_id, limit),
            ).fetchall()
            return [_row_to_node(r) for r in rows]

    def get_nodes_by_type(self, node_type: str,
                           activity_id: str | None = None,
                           limit: int = 100) -> list[ActivityNode]:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            if activity_id:
                rows = conn.execute(
                    """SELECT * FROM activity_nodes
                       WHERE node_type=? AND activity_id=?
                       ORDER BY created_at DESC LIMIT ?""",
                    (node_type, activity_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT * FROM activity_nodes
                       WHERE node_type=?
                       ORDER BY created_at DESC LIMIT ?""",
                    (node_type, limit),
                ).fetchall()
            return [_row_to_node(r) for r in rows]

    def count_by_status(self, activity_id: str) -> dict[str, int]:
        """Return counts of nodes per status for an activity."""
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT status, COUNT(*) as cnt FROM activity_nodes
                   WHERE activity_id=?
                   GROUP BY status""",
                (activity_id,),
            ).fetchall()
            return {r["status"]: r["cnt"] for r in rows}

    def search_nodes(self, query: str, limit: int = 20) -> list[ActivityNode]:
        """Search nodes by label (LIKE match)."""
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT * FROM activity_nodes
                   WHERE label LIKE ?
                   ORDER BY created_at DESC LIMIT ?""",
                (f"%{query}%", limit),
            ).fetchall()
            return [_row_to_node(r) for r in rows]


    def prune_stale_running(self, hours: int = 24) -> int:
        """Mark nodes stuck in RUNNING/PENDING older than `hours` as FAILED.

        Returns count of nodes pruned.  Safe to call at startup — only
        affects nodes with no update for the threshold duration.
        Gracefully handles :memory: databases or missing tables.
        """
        import json as _json
        from datetime import datetime, timedelta, timezone
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        error_json = _json.dumps({"error": f"Stale - no update for >{hours}h"})
        try:
            with self._lock, sqlite3.connect(self._db_path) as conn:
                cur = conn.execute(
                    """UPDATE activity_nodes SET
                         status='FAILED',
                         completed_at=datetime('now'),
                         output_json=?
                       WHERE status IN ('RUNNING','PENDING')
                         AND created_at < ?""",
                    (error_json, cutoff),
                )
                pruned = cur.rowcount
                if pruned:
                    logger.warning("Pruned %d stale RUNNING/PENDING activities (>%dh)", pruned, hours)
                return pruned
        except sqlite3.OperationalError:
            return 0

# ── Serialization helpers ──────────────────────────────────────────────────

def _dt(d: datetime | None) -> str | None:
    return d.isoformat() if d else None


def _parse_dt(s: str | None) -> datetime | None:
    return datetime.fromisoformat(s) if s else None


def _row_to_node(row: sqlite3.Row) -> ActivityNode:
    return ActivityNode(
        node_id=row["node_id"],
        parent_id=row["parent_id"],
        activity_id=row["activity_id"],
        node_type=row["node_type"],
        label=row["label"],
        status=ActivityStatus(row["status"]),
        depth=row["depth"],
        agent_id=row["agent_id"],
        origin_node_id=row["origin_node_id"],
        input=json.loads(row["input_json"]),
        output=json.loads(row["output_json"]),
        artifacts=json.loads(row["artifacts_json"]),
        workflow_id=row["workflow_id"],
        started_at=_parse_dt(row["started_at"]),
        completed_at=_parse_dt(row["completed_at"]),
        metadata=json.loads(row["metadata_json"]),
        created_at=_parse_dt(row["created_at"]),
    )


def _row_to_edge(row: sqlite3.Row) -> ActivityEdge:
    return ActivityEdge(
        edge_id=row["edge_id"],
        from_node_id=row["from_node_id"],
        to_node_id=row["to_node_id"],
        edge_type=row["edge_type"],
        metadata=json.loads(row["metadata_json"]),
        created_at=_parse_dt(row["created_at"]),
    )
