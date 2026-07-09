from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from core.distribution.contracts import WorkerStatus
from core.distribution.registry import WorkerRegistration

logger = logging.getLogger(__name__)


@dataclass
class WorkerPool:
    """Weighted worker pool per (tenant_id, capability).

    Manages worker selection, eviction of unhealthy workers, and
    round-robin dispatch.
    """

    _pools: dict[str, list[WorkerRegistration]] = field(default_factory=dict)
    _index: dict[str, int] = field(default_factory=dict)

    def _key(self, tenant_id: str | None, capability: str | None) -> str:
        return f"{tenant_id or ''}:{capability or ''}"

    def add_worker(self, worker: WorkerRegistration) -> None:
        for cap in worker.capabilities:
            key = self._key(worker.tenant_id, cap.id)
            if key not in self._pools:
                self._pools[key] = []
                self._index[key] = 0
            if worker not in self._pools[key]:
                self._pools[key].append(worker)

    def remove_worker(self, worker_id: str, tenant_id: str | None = None) -> None:
        for pool in self._pools.values():
            pool[:] = [w for w in pool if w.worker_id != worker_id]

    def next_worker(
        self,
        tenant_id: str | None = None,
        capability: str | None = None,
    ) -> WorkerRegistration | None:
        key = self._key(tenant_id, capability)
        pool = self._pools.get(key, [])
        pool = [w for w in pool if w.status == WorkerStatus.ONLINE]
        if not pool:
            return None
        idx = self._index.get(key, 0) % len(pool)
        self._index[key] = idx + 1
        return pool[idx]

    def evict_unhealthy(self) -> int:
        count = 0
        for pool in self._pools.values():
            before = len(pool)
            pool[:] = [w for w in pool if w.status == WorkerStatus.ONLINE]
            count += before - len(pool)
        return count
