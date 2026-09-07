from __future__ import annotations

from .contracts import ExecutionAffinity, WorkerRequest, WorkerResponse
from .registry import get_worker_registry


class RemoteExecutionRuntime:
    def __init__(self, pipeline_version="1.0", runtime_spec_version="1.0", registry=None):
        self.pipeline_version = pipeline_version
        self.runtime_spec_version = runtime_spec_version
        self.registry = registry

    async def _execute_local(self, request):
        return WorkerResponse(outcome=request)

    async def execute(self, request, affinity=None):
        registry = self.registry or get_worker_registry()
        affinity = affinity or ExecutionAffinity()
        workers = registry.discover(tenant_id=affinity.tenant_id, capability=affinity.capability)
        workers = [w for w in workers if registry.check_version_compatibility(
            w, self.pipeline_version, self.runtime_spec_version).compatible]
        if affinity.worker_id:
            workers = [w for w in workers if w.worker_id == affinity.worker_id]
        if workers:
            return await workers[0].worker.execute(WorkerRequest(
                request=request, pipeline_version=self.pipeline_version,
                runtime_spec_version=self.runtime_spec_version))
        return await self._execute_local(request)
