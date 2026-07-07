from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.pipeline.deterministic import DeterministicServices


def _compute_fingerprint(source: str, type_: str, payload: dict[str, Any]) -> str:
    """Deterministic hash of (source, type, payload) for deduplication."""
    raw = json.dumps({"source": source, "type": type_, "payload": payload}, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class Observation:
    """A single observed event during execution.

    Immutable and content-addressable (via ``fingerprint``).  Every
    Observation belongs to exactly one Activity (``activity_id``).

    Sources: ``execution``, ``scheduler``, ``tool``, ``llm``, ``filesystem``,
    ``user``, ``browser``, ``plugin``, ``webhook``, ``timer``.

    Types: ``text``, ``tool_output``, ``search_result``, ``browser_page``,
    ``error``, ``metric``, ``code``, ``image``.
    """

    id: str
    fingerprint: str
    activity_id: str
    source: str
    type: str
    timestamp: datetime
    payload: dict[str, Any]
    confidence: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    parent_id: str | None = None
    tenant_id: str | None = None
    organization_id: str | None = None
    workspace_id: str | None = None

    @classmethod
    def new(
        cls,
        activity_id: str,
        source: str,
        type_: str,
        payload: dict[str, Any],
        *,
        confidence: float | None = None,
        metadata: dict[str, Any] | None = None,
        parent_id: str | None = None,
        tenant_id: str | None = None,
        organization_id: str | None = None,
        workspace_id: str | None = None,
        services: DeterministicServices | None = None,
    ) -> Observation:
        """Create a new Observation with auto-generated id and fingerprint.

        When *services* is provided, its ``uuid4`` and ``now`` are used
        instead of ``uuid.uuid4()`` and ``datetime.now()``, enabling
        deterministic observation creation in tests.
        """
        fingerprint = _compute_fingerprint(source, type_, payload)
        obs_id = services.uuid4() if services else uuid.uuid4().hex
        ts = services.now() if services else datetime.now(timezone.utc)
        return cls(
            id=obs_id,
            fingerprint=fingerprint,
            activity_id=activity_id,
            source=source,
            type=type_,
            timestamp=ts,
            payload=payload,
            confidence=confidence,
            metadata=metadata or {},
            parent_id=parent_id,
            tenant_id=tenant_id,
            organization_id=organization_id,
            workspace_id=workspace_id,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "fingerprint": self.fingerprint,
            "activity_id": self.activity_id,
            "source": self.source,
            "type": self.type,
            "timestamp": self.timestamp.isoformat(),
            "payload": self.payload,
            "confidence": self.confidence,
            "metadata": self.metadata,
            "parent_id": self.parent_id,
            "tenant_id": self.tenant_id,
            "organization_id": self.organization_id,
            "workspace_id": self.workspace_id,
        }
