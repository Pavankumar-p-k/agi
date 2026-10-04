"""SQLite persistence for workflow instances, steps, events, and graphs."""

from __future__ import annotations

import json
import os
import sqlite3
import time
from datetime import datetime

from core.workflow.models import (
    WorkflowInstance,
    WorkflowStatus,
    WorkflowStep,
)


def _wf_to_data(wf: WorkflowInstance) -> str:
    payload = {
        "workflow_id": wf.workflow_id,
        "workflow_type": wf.workflow_type,
        "status": wf.status.value
        if isinstance(wf.status, WorkflowStatus)
        else str(wf.status),
        "execution_context": wf.execution_context,
        "artifacts": wf.artifacts,
        "created_at": wf.created_at.isoformat()
        if isinstance(wf.created_at, datetime)
        else wf.created_at,
        "last_heartbeat": wf.last_heartbeat.isoformat()
        if isinstance(wf.last_heartbeat, datetime)
        else wf.last_heartbeat,
        "current_step": int(wf.current_step or 0),
        "owner": wf.owner,
        "session_id": wf.session_id,
        "retry_budget": int(wf.retry_budget or 0),
        "retry_count": int(wf.retry_count or 0),
        "compensated_steps": list(wf.compensated_steps or []),
    }
    return json.dumps(payload, default=str)


def _wf_from_row(row: sqlite3.Row, steps: list[WorkflowStep]) -> WorkflowInstance:
    data = json.loads(row["data"] or "{}")
    created = data.get("created_at")
    heartbeat = data.get("last_heartbeat")
    status = data.get("status", WorkflowStatus.PENDING.value)
    try:
        wf_status = WorkflowStatus(status)
    except ValueError:
        wf_status = WorkflowStatus.PENDING
    return WorkflowInstance(
        workflow_id=data.get("workflow_id") or row["workflow_id"],
        workflow_type=data.get("workflow_type", ""),
        status=wf_status,
        steps=steps,
        execution_context=data.get("execution_context") or {},
        artifacts=data.get("artifacts") or [],
        created_at=datetime.fromisoformat(created) if created else datetime.utcnow(),
        last_heartbeat=datetime.fromisoformat(heartbeat) if heartbeat else None,
        current_step=int(data.get("current_step", 0) or 0),
        owner=data.get("owner"),
        session_id=data.get("session_id"),
        retry_budget=int(data.get("retry_budget", 0) or 0),
        retry_count=int(data.get("retry_count", 0) or 0),
        compensated_steps=list(data.get("compensated_steps") or []),
    )


class WorkflowStore:
    """Store for workflow instances, their steps, events, and graphs."""

    def __init__(self, db_path: str = "data/workflows.db") -> None:
        self.db_path = db_path
        parent = os.path.dirname(db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        self._conn = sqlite3.connect(db_path, isolation_level=None,
                                     check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS workflow_instances (
                workflow_id TEXT PRIMARY KEY,
                workflow_type TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'PENDING',
                created_at TEXT,
                updated_at REAL,
                data TEXT NOT NULL DEFAULT '{}'
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS workflow_steps (
                step_id TEXT PRIMARY KEY,
                workflow_id TEXT NOT NULL,
                position INTEGER NOT NULL DEFAULT 0,
                data TEXT NOT NULL DEFAULT '{}'
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS workflow_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                workflow_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                data TEXT NOT NULL DEFAULT '{}',
                created_at REAL NOT NULL
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS workflow_graphs (
                goal_id TEXT PRIMARY KEY,
                data TEXT NOT NULL DEFAULT '{}',
                updated_at REAL
            )
            """
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_wf_events_workflow_id "
            "ON workflow_events (workflow_id)"
        )

    # ── Workflows ────────────────────────────────────────────────────

    def create_workflow(self, wf: WorkflowInstance) -> None:
        status = (
            wf.status.value
            if isinstance(wf.status, WorkflowStatus)
            else str(wf.status)
        )
        created = (
            wf.created_at.isoformat()
            if isinstance(wf.created_at, datetime)
            else str(wf.created_at)
        )
        self._conn.execute(
            """
            INSERT INTO workflow_instances
                (workflow_id, workflow_type, status, created_at,
                 updated_at, data)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                wf.workflow_id,
                wf.workflow_type,
                status,
                created,
                time.time(),
                _wf_to_data(wf),
            ),
        )
        for position, step in enumerate(wf.steps):
            self._conn.execute(
                """
                INSERT INTO workflow_steps (step_id, workflow_id, position, data)
                VALUES (?, ?, ?, ?)
                """,
                (step.step_id, wf.workflow_id, position,
                 json.dumps(step.to_dict(), default=str)),
            )

    def get_workflow(self, workflow_id: str) -> WorkflowInstance | None:
        row = self._conn.execute(
            "SELECT * FROM workflow_instances WHERE workflow_id = ?",
            (workflow_id,),
        ).fetchone()
        if row is None:
            return None
        step_rows = self._conn.execute(
            "SELECT data FROM workflow_steps WHERE workflow_id = ? "
            "ORDER BY position ASC",
            (workflow_id,),
        ).fetchall()
        steps = [WorkflowStep.from_dict(json.loads(r["data"] or "{}"))
                 for r in step_rows]
        return _wf_from_row(row, steps)

    def update_workflow(self, wf: WorkflowInstance) -> None:
        status = (
            wf.status.value
            if isinstance(wf.status, WorkflowStatus)
            else str(wf.status)
        )
        self._conn.execute(
            """
            UPDATE workflow_instances
            SET status = ?, updated_at = ?, data = ?
            WHERE workflow_id = ?
            """,
            (status, time.time(), _wf_to_data(wf), wf.workflow_id),
        )

    def update_step(self, step: WorkflowStep) -> None:
        self._conn.execute(
            "UPDATE workflow_steps SET data = ? WHERE step_id = ?",
            (
                json.dumps(step.to_dict(), default=str),
                step.step_id,
            ),
        )

    def get_workflows(
        self, status: WorkflowStatus | str | None = None
    ) -> list[WorkflowInstance]:
        if status is None:
            rows = self._conn.execute(
                "SELECT * FROM workflow_instances ORDER BY created_at ASC"
            ).fetchall()
        else:
            value = (
                status.value if isinstance(status, WorkflowStatus) else str(status)
            )
            rows = self._conn.execute(
                "SELECT * FROM workflow_instances WHERE status = ? "
                "ORDER BY created_at ASC",
                (value,),
            ).fetchall()
        return [self._load_row(row) for row in rows]

    def get_active_workflows(self) -> list[WorkflowInstance]:
        active = {WorkflowStatus.RUNNING.value,
                  WorkflowStatus.COMPENSATING.value}
        rows = self._conn.execute(
            "SELECT * FROM workflow_instances "
            f"WHERE status IN (?, ?) ORDER BY created_at ASC",
            tuple(sorted(active)),
        ).fetchall()
        return [self._load_row(row) for row in rows]

    def list_workflows(self) -> list[WorkflowInstance]:
        return self.get_workflows()

    def _load_row(self, row: sqlite3.Row) -> WorkflowInstance:
        step_rows = self._conn.execute(
            "SELECT data FROM workflow_steps WHERE workflow_id = ? "
            "ORDER BY position ASC",
            (row["workflow_id"],),
        ).fetchall()
        steps = [WorkflowStep.from_dict(json.loads(r["data"] or "{}"))
                 for r in step_rows]
        return _wf_from_row(row, steps)

    # ── Events ───────────────────────────────────────────────────────

    def add_event(
        self, workflow_id: str, event_type: str, data: dict | None = None
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO workflow_events
                (workflow_id, event_type, data, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                workflow_id,
                event_type,
                json.dumps(data or {}, default=str),
                time.time(),
            ),
        )

    def get_events(self, workflow_id: str) -> list:
        rows = self._conn.execute(
            "SELECT * FROM workflow_events WHERE workflow_id = ? "
            "ORDER BY event_id ASC",
            (workflow_id,),
        ).fetchall()
        from core.workflow.events import MJEvent

        events = []
        for row in rows:
            payload = json.loads(row["data"] or "{}")
            event = MJEvent(
                event_type=row["event_type"],
                workflow_id=row["workflow_id"],
                data=payload,
                timestamp=row["created_at"],
            )
            events.append(event)
        return events

    # ── Graphs ───────────────────────────────────────────────────────

    def save_graph(self, graph) -> None:
        goal_id = getattr(graph, "goal_id", "") or ""
        payload = {
            "goal_id": goal_id,
            "goal": getattr(graph, "goal", ""),
            "graph": _graph_to_dict(graph),
        }
        self._conn.execute(
            """
            INSERT INTO workflow_graphs (goal_id, data, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT (goal_id) DO UPDATE SET
                data = excluded.data,
                updated_at = excluded.updated_at
            """,
            (goal_id, json.dumps(payload, default=str), time.time()),
        )

    def load_graph(self, goal_id: str):
        from core.workflow.graph import ExecutionGraph

        row = self._conn.execute(
            "SELECT data FROM workflow_graphs WHERE goal_id = ?",
            (goal_id,),
        ).fetchone()
        if row is None:
            return None
        payload = json.loads(row["data"] or "{}")
        return ExecutionGraph.from_dict(payload.get("graph") or {})

    def list_graphs(self, limit: int = 10) -> list[dict]:
        rows = self._conn.execute(
            "SELECT data FROM workflow_graphs "
            "ORDER BY updated_at DESC LIMIT ?",
            (int(limit),),
        ).fetchall()
        out = []
        for row in rows:
            payload = json.loads(row["data"] or "{}")
            entry = {
                "goal_id": payload.get("goal_id", ""),
                "goal": payload.get("goal", ""),
            }
            graph = payload.get("graph") or {}
            root = graph.get("root") or {}
            entry["status"] = root.get("status", "")
            entry["node_count"] = _count_nodes(root)
            out.append(entry)
        return out

    def close(self) -> None:
        self._conn.close()


def _graph_to_dict(graph) -> dict:
    if hasattr(graph, "to_dict"):
        return graph.to_dict()
    root = getattr(graph, "root", None)
    return {
        "goal_id": getattr(graph, "goal_id", ""),
        "goal": getattr(graph, "goal", ""),
        "root": _node_to_dict(root),
    }


def _node_to_dict(node) -> dict | None:
    if node is None:
        return None
    if hasattr(node, "to_dict"):
        return node.to_dict()
    children = getattr(node, "children", []) or []
    return {
        "label": getattr(node, "label", ""),
        "node_type": getattr(node, "node_type", ""),
        "status": getattr(node, "status", ""),
        "confidence": getattr(node, "confidence", 0.0),
        "estimate_seconds": getattr(node, "estimate_seconds", 0.0),
        "detail": getattr(node, "detail", ""),
        "trust_level": getattr(node, "trust_level", ""),
        "can_skip": getattr(node, "can_skip", False),
        "can_reorder": getattr(node, "can_reorder", False),
        "files": list(getattr(node, "files", []) or []),
        "artifacts": list(getattr(node, "artifacts", []) or []),
        "logs": list(getattr(node, "logs", []) or []),
        "agent_reasoning": getattr(node, "agent_reasoning", ""),
        "error": getattr(node, "error", None),
        "started_at": getattr(node, "started_at", None),
        "completed_at": getattr(node, "completed_at", None),
        "children": [_node_to_dict(c) for c in children],
    }


def _count_nodes(node: dict | None) -> int:
    if not node:
        return 0
    total = 1
    for child in node.get("children") or []:
        total += _count_nodes(child)
    return total
