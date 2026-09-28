"""Distribution data contracts.

``WorkerRequest`` / ``WorkerResponse`` are the only cross-boundary payloads
between the runtime and a worker (architecture Rule 39); the remaining types
describe worker identity, capability advertisement, affinity and version
compatibility.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class HealthStatus(str, Enum):
    """Worker health as reported by its health endpoint."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        return str(self.value)


class WorkerStatus(str, Enum):
    """Lifecycle status tracked by the worker registry."""

    ONLINE = "online"
    OFFLINE = "offline"
    BUSY = "busy"
    DRAINING = "draining"

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        return str(self.value)


@dataclass
class CapabilityDescriptor:
    """A capability a worker advertises."""

    id: str
    name: str = ""
    version: str = "1.0"
    metadata: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.id = str(self.id or "").strip()
        if not self.name:
            self.name = self.id

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "version": self.version}


@dataclass
class ExecutionAffinity:
    """Placement hints for a dispatch."""

    tenant_id: Optional[str] = None
    workspace_id: Optional[str] = None
    capability: Optional[str] = None
    worker_id: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "tenant_id": self.tenant_id,
            "workspace_id": self.workspace_id,
            "capability": self.capability,
            "worker_id": self.worker_id,
        }


@dataclass
class VersionCheck:
    """Result of a runtime/worker version compatibility check."""

    compatible: bool = True
    reason: Optional[str] = None

    def __bool__(self) -> bool:
        return bool(self.compatible)


@dataclass
class WorkerRequest:
    """The single outbound cross-boundary request payload.

    ``worker_protocol_version`` is validated by the receiving worker; a
    mismatch is rejected rather than silently coerced.
    """

    runtime_context: Any = None
    request: Any = ""
    pipeline_version: str = "1.0"
    runtime_spec_version: str = "1.0"
    worker_protocol_version: str = "1.0"
    worker_id: str = ""
    tenant_id: Optional[str] = None
    capability: Optional[str] = None
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        ctx = self.runtime_context
        return {
            "runtime_context": ctx.to_dict() if hasattr(ctx, "to_dict") else ctx,
            "request": self.request,
            "pipeline_version": self.pipeline_version,
            "runtime_spec_version": self.runtime_spec_version,
            "worker_protocol_version": self.worker_protocol_version,
            "worker_id": self.worker_id,
            "tenant_id": self.tenant_id,
            "capability": self.capability,
            "request_id": self.request_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "WorkerRequest":
        """Reconstruct a request from its serialised form.

        This is the only place allowed to rebuild a ``RuntimeContext``
        (architecture Rule 42).
        """
        payload = dict(data or {})
        ctx = payload.get("runtime_context")
        if isinstance(ctx, dict):
            from core.runtime.context import RuntimeContext
            try:
                ctx = RuntimeContext(**ctx)
            except TypeError:
                ctx = dict(ctx)
        payload["runtime_context"] = ctx
        allowed = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in payload.items() if k in allowed})


@dataclass
class WorkerResponse:
    """The single inbound cross-boundary response payload."""

    outcome: Any = None
    observations: tuple = ()
    metrics: Any = None
    worker_id: str = ""
    error: Optional[str] = None
    success: bool = True
    duration_ms: float = 0.0
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "outcome": self.outcome,
            "observations": list(self.observations or ()),
            "metrics": self.metrics,
            "worker_id": self.worker_id,
            "error": self.error,
            "success": self.success,
            "duration_ms": self.duration_ms,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "WorkerResponse":
        payload = dict(data or {})
        allowed = {f for f in cls.__dataclass_fields__}
        payload.setdefault("observations", ())
        if isinstance(payload.get("observations"), list):
            payload["observations"] = tuple(payload["observations"])
        return cls(**{k: v for k, v in payload.items() if k in allowed})


__all__ = [
    "HealthStatus", "WorkerStatus", "CapabilityDescriptor", "ExecutionAffinity",
    "VersionCheck", "WorkerRequest", "WorkerResponse",
]
