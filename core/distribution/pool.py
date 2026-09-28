"""WorkerPool — round-robin placement across eligible workers."""
from __future__ import annotations

from typing import Iterable, Optional

from core.distribution.contracts import WorkerStatus
from core.distribution.registry import WorkerRegistration


class WorkerPool:
    """Round-robin pool over registered workers."""

    def __init__(self, workers: Optional[Iterable[WorkerRegistration]] = None) -> None:
        self._workers: list[WorkerRegistration] = []
        self._cursor: int = 0
        for worker in workers or ():
            self.add_worker(worker)

    # ── membership ──────────────────────────────────────────────────
    def add_worker(self, registration: WorkerRegistration) -> WorkerRegistration:
        if not isinstance(registration, WorkerRegistration):
            raise TypeError("add_worker() expects a WorkerRegistration")
        self.remove_worker(registration.worker_id)
        self._workers.append(registration)
        return registration

    def remove_worker(self, worker_id: str) -> bool:
        before = len(self._workers)
        self._workers = [w for w in self._workers if w.worker_id != str(worker_id)]
        return len(self._workers) != before

    def workers(self) -> list:
        return list(self._workers)

    def __len__(self) -> int:
        return len(self._workers)

    # ── selection ───────────────────────────────────────────────────
    def _eligible(self, tenant_id: Optional[str] = None,
                  capability: Optional[str] = None) -> list:
        out = []
        for reg in self._workers:
            if reg.status != WorkerStatus.ONLINE:
                continue
            if tenant_id is not None and reg.tenant_id != tenant_id:
                continue
            if capability and not reg.supports(capability):
                continue
            out.append(reg)
        return out

    def next_worker(self, tenant_id: Optional[str] = None,
                    capability: Optional[str] = None) -> Optional[WorkerRegistration]:
        """Round-robin over eligible workers (None when none are eligible)."""
        eligible = self._eligible(tenant_id=tenant_id, capability=capability)
        if not eligible:
            return None
        chosen = eligible[self._cursor % len(eligible)]
        self._cursor = (self._cursor + 1) % max(1, len(self._workers))
        return chosen

    def evict_unhealthy(self) -> int:
        """Drop workers that are not ONLINE. Returns the number evicted."""
        unhealthy = [w for w in self._workers if w.status != WorkerStatus.ONLINE]
        for worker in unhealthy:
            self.remove_worker(worker.worker_id)
        return len(unhealthy)


__all__ = ["WorkerPool"]
