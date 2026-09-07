from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol

from .contracts import CapabilityDescriptor, VersionCheck, WorkerStatus


class WorkerRegistry(Protocol):
    def discover(self, tenant_id=None, capability=None, version_check=None): ...


class WorkerRegistration:
    def __init__(self, worker_id, worker, tenant_id=None, capabilities=None,
                 pipeline_version="1.0", runtime_spec_version="1.0",
                 status=WorkerStatus.ONLINE, last_heartbeat=None):
        self.worker_id = worker_id
        self.worker = worker
        self.tenant_id = tenant_id
        self.capabilities = list(capabilities or [])
        self.pipeline_version = pipeline_version
        self.runtime_spec_version = runtime_spec_version
        self.status = status
        self.last_heartbeat = last_heartbeat


class InMemoryWorkerRegistry:
    def __init__(self):
        self._workers = {}

    def register(self, registration):
        self._workers[registration.worker_id] = registration
        return registration

    def deregister(self, worker_id):
        return self._workers.pop(worker_id, None) is not None

    def get(self, worker_id):
        return self._workers.get(worker_id)

    def all_workers(self):
        return list(self._workers.values())

    def discover(self, tenant_id=None, capability=None, version_check=None):
        result = []
        for worker in self._workers.values():
            if worker.status != WorkerStatus.ONLINE:
                continue
            if tenant_id is not None and worker.tenant_id != tenant_id:
                continue
            if capability is not None and not any(
                (c.id if isinstance(c, CapabilityDescriptor) else c) == capability
                for c in worker.capabilities
            ):
                continue
            if version_check is not None and not version_check.compatible:
                continue
            result.append(worker)
        return result

    def heartbeat(self, worker_id):
        worker = self._workers.get(worker_id)
        if worker is None:
            return False
        worker.last_heartbeat = datetime.now(timezone.utc)
        worker.status = WorkerStatus.ONLINE
        return True

    @staticmethod
    def check_version_compatibility(worker, pipeline_version, runtime_spec_version):
        if worker.pipeline_version != pipeline_version:
            return VersionCheck(False, f"pipeline_version mismatch: {worker.pipeline_version} != {pipeline_version}")
        if worker.runtime_spec_version != runtime_spec_version:
            return VersionCheck(False, f"runtime_spec_version mismatch: {worker.runtime_spec_version} != {runtime_spec_version}")
        return VersionCheck(True)


_registry = InMemoryWorkerRegistry()


def get_worker_registry():
    return _registry


def set_worker_registry(registry):
    global _registry
    _registry = registry
