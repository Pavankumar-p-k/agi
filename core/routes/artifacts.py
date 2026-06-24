"""core/routes/artifacts.py — REST API for the Artifact Store.

Wraps ArtifactStore as HTTP endpoints so frontends can list, search,
download, and manage artifacts produced by workflows and builds.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from core.workflow.artifact_store import ArtifactRef, ArtifactStore
from core.workflow.storage import WorkflowStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/artifacts", tags=["Artifacts"])

# ── Singleton store ───────────────────────────────────────────────────────────

_store: ArtifactStore | None = None


def _get_store() -> ArtifactStore:
    global _store
    if _store is None:
        _store = ArtifactStore(WorkflowStore())
    return _store


# ── Pydantic response models ────────────────────────────────────────────────


class ArtifactResponse(BaseModel):
    artifact_id: str
    workflow_id: str
    name: str
    artifact_type: str
    path: str
    size_bytes: int | None = None
    checksum: str | None = None
    metadata: dict[str, Any] = {}
    created_at: str | None = None


def _to_response(ref: ArtifactRef) -> ArtifactResponse:
    return ArtifactResponse(
        artifact_id=ref.artifact_id,
        workflow_id=ref.workflow_id,
        name=ref.name,
        artifact_type=ref.artifact_type,
        path=ref.path,
        size_bytes=ref.size_bytes,
        checksum=ref.checksum,
        metadata=ref.metadata,
        created_at=ref.created_at.isoformat() if ref.created_at else None,
    )


# ── Routes ──────────────────────────────────────────────────────────────────


@router.get("")
def list_artifacts(
    workflow_id: str | None = Query(None, description="Filter by workflow"),
    artifact_type: str | None = Query(None, description="Filter by type"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict:
    store = _get_store()
    if workflow_id:
        refs = store.list_artifacts(workflow_id)
    else:
        refs = store.list_all_artifacts()
    filtered = refs
    if artifact_type:
        filtered = [r for r in filtered if r.artifact_type == artifact_type]
    total = len(filtered)
    page = filtered[offset : offset + limit]
    return {
        "artifacts": [_to_response(r) for r in page],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@router.get("/search")
def search_artifacts(
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(50, ge=1, le=500),
) -> dict:
    store = _get_store()
    results = store.search_artifacts(q)
    return {
        "artifacts": [_to_response(r) for r in results[:limit]],
        "total": len(results),
    }


@router.get("/{artifact_id}")
def get_artifact(artifact_id: str) -> ArtifactResponse:
    ref = _get_store().get_artifact(artifact_id)
    if ref is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return _to_response(ref)


@router.get("/{artifact_id}/download")
def download_artifact(artifact_id: str):
    ref = _get_store().get_artifact(artifact_id)
    if ref is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    path = Path(ref.path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Artifact file not found on disk")
    return FileResponse(str(path), filename=path.name)


@router.delete("/{artifact_id}")
def delete_artifact(artifact_id: str) -> dict:
    store = _get_store()
    ref = store.get_artifact(artifact_id)
    if ref is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    store.delete_artifact(artifact_id)
    logger.info("Deleted artifact %s (type=%s)", artifact_id, ref.artifact_type)
    return {"deleted": artifact_id}
