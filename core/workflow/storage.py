from __future__ import annotations

import json
import logging
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from core.workflow.events import WorkflowEvent
from core.workflow.models import StepStatus, WorkflowInstance, WorkflowStatus, WorkflowStep

logger = logging.getLogger(__name__)


class WorkflowStore:
    def __init__(self, db_path: str | None = None) -> None:
        if db_path is None:
            db_path = str(Path("data") / "workflow.db")
        self._db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self) -> None:
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS workflow_instances (
                    workflow_id TEXT PRIMARY KEY,
                    workflow_type TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'PENDING',
                    current_step INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    session_id TEXT NOT NULL DEFAULT '',
                    owner TEXT NOT NULL DEFAULT '',
                    timeout_seconds INTEGER,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    parent_workflow_id TEXT,
                    workflow_version INTEGER NOT NULL DEFAULT 1,
                    execution_context TEXT DEFAULT '{}',
                    artifacts TEXT DEFAULT '[]'
                );

                CREATE TABLE IF NOT EXISTS workflow_steps (
                    step_id TEXT PRIMARY KEY,
                    workflow_id TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    tool_name TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'PENDING',
                    started_at TEXT,
                    completed_at TEXT,
                    input_data TEXT DEFAULT '{}',
                    output_data TEXT DEFAULT '{}',
                    error TEXT,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    timeout_seconds INTEGER,
                    max_retries INTEGER NOT NULL DEFAULT 3,
                    FOREIGN KEY (workflow_id) REFERENCES workflow_instances(workflow_id)
                );

                CREATE TABLE IF NOT EXISTS workflow_events (
                    event_id TEXT PRIMARY KEY,
                    workflow_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    data TEXT DEFAULT '{}',
                    timestamp TEXT NOT NULL,
                    FOREIGN KEY (workflow_id) REFERENCES workflow_instances(workflow_id)
                );

                CREATE INDEX IF NOT EXISTS idx_workflow_steps_workflow
                    ON workflow_steps(workflow_id);
                CREATE INDEX IF NOT EXISTS idx_workflow_events_workflow
                    ON workflow_events(workflow_id);
                CREATE INDEX IF NOT EXISTS idx_workflow_instances_status
                    ON workflow_instances(status);
            """)

    def create_workflow(self, wf: WorkflowInstance) -> WorkflowInstance:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """INSERT INTO workflow_instances
                   (workflow_id, workflow_type, status, current_step,
                    created_at, updated_at, session_id, owner,
                    timeout_seconds, retry_count, parent_workflow_id,
                    workflow_version, execution_context, artifacts)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    wf.workflow_id, wf.workflow_type, wf.status.value, wf.current_step,
                    _dt(wf.created_at), _dt(wf.updated_at), wf.session_id, wf.owner,
                    wf.timeout_seconds, wf.retry_count, wf.parent_workflow_id,
                    wf.workflow_version, json.dumps(wf.execution_context),
                    json.dumps(wf.artifacts),
                ),
            )
            for step in wf.steps:
                conn.execute(
                    """INSERT INTO workflow_steps
                       (step_id, workflow_id, idempotency_key, tool_name,
                        status, started_at, completed_at, input_data,
                        output_data, error, retry_count, timeout_seconds, max_retries)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        step.step_id, wf.workflow_id, step.idempotency_key, step.tool_name,
                        step.status.value, _dt(step.started_at), _dt(step.completed_at),
                        json.dumps(step.input_data), json.dumps(step.output_data),
                        step.error, step.retry_count, step.timeout_seconds, step.max_retries,
                    ),
                )
        return wf

    def update_workflow(self, wf: WorkflowInstance) -> None:
        wf.updated_at = datetime.utcnow()
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """UPDATE workflow_instances SET
                   status=?, current_step=?, updated_at=?, retry_count=?,
                   execution_context=?, artifacts=?
                   WHERE workflow_id=?""",
                (
                    wf.status.value, wf.current_step, _dt(wf.updated_at),
                    wf.retry_count, json.dumps(wf.execution_context),
                    json.dumps(wf.artifacts), wf.workflow_id,
                ),
            )

    def update_step(self, step: WorkflowStep) -> None:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """UPDATE workflow_steps SET
                   status=?, started_at=?, completed_at=?, output_data=?,
                   error=?, retry_count=?
                   WHERE step_id=?""",
                (
                    step.status.value, _dt(step.started_at), _dt(step.completed_at),
                    json.dumps(step.output_data), step.error, step.retry_count,
                    step.step_id,
                ),
            )

    def get_workflow(self, workflow_id: str) -> WorkflowInstance | None:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM workflow_instances WHERE workflow_id=?", (workflow_id,)
            ).fetchone()
            if row is None:
                return None
            wf = _row_to_workflow(row)
            step_rows = conn.execute(
                "SELECT * FROM workflow_steps WHERE workflow_id=? ORDER BY step_id",
                (workflow_id,),
            ).fetchall()
            wf.steps = [_row_to_step(r) for r in step_rows]
            return wf

    def list_workflows(self, status: str | None = None, limit: int = 50) -> list[WorkflowInstance]:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            if status:
                rows = conn.execute(
                    "SELECT * FROM workflow_instances WHERE status=? ORDER BY created_at DESC LIMIT ?",
                    (status, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM workflow_instances ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            results = []
            for row in rows:
                wf = _row_to_workflow(row)
                step_rows = conn.execute(
                    "SELECT * FROM workflow_steps WHERE workflow_id=? ORDER BY step_id",
                    (wf.workflow_id,),
                ).fetchall()
                wf.steps = [_row_to_step(r) for r in step_rows]
                results.append(wf)
            return results

    def list_active_workflows(self) -> list[WorkflowInstance]:
        return self.list_workflows(status=WorkflowStatus.RUNNING.value)

    def append_event(self, event: WorkflowEvent) -> None:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """INSERT INTO workflow_events
                   (event_id, workflow_id, event_type, data, timestamp)
                   VALUES (?, ?, ?, ?, ?)""",
                (event.event_id, event.workflow_id, event.event_type,
                 json.dumps(event.data), _dt(event.timestamp)),
            )

    def get_events(self, workflow_id: str, limit: int = 100) -> list[WorkflowEvent]:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM workflow_events WHERE workflow_id=? ORDER BY timestamp LIMIT ?",
                (workflow_id, limit),
            ).fetchall()
            return [
                WorkflowEvent(
                    event_id=r["event_id"], workflow_id=r["workflow_id"],
                    event_type=r["event_type"], data=json.loads(r["data"]),
                    timestamp=_parse_dt(r["timestamp"]),
                )
                for r in rows
            ]


def _dt(d: datetime | None) -> str | None:
    return d.isoformat() if d else None


def _parse_dt(s: str | None) -> datetime | None:
    return datetime.fromisoformat(s) if s else None


def _row_to_workflow(row: sqlite3.Row) -> WorkflowInstance:
    return WorkflowInstance(
        workflow_id=row["workflow_id"],
        workflow_type=row["workflow_type"],
        status=WorkflowStatus(row["status"]),
        current_step=row["current_step"],
        created_at=_parse_dt(row["created_at"]),
        updated_at=_parse_dt(row["updated_at"]),
        session_id=row["session_id"],
        owner=row["owner"],
        timeout_seconds=row["timeout_seconds"],
        retry_count=row["retry_count"],
        parent_workflow_id=row["parent_workflow_id"],
        workflow_version=row["workflow_version"],
        execution_context=json.loads(row["execution_context"]),
        artifacts=json.loads(row["artifacts"]),
    )


def _row_to_step(row: sqlite3.Row) -> WorkflowStep:
    return WorkflowStep(
        step_id=row["step_id"],
        idempotency_key=row["idempotency_key"],
        tool_name=row["tool_name"],
        status=StepStatus(row["status"]),
        started_at=_parse_dt(row["started_at"]),
        completed_at=_parse_dt(row["completed_at"]),
        input_data=json.loads(row["input_data"]),
        output_data=json.loads(row["output_data"]),
        error=row["error"],
        retry_count=row["retry_count"],
        timeout_seconds=row["timeout_seconds"],
        max_retries=row["max_retries"],
    )
