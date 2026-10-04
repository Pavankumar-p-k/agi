"""Artifact registration and retrieval for workflow runs."""

from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from dataclasses import dataclass, field


@dataclass
class ArtifactRef:
    """Reference to an artifact produced by a workflow."""

    artifact_id: str = ""
    name: str = ""
    artifact_type: str = ""
    path: str = ""
    metadata: dict = field(default_factory=dict)
    size_bytes: int | None = None
    checksum: str | None = None


def _file_stats(path: str) -> tuple[int | None, str | None]:
    if not path or not os.path.isfile(path):
        return None, None
    size = os.path.getsize(path)
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return size, digest.hexdigest()


class ArtifactStore:
    """SQLite-backed registry of artifact references."""

    def __init__(self, store) -> None:
        self._store = store
        self._conn = store._conn
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS workflow_artifacts (
                artifact_id TEXT PRIMARY KEY,
                workflow_id TEXT NOT NULL,
                name TEXT NOT NULL DEFAULT '',
                artifact_type TEXT NOT NULL DEFAULT '',
                path TEXT NOT NULL DEFAULT '',
                metadata TEXT NOT NULL DEFAULT '{}',
                size_bytes INTEGER,
                checksum TEXT,
                created_at REAL NOT NULL
            )
            """
        )

    def register_artifact(
        self,
        workflow_id: str,
        name: str,
        artifact_type: str,
        path: str,
        metadata: dict | None = None,
    ) -> ArtifactRef:
        size_bytes, checksum = _file_stats(path)
        ref = ArtifactRef(
            artifact_id=f"art_{uuid.uuid4().hex}",
            name=name,
            artifact_type=artifact_type,
            path=path,
            metadata=dict(metadata or {}),
            size_bytes=size_bytes,
            checksum=checksum,
        )
        self._conn.execute(
            """
            INSERT INTO workflow_artifacts
                (artifact_id, workflow_id, name, artifact_type, path,
                 metadata, size_bytes, checksum, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ref.artifact_id,
                workflow_id,
                ref.name,
                ref.artifact_type,
                ref.path,
                json.dumps(ref.metadata, default=str),
                ref.size_bytes,
                ref.checksum,
                time.time(),
            ),
        )
        return ref

    def _row_to_ref(self, row) -> ArtifactRef:
        return ArtifactRef(
            artifact_id=row["artifact_id"],
            name=row["name"],
            artifact_type=row["artifact_type"],
            path=row["path"],
            metadata=json.loads(row["metadata"] or "{}"),
            size_bytes=row["size_bytes"],
            checksum=row["checksum"],
        )

    def get_artifact(self, artifact_id: str) -> ArtifactRef | None:
        row = self._conn.execute(
            "SELECT * FROM workflow_artifacts WHERE artifact_id = ?",
            (artifact_id,),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_ref(row)

    def list_artifacts(self, workflow_id: str) -> list[ArtifactRef]:
        rows = self._conn.execute(
            "SELECT * FROM workflow_artifacts WHERE workflow_id = ? "
            "ORDER BY created_at ASC, rowid ASC",
            (workflow_id,),
        ).fetchall()
        return [self._row_to_ref(row) for row in rows]

    def delete_artifact(self, artifact_id: str) -> None:
        self._conn.execute(
            "DELETE FROM workflow_artifacts WHERE artifact_id = ?",
            (artifact_id,),
        )


def resolve_artifact_path(
    artifact_id: str, store=None
) -> str | None:
    """Resolve an artifact id to its stored filesystem path."""
    if artifact_id is None:
        return None
    owns_store = store is None
    if owns_store:
        from core.workflow.storage import WorkflowStore

        store = WorkflowStore()
    try:
        ref = ArtifactStore(store).get_artifact(artifact_id)
        if ref is None:
            return None
        return ref.path
    finally:
        if owns_store:
            store.close()
