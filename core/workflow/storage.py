from __future__ import annotations

import json
import logging
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from core.workflow.context import ExecutionContext
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
                    last_heartbeat TEXT NOT NULL,
                    session_id TEXT NOT NULL DEFAULT '',
                    owner TEXT NOT NULL DEFAULT '',
                    timeout_seconds INTEGER,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    retry_budget INTEGER NOT NULL DEFAULT 0,
                    parent_workflow_id TEXT,
                    workflow_version INTEGER NOT NULL DEFAULT 1,
                    execution_context TEXT DEFAULT '{}',
                    artifacts TEXT DEFAULT '[]',
                    compensated_steps TEXT DEFAULT '[]'
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
                    compensation_tool TEXT,
                    compensation_data TEXT DEFAULT '{}',
                    compensated INTEGER NOT NULL DEFAULT 0,
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

                CREATE TABLE IF NOT EXISTS workflow_contexts (
                    workflow_id TEXT PRIMARY KEY,
                    owner TEXT NOT NULL DEFAULT '',
                    session_id TEXT NOT NULL DEFAULT '',
                    variables_json TEXT DEFAULT '{}',
                    artifacts_json TEXT DEFAULT '{}',
                    metadata_json TEXT DEFAULT '{}',
                    created_at TEXT,
                    updated_at TEXT,
                    FOREIGN KEY (workflow_id) REFERENCES workflow_instances(workflow_id)
                );

                CREATE TABLE IF NOT EXISTS workflow_artifacts (
                    artifact_id TEXT PRIMARY KEY,
                    workflow_id TEXT NOT NULL,
                    name TEXT,
                    artifact_type TEXT,
                    path TEXT,
                    size_bytes INTEGER,
                    checksum TEXT,
                    metadata_json TEXT DEFAULT '{}',
                    created_at TEXT,
                    FOREIGN KEY (workflow_id) REFERENCES workflow_instances(workflow_id)
                );

                CREATE INDEX IF NOT EXISTS idx_workflow_artifacts_workflow
                    ON workflow_artifacts(workflow_id);
            """)
            # Migrate existing databases — add columns if missing
            migrations = [
                "ALTER TABLE workflow_instances ADD COLUMN compensated_steps TEXT DEFAULT '[]'",
                "ALTER TABLE workflow_instances ADD COLUMN retry_budget INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE workflow_steps ADD COLUMN compensation_tool TEXT",
                "ALTER TABLE workflow_steps ADD COLUMN compensation_data TEXT DEFAULT '{}'",
                "ALTER TABLE workflow_steps ADD COLUMN compensated INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE workflow_contexts ADD COLUMN artifacts_json TEXT DEFAULT '{}'",
            ]
            for sql in migrations:
                try:
                    conn.execute(sql)
                except Exception:
                    pass

    def create_workflow(self, wf: WorkflowInstance) -> WorkflowInstance:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """INSERT INTO workflow_instances
                   (workflow_id, workflow_type, status, current_step,
                    created_at, updated_at, last_heartbeat, session_id, owner,
                    timeout_seconds, retry_count, retry_budget, parent_workflow_id,
                    workflow_version, execution_context, artifacts, compensated_steps)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    wf.workflow_id, wf.workflow_type, wf.status.value, wf.current_step,
                    _dt(wf.created_at), _dt(wf.updated_at), _dt(wf.last_heartbeat),
                    wf.session_id, wf.owner,
                    wf.timeout_seconds, wf.retry_count, wf.retry_budget,
                    wf.parent_workflow_id,
                    wf.workflow_version, json.dumps(wf.execution_context),
                    json.dumps(wf.artifacts), json.dumps(wf.compensated_steps),
                ),
            )
            for step in wf.steps:
                conn.execute(
                    """INSERT INTO workflow_steps
                       (step_id, workflow_id, idempotency_key, tool_name,
                        status, started_at, completed_at, input_data,
                        output_data, error, retry_count, timeout_seconds, max_retries,
                        compensation_tool, compensation_data, compensated)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        step.step_id, wf.workflow_id, step.idempotency_key, step.tool_name,
                        step.status.value, _dt(step.started_at), _dt(step.completed_at),
                        json.dumps(step.input_data), json.dumps(step.output_data),
                        step.error, step.retry_count, step.timeout_seconds, step.max_retries,
                        step.compensation_tool, json.dumps(step.compensation_data),
                        1 if step.compensated else 0,
                    ),
                )
        return wf

    def update_workflow(self, wf: WorkflowInstance) -> None:
        wf.updated_at = datetime.utcnow()
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """UPDATE workflow_instances SET
                   status=?, current_step=?, updated_at=?, last_heartbeat=?,
                   retry_count=?, execution_context=?, artifacts=?, compensated_steps=?
                   WHERE workflow_id=?""",
                (
                    wf.status.value, wf.current_step, _dt(wf.updated_at),
                    _dt(wf.last_heartbeat), wf.retry_count,
                    json.dumps(wf.execution_context),
                    json.dumps(wf.artifacts), json.dumps(wf.compensated_steps),
                    wf.workflow_id,
                ),
            )

    def update_step(self, step: WorkflowStep) -> None:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """UPDATE workflow_steps SET
                   status=?, started_at=?, completed_at=?, output_data=?,
                   error=?, retry_count=?, compensated=?
                   WHERE step_id=?""",
                (
                    step.status.value, _dt(step.started_at), _dt(step.completed_at),
                    json.dumps(step.output_data), step.error, step.retry_count,
                    1 if step.compensated else 0, step.step_id,
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

    def list_compensating_workflows(self) -> list[WorkflowInstance]:
        return self.list_workflows(status=WorkflowStatus.COMPENSATING.value)

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


    # ── Context CRUD ──────────────────────────────────────────────────────

    def create_context(self, ctx: ExecutionContext) -> ExecutionContext:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """INSERT INTO workflow_contexts
                   (workflow_id, owner, session_id, variables_json, artifacts_json, metadata_json, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (ctx.workflow_id, ctx.owner, ctx.session_id,
                 json.dumps(ctx.variables), json.dumps(ctx.artifacts),
                 json.dumps(ctx.metadata),
                 _dt(ctx.created_at), _dt(ctx.updated_at)),
            )
        return ctx

    def get_context(self, workflow_id: str) -> ExecutionContext | None:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM workflow_contexts WHERE workflow_id=?", (workflow_id,)
            ).fetchone()
            if row is None:
                return None
            return ExecutionContext(
                workflow_id=row["workflow_id"],
                owner=row["owner"],
                session_id=row["session_id"],
                variables=json.loads(row["variables_json"]),
                artifacts=json.loads(row["artifacts_json"]),
                metadata=json.loads(row["metadata_json"]),
                created_at=_parse_dt(row["created_at"]),
                updated_at=_parse_dt(row["updated_at"]),
            )

    def update_context(self, ctx: ExecutionContext) -> None:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """UPDATE workflow_contexts SET
                   variables_json=?, artifacts_json=?, metadata_json=?, updated_at=?
                   WHERE workflow_id=?""",
                (json.dumps(ctx.variables), json.dumps(ctx.artifacts),
                 json.dumps(ctx.metadata),
                 _dt(ctx.updated_at), ctx.workflow_id),
            )

    def delete_context(self, workflow_id: str) -> None:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "DELETE FROM workflow_contexts WHERE workflow_id=?", (workflow_id,)
            )

    # ── Artifact CRUD ─────────────────────────────────────────────────────

    def create_artifact(self, ref: "ArtifactRef") -> "ArtifactRef":
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """INSERT INTO workflow_artifacts
                   (artifact_id, workflow_id, name, artifact_type, path,
                    size_bytes, checksum, metadata_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (ref.artifact_id, ref.workflow_id, ref.name, ref.artifact_type,
                 ref.path, ref.size_bytes, ref.checksum,
                 json.dumps(ref.metadata), _dt(ref.created_at)),
            )
        return ref

    def get_artifact(self, artifact_id: str) -> "ArtifactRef | None":
        from core.workflow.artifact_store import ArtifactRef

        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM workflow_artifacts WHERE artifact_id=?", (artifact_id,)
            ).fetchone()
            if row is None:
                return None
            return ArtifactRef(
                artifact_id=row["artifact_id"],
                workflow_id=row["workflow_id"],
                name=row["name"],
                artifact_type=row["artifact_type"],
                path=row["path"],
                size_bytes=row["size_bytes"],
                checksum=row["checksum"],
                metadata=json.loads(row["metadata_json"]),
                created_at=_parse_dt(row["created_at"]),
            )

    def list_artifacts(self, workflow_id: str) -> "list[ArtifactRef]":
        from core.workflow.artifact_store import ArtifactRef

        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM workflow_artifacts WHERE workflow_id=? ORDER BY created_at",
                (workflow_id,),
            ).fetchall()
            return [
                ArtifactRef(
                    artifact_id=r["artifact_id"],
                    workflow_id=r["workflow_id"],
                    name=r["name"],
                    artifact_type=r["artifact_type"],
                    path=r["path"],
                    size_bytes=r["size_bytes"],
                    checksum=r["checksum"],
                    metadata=json.loads(r["metadata_json"]),
                    created_at=_parse_dt(r["created_at"]),
                )
                for r in rows
            ]

    def list_all_artifacts(self) -> "list[ArtifactRef]":
        from core.workflow.artifact_store import ArtifactRef

        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM workflow_artifacts ORDER BY created_at DESC"
            ).fetchall()
            return [
                ArtifactRef(
                    artifact_id=r["artifact_id"],
                    workflow_id=r["workflow_id"],
                    name=r["name"],
                    artifact_type=r["artifact_type"],
                    path=r["path"],
                    size_bytes=r["size_bytes"],
                    checksum=r["checksum"],
                    metadata=json.loads(r["metadata_json"]),
                    created_at=_parse_dt(r["created_at"]),
                )
                for r in rows
            ]

    def search_artifacts(self, query: str) -> "list[ArtifactRef]":
        from core.workflow.artifact_store import ArtifactRef

        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            like = f"%{query}%"
            rows = conn.execute(
                """SELECT * FROM workflow_artifacts
                   WHERE name LIKE ? OR artifact_type LIKE ? OR path LIKE ?
                   ORDER BY created_at DESC""",
                (like, like, like),
            ).fetchall()
            return [
                ArtifactRef(
                    artifact_id=r["artifact_id"],
                    workflow_id=r["workflow_id"],
                    name=r["name"],
                    artifact_type=r["artifact_type"],
                    path=r["path"],
                    size_bytes=r["size_bytes"],
                    checksum=r["checksum"],
                    metadata=json.loads(r["metadata_json"]),
                    created_at=_parse_dt(r["created_at"]),
                )
                for r in rows
            ]

    def delete_artifact(self, artifact_id: str) -> None:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "DELETE FROM workflow_artifacts WHERE artifact_id=?", (artifact_id,)
            )


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
        last_heartbeat=_parse_dt(row["last_heartbeat"]),
        session_id=row["session_id"],
        owner=row["owner"],
        timeout_seconds=row["timeout_seconds"],
        retry_count=row["retry_count"],
        retry_budget=row["retry_budget"],
        parent_workflow_id=row["parent_workflow_id"],
        workflow_version=row["workflow_version"],
        execution_context=json.loads(row["execution_context"]),
        artifacts=json.loads(row["artifacts"]),
        compensated_steps=json.loads(row["compensated_steps"]),
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
        compensation_tool=row["compensation_tool"],
        compensation_data=json.loads(row["compensation_data"]),
        compensated=bool(row["compensated"]),
    )
