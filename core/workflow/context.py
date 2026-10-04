"""ExecutionContext persistence through the workflow store."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field


@dataclass
class ExecutionContext:
    """Per-workflow execution state shared with tools."""

    workflow_id: str = ""
    owner: str | None = None
    session_id: str | None = None
    variables: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)
    artifacts: dict = field(default_factory=dict)


class ContextManager:
    """SQLite-backed lifecycle for ExecutionContext objects."""

    def __init__(self, store) -> None:
        self._store = store
        self._conn = store._conn
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS workflow_contexts (
                workflow_id TEXT PRIMARY KEY,
                owner TEXT,
                session_id TEXT,
                variables TEXT NOT NULL DEFAULT '{}',
                metadata TEXT NOT NULL DEFAULT '{}',
                artifacts TEXT NOT NULL DEFAULT '{}',
                updated_at REAL NOT NULL
            )
            """
        )

    def create_context(
        self,
        workflow_id: str,
        owner: str | None = None,
        session_id: str | None = None,
        variables: dict | None = None,
        metadata: dict | None = None,
        artifacts: dict | None = None,
    ) -> ExecutionContext:
        ctx = ExecutionContext(
            workflow_id=workflow_id,
            owner=owner,
            session_id=session_id,
            variables=dict(variables or {}),
            metadata=dict(metadata or {}),
            artifacts=dict(artifacts or {}),
        )
        self._conn.execute(
            """
            INSERT INTO workflow_contexts
                (workflow_id, owner, session_id, variables, metadata,
                 artifacts, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (workflow_id) DO UPDATE SET
                owner = excluded.owner,
                session_id = excluded.session_id,
                variables = excluded.variables,
                metadata = excluded.metadata,
                artifacts = excluded.artifacts,
                updated_at = excluded.updated_at
            """,
            (
                ctx.workflow_id,
                ctx.owner,
                ctx.session_id,
                json.dumps(ctx.variables, default=str),
                json.dumps(ctx.metadata, default=str),
                json.dumps(ctx.artifacts, default=str),
                time.time(),
            ),
        )
        return ctx

    def get_context(self, workflow_id: str) -> ExecutionContext | None:
        row = self._conn.execute(
            "SELECT * FROM workflow_contexts WHERE workflow_id = ?",
            (workflow_id,),
        ).fetchone()
        if row is None:
            return None
        return ExecutionContext(
            workflow_id=row["workflow_id"],
            owner=row["owner"],
            session_id=row["session_id"],
            variables=json.loads(row["variables"] or "{}"),
            metadata=json.loads(row["metadata"] or "{}"),
            artifacts=json.loads(row["artifacts"] or "{}"),
        )

    def update_context(self, ctx: ExecutionContext) -> None:
        self._conn.execute(
            """
            UPDATE workflow_contexts
            SET owner = ?, session_id = ?, variables = ?, metadata = ?,
                artifacts = ?, updated_at = ?
            WHERE workflow_id = ?
            """,
            (
                ctx.owner,
                ctx.session_id,
                json.dumps(ctx.variables, default=str),
                json.dumps(ctx.metadata, default=str),
                json.dumps(ctx.artifacts, default=str),
                time.time(),
                ctx.workflow_id,
            ),
        )

    def delete_context(self, workflow_id: str) -> None:
        self._conn.execute(
            "DELETE FROM workflow_contexts WHERE workflow_id = ?",
            (workflow_id,),
        )
