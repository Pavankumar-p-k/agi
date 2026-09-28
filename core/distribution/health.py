"""HealthChecker — marks workers OFFLINE after missed heartbeats."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from core.distribution.contracts import WorkerStatus
from core.distribution.registry import get_worker_registry

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_SECONDS = 30.0
DEFAULT_MISSED_THRESHOLD = 3


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class HealthChecker:
    """Periodically verifies workers are still heartbeating."""

    def __init__(self, interval_seconds: float = DEFAULT_INTERVAL_SECONDS,
                 missed_heartbeat_threshold: int = DEFAULT_MISSED_THRESHOLD,
                 registry: Any = None) -> None:
        self.interval_seconds = float(interval_seconds)
        self.missed_heartbeat_threshold = int(missed_heartbeat_threshold)
        self.registry = registry
        self._task: Optional[asyncio.Task] = None
        self._running = False

    def _registry(self) -> Any:
        return self.registry if self.registry is not None else get_worker_registry()

    @property
    def grace_seconds(self) -> float:
        return self.interval_seconds * max(1, self.missed_heartbeat_threshold)

    # ── checks ──────────────────────────────────────────────────────
    def is_stale(self, registration: Any, now: Optional[datetime] = None) -> bool:
        last = getattr(registration, "last_heartbeat", None)
        if last is None:
            return True
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        now = now or _utcnow()
        return (now - last).total_seconds() > self.grace_seconds

    def _check_all(self) -> int:
        """Mark every stale worker offline. Returns how many were marked."""
        marked = 0
        registry = self._registry()
        for registration in registry.all_workers():
            if self.is_stale(registration):
                if registration.status != WorkerStatus.OFFLINE:
                    registration.status = WorkerStatus.OFFLINE
                    marked += 1
                    logger.info("worker %s marked offline (missed heartbeats)",
                                registration.worker_id)
        return marked

    def check_worker(self, worker_id: str) -> bool:
        """Force a health check on one worker; True when it is offline."""
        registry = self._registry()
        registration = registry.get(worker_id)
        if registration is None:
            return True
        if self.is_stale(registration):
            registration.status = WorkerStatus.OFFLINE
            return True
        return False

    # ── background loop ─────────────────────────────────────────────
    async def _run(self) -> None:
        while self._running:
            try:
                self._check_all()
            except Exception as exc:  # noqa: BLE001 — the loop must survive
                logger.warning("health check failed: %s", exc)
            await asyncio.sleep(self.interval_seconds)

    def start(self) -> Optional[asyncio.Task]:
        if self._running:
            return self._task
        self._running = True
        try:
            self._task = asyncio.get_running_loop().create_task(self._run())
        except RuntimeError:  # no running loop — caller drives _check_all()
            self._running = False
            self._task = None
        return self._task

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
            self._task = None


__all__ = ["HealthChecker", "DEFAULT_INTERVAL_SECONDS", "DEFAULT_MISSED_THRESHOLD"]
