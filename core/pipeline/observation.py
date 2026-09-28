"""Observation — immutable runtime trace record (Sprint 5.5C contract)."""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional


def _fingerprint(source: str, type_: str, payload: Any) -> str:
    """Deterministic hash of the observation's semantic content.

    Deliberately excludes ids/activity ids: two replays with different
    generated ids but identical content must produce equal fingerprints.
    """
    blob = json.dumps(
        {"source": source, "type": type_, "payload": payload},
        sort_keys=True, default=str,
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class Observation:
    """A single observed fact recorded during pipeline execution.

    Frozen: runtime artifacts must not be mutated after creation
    (trace validation asserts immutability).
    """

    id: str
    activity_id: str
    source: str
    type: str
    payload: Any = None
    fingerprint: str = ""
    parent_id: Optional[str] = None
    worker_id: Optional[str] = None
    timestamp: Any = None
    resource_scope: Any = None
    metadata: dict = field(default_factory=dict, compare=False)

    @classmethod
    def new(
        cls,
        activity_id: str,
        source: str,
        type_: str,
        payload: Any = None,
        services: Any = None,
        parent_id: Optional[str] = None,
        worker_id: Optional[str] = None,
        resource_scope: Any = None,
        timestamp: Any = None,
    ) -> "Observation":
        oid = services.uuid4() if services is not None and hasattr(services, "uuid4") \
            else uuid.uuid4().hex
        return cls(
            id=oid,
            activity_id=activity_id,
            source=source,
            type=type_,
            payload=payload,
            fingerprint=_fingerprint(source, type_, payload),
            parent_id=parent_id,
            worker_id=worker_id,
            resource_scope=resource_scope,
            timestamp=timestamp,
        )

    def to_dict(self) -> dict:
        d = {
            "id": self.id,
            "fingerprint": self.fingerprint,
            "activity_id": self.activity_id,
            "source": self.source,
            "type": self.type,
            "payload": self.payload,
            "parent_id": self.parent_id,
            "resource_scope": (
                self.resource_scope.to_dict()
                if hasattr(self.resource_scope, "to_dict")
                else self.resource_scope
            ),
        }
        return d


__all__ = ["Observation"]
