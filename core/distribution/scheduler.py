"""Scheduler facade for the distribution layer.

Placement decisions live in the worker pool; actual dispatch is delegated to
:class:`RemoteExecutionRuntime`, which owns the Transport protocol.
"""
from __future__ import annotations

import logging
from typing import Any, Iterable, Optional

from core.distribution.contracts import ExecutionAffinity, WorkerResponse
from core.distribution.pool import WorkerPool
from core.distribution.registry import get_worker_registry
from core.distribution.runtime import RemoteExecutionRuntime

logger = logging.getLogger(__name__)


class DistributionScheduler:
    """Routes work to the best available worker, or runs it locally."""

    def __init__(self, runtime: Optional[RemoteExecutionRuntime] = None,
                 pool: Optional[WorkerPool] = None,
                 registry: Any = None) -> None:
        self.registry = registry if registry is not None else get_worker_registry()
        self.pool = pool or WorkerPool(self.registry.all_workers())
        self.runtime = runtime or RemoteExecutionRuntime(registry=self.registry)

    def refresh_pool(self) -> None:
        """Rebuild the pool from the current registry contents."""
        self.pool = WorkerPool(self.registry.all_workers())

    async def dispatch(self, request: Any,
                       affinity: Optional[ExecutionAffinity] = None) -> WorkerResponse:
        affinity = affinity or ExecutionAffinity()
        if affinity.worker_id is None:
            selected = self.pool.next_worker(
                tenant_id=affinity.tenant_id, capability=affinity.capability)
            if selected is not None:
                affinity.worker_id = selected.worker_id
        return await self.runtime.execute(request, affinity=affinity)

    async def dispatch_many(self, requests: Iterable[Any],
                            affinity: Optional[ExecutionAffinity] = None) -> list:
        out = []
        for request in requests or ():
            out.append(await self.dispatch(request, affinity=affinity))
        return out


__all__ = ["DistributionScheduler"]
