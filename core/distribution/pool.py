from __future__ import annotations

from .contracts import WorkerStatus


class WorkerPool:
    def __init__(self):
        self._workers = {}
        self._indexes = {}

    def add_worker(self, worker):
        self._workers[worker.worker_id] = worker

    def remove_worker(self, worker_id):
        self._workers.pop(worker_id, None)

    def next_worker(self, tenant_id=None, capability=None):
        candidates = [w for w in self._workers.values()
                      if w.status == WorkerStatus.ONLINE
                      and (tenant_id is None or w.tenant_id == tenant_id)
                      and (capability is None or any((c.id if hasattr(c, "id") else c) == capability for c in w.capabilities))]
        if not candidates:
            return None
        key = (tenant_id, capability)
        index = self._indexes.get(key, 0) % len(candidates)
        self._indexes[key] = index + 1
        return candidates[index]

    def evict_unhealthy(self):
        dead = [wid for wid, w in self._workers.items() if w.status != WorkerStatus.ONLINE]
        for wid in dead:
            del self._workers[wid]
        return len(dead)
