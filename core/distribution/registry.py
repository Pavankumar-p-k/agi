"""Worker registry — the sole source of worker discovery (Rule 38).

Registrations advertise their runtime versions so dispatch can reject
incompatible workers before a request leaves the process (Rule 41).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Optional, Protocol, runtime_checkable

from core.distribution.contracts import (
    CapabilityDescriptor,
    VersionCheck,
    WorkerStatus,
)

PIPELINE_VERSION = "1.0"
RUNTIME_SPEC_VERSION = "1.0"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class WorkerRegistration:
    """A registered worker plus the versions it advertises."""

    worker_id: str
    worker: Any = None
    tenant_id: Optional[str] = None
    capabilities: list = field(default_factory=list)
    pipeline_version: str = PIPELINE_VERSION
    runtime_spec_version: str = RUNTIME_SPEC_VERSION
    worker_protocol_version: str = "1.0"
    status: WorkerStatus = WorkerStatus.ONLINE
    last_heartbeat: Optional[datetime] = None
    metadata: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.worker_id = str(self.worker_id or "").strip()
        if not self.worker_id:
            raise ValueError("worker_id is required")
        if self.last_heartbeat is None:
            self.last_heartbeat = _utcnow()
        normalised = []
        for cap in self.capabilities or []:
            normalised.append(cap if isinstance(cap, CapabilityDescriptor)
                              else CapabilityDescriptor(id=str(cap), name=str(cap)))
        self.capabilities = normalised

    @property
    def capability_ids(self) -> set:
        return {c.id for c in self.capabilities}

    def supports(self, capability: Optional[str]) -> bool:
        if not capability:
            return True
        return str(capability) in self.capability_ids

    def to_dict(self) -> dict:
        return {
            "worker_id": self.worker_id,
            "tenant_id": self.tenant_id,
            "capabilities": [c.id for c in self.capabilities],
            "pipeline_version": self.pipeline_version,
            "runtime_spec_version": self.runtime_spec_version,
            "worker_protocol_version": self.worker_protocol_version,
            "status": self.status.value if hasattr(self.status, "value") else str(self.status),
        }


@runtime_checkable
class WorkerRegistry(Protocol):
    """Discovery surface used by the runtime."""

    def register(self, registration: WorkerRegistration) -> None: ...
    def deregister(self, worker_id: str) -> bool: ...
    def discover(self, tenant_id: Optional[str] = None,
                 capability: Optional[str] = None, **kwargs) -> list: ...
    def heartbeat(self, worker_id: str) -> bool: ...
    def all_workers(self) -> list: ...


class InMemoryWorkerRegistry:
    """Process-local worker registry with tenant isolation."""

    def __init__(self) -> None:
        self._workers: dict[str, WorkerRegistration] = {}

    # ── lifecycle ───────────────────────────────────────────────────
    def register(self, registration: WorkerRegistration) -> WorkerRegistration:
        if not isinstance(registration, WorkerRegistration):
            raise TypeError("register() expects a WorkerRegistration")
        registration.status = WorkerStatus.ONLINE
        registration.last_heartbeat = registration.last_heartbeat or _utcnow()
        self._workers[registration.worker_id] = registration
        return registration

    def deregister(self, worker_id: str) -> bool:
        return self._workers.pop(str(worker_id), None) is not None

    def heartbeat(self, worker_id: str) -> bool:
        reg = self._workers.get(str(worker_id))
        if reg is None:
            return False
        reg.last_heartbeat = _utcnow()
        reg.status = WorkerStatus.ONLINE
        return True

    # ── discovery ───────────────────────────────────────────────────
    def discover(self, tenant_id: Optional[str] = None,
                 capability: Optional[str] = None,
                 version_check: Optional[VersionCheck] = None,
                 include_offline: bool = False) -> list:
        out = []
        for reg in self._workers.values():
            if not include_offline and reg.status != WorkerStatus.ONLINE:
                continue
            if tenant_id is not None and reg.tenant_id != tenant_id:
                continue
            if capability and not reg.supports(capability):
                continue
            if version_check is not None and not version_check.compatible:
                continue
            out.append(reg)
        return out

    def all_workers(self) -> list:
        return list(self._workers.values())

    def get(self, worker_id: str) -> Optional[WorkerRegistration]:
        return self._workers.get(str(worker_id))

    def __len__(self) -> int:
        return len(self._workers)

    # ── version negotiation ─────────────────────────────────────────
    def check_version_compatibility(
        self,
        registration: WorkerRegistration,
        pipeline_version: str = PIPELINE_VERSION,
        runtime_spec_version: str = RUNTIME_SPEC_VERSION,
    ) -> VersionCheck:
        """Compare a worker's advertised versions against the runtime's."""
        if registration is None:
            return VersionCheck(compatible=False, reason="no worker registration")
        if registration.pipeline_version != pipeline_version:
            return VersionCheck(
                compatible=False,
                reason=(f"pipeline_version mismatch: worker="
                        f"{registration.pipeline_version} runtime={pipeline_version}"),
            )
        if registration.runtime_spec_version != runtime_spec_version:
            return VersionCheck(
                compatible=False,
                reason=(f"runtime_spec_version mismatch: worker="
                        f"{registration.runtime_spec_version} runtime={runtime_spec_version}"),
            )
        return VersionCheck(compatible=True, reason=None)


_worker_registry: WorkerRegistry = InMemoryWorkerRegistry()


def get_worker_registry() -> WorkerRegistry:
    """Return the process-wide worker registry."""
    return _worker_registry


def set_worker_registry(registry: WorkerRegistry) -> None:
    """Swap the process-wide registry (tests/deployments)."""
    global _worker_registry
    _worker_registry = registry


__all__ = [
    "WorkerRegistration", "WorkerRegistry", "InMemoryWorkerRegistry",
    "get_worker_registry", "set_worker_registry",
    "PIPELINE_VERSION", "RUNTIME_SPEC_VERSION",
]
