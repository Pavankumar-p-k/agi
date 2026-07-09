from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol, Sequence

from core.distribution.contracts import (
    CapabilityDescriptor,
    ExecutionAffinity,
    VersionCheck,
    WorkerStatus,
)
from core.distribution.worker import WorkerEndpoint

logger = logging.getLogger(__name__)

_registry_instance: WorkerRegistry | None = None


@dataclass
class WorkerRegistration:
    worker_id: str
    worker: WorkerEndpoint
    tenant_id: str | None = None
    capabilities: list[CapabilityDescriptor] = field(default_factory=list)
    pipeline_version: str = "1.0"
    runtime_spec_version: str = "1.0"
    worker_protocol_version: str = "1.0"
    last_heartbeat: datetime | None = None
    status: WorkerStatus = WorkerStatus.ONLINE
    address: str = ""


class WorkerRegistry(Protocol):
    """Canonical worker discovery contract.

    ``Registry`` is the sole source of worker discovery (Rule 38).
    """

    def register(self, registration: WorkerRegistration) -> None:
        ...

    def deregister(self, worker_id: str) -> None:
        ...

    def discover(
        self,
        tenant_id: str | None = None,
        capability: str | None = None,
        version_check: VersionCheck | None = None,
    ) -> list[WorkerRegistration]:
        ...

    def heartbeat(self, worker_id: str) -> None:
        ...

    def get_worker(self, worker_id: str) -> WorkerRegistration | None:
        ...

    def all_workers(self) -> list[WorkerRegistration]:
        ...


class InMemoryWorkerRegistry:
    """In-memory implementation of ``WorkerRegistry`` for development and tests."""

    def __init__(self) -> None:
        self._workers: dict[str, WorkerRegistration] = {}

    def register(self, registration: WorkerRegistration) -> None:
        self._workers[registration.worker_id] = registration
        logger.info("Worker %s registered (tenant=%s, caps=%s)",
                     registration.worker_id,
                     registration.tenant_id,
                     [c.id for c in registration.capabilities])

    def deregister(self, worker_id: str) -> None:
        self._workers.pop(worker_id, None)
        logger.info("Worker %s deregistered", worker_id)

    def discover(
        self,
        tenant_id: str | None = None,
        capability: str | None = None,
        version_check: VersionCheck | None = None,
    ) -> list[WorkerRegistration]:
        results: list[WorkerRegistration] = []
        for w in self._workers.values():
            if w.status != WorkerStatus.ONLINE:
                continue
            if tenant_id is not None and w.tenant_id != tenant_id:
                continue
            if capability is not None:
                cap_ids = [c.id for c in w.capabilities]
                if capability not in cap_ids:
                    continue
            if version_check is not None and not version_check.compatible:
                continue
            results.append(w)
        return results

    def heartbeat(self, worker_id: str) -> None:
        w = self._workers.get(worker_id)
        if w is not None:
            w.last_heartbeat = datetime.now(timezone.utc)
            w.status = WorkerStatus.ONLINE

    def get_worker(self, worker_id: str) -> WorkerRegistration | None:
        return self._workers.get(worker_id)

    def all_workers(self) -> list[WorkerRegistration]:
        return list(self._workers.values())

    def check_version_compatibility(
        self,
        worker: WorkerRegistration,
        pipeline_version: str,
        runtime_spec_version: str,
    ) -> VersionCheck:
        if worker.pipeline_version != pipeline_version:
            return VersionCheck(
                compatible=False,
                reason=f"pipeline_version mismatch: worker={worker.pipeline_version}, request={pipeline_version}",
            )
        if worker.runtime_spec_version != runtime_spec_version:
            return VersionCheck(
                compatible=False,
                reason=f"runtime_spec_version mismatch: worker={worker.runtime_spec_version}, request={runtime_spec_version}",
            )
        return VersionCheck(compatible=True)


def get_worker_registry() -> WorkerRegistry:
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = InMemoryWorkerRegistry()
    return _registry_instance


def set_worker_registry(registry: WorkerRegistry | None) -> None:
    global _registry_instance
    _registry_instance = registry
