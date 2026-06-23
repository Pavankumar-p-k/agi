from __future__ import annotations

import hashlib
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class ArtifactRef:
    artifact_id: str
    workflow_id: str
    name: str
    artifact_type: str
    path: str
    size_bytes: int | None = None
    checksum: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None


class ArtifactStore:
    def __init__(self, store: "WorkflowStore") -> None:
        self._store = store

    def register_artifact(
        self,
        workflow_id: str,
        name: str,
        artifact_type: str,
        path: str,
        metadata: dict | None = None,
    ) -> ArtifactRef:
        artifact_id = f"art_{uuid.uuid4().hex}"
        size_bytes = None
        checksum = None
        if os.path.isfile(path):
            size_bytes = os.path.getsize(path)
            checksum = self._compute_checksum(path)
        now = datetime.utcnow()
        ref = ArtifactRef(
            artifact_id=artifact_id,
            workflow_id=workflow_id,
            name=name,
            artifact_type=artifact_type,
            path=path,
            size_bytes=size_bytes,
            checksum=checksum,
            metadata=metadata or {},
            created_at=now,
        )
        self._store.create_artifact(ref)
        return ref

    def get_artifact(self, artifact_id: str) -> ArtifactRef | None:
        return self._store.get_artifact(artifact_id)

    def list_artifacts(self, workflow_id: str) -> list[ArtifactRef]:
        return self._store.list_artifacts(workflow_id)

    def delete_artifact(self, artifact_id: str) -> None:
        self._store.delete_artifact(artifact_id)

    @staticmethod
    def _compute_checksum(path: str) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
