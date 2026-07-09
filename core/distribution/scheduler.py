from __future__ import annotations

import logging
from typing import Any

from core.distribution.contracts import ExecutionAffinity
from core.distribution.registry import get_worker_registry
from core.distribution.runtime import RemoteExecutionRuntime
from core.distribution.transport import HttpTransport, InProcessTransport

logger = logging.getLogger(__name__)


class DistributedScheduler:
    """Scheduler that routes activities to workers via ``WorkerRegistry``.

    Tenant-aware and capability-aware routing.  Falls back to
    ``RemoteExecutionRuntime`` (which falls back to local) when
    no specialised worker is available.
    """

    def __init__(
        self,
        runtime: RemoteExecutionRuntime | None = None,
    ) -> None:
        self._runtime = runtime or RemoteExecutionRuntime()

    async def submit(
        self,
        goal: str,
        tenant_id: str | None = None,
        capability: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        from core.pipeline.messages import Request

        registry = get_worker_registry()
        workers = registry.discover(tenant_id=tenant_id, capability=capability)

        if workers:
            logger.info("Routing to %d worker(s) for tenant=%s cap=%s",
                         len(workers), tenant_id, capability)
        else:
            logger.info("No worker for tenant=%s cap=%s, executing locally",
                         tenant_id, capability)

        affinity = ExecutionAffinity(
            tenant_id=tenant_id or "",
            locality="remote" if workers else "local",
        )

        req = Request(
            text=goal,
            transport="distribution",
            metadata={
                **(metadata or {}),
                "tenant_id": tenant_id,
                "capability": capability,
            },
        )

        response = await self._runtime.execute(req, affinity=affinity)
        return response.outcome.activity_id if response.outcome else ""

    async def get_queue(
        self,
        tenant_id: str | None = None,
    ) -> list[Any]:
        return []
