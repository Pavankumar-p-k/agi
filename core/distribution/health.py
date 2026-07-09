from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from core.distribution.contracts import HealthStatus, WorkerStatus
from core.distribution.registry import get_worker_registry

logger = logging.getLogger(__name__)


@dataclass
class HealthChecker:
    """Periodically probes worker health and marks OFFLINE on failure.

    Call ``start()`` to begin the background loop and ``stop()`` to
    shut it down.
    """

    interval_seconds: float = 10.0
    missed_heartbeat_threshold: int = 3
    _task: asyncio.Task[Any] | None = field(default=None, init=False, repr=False)

    async def start(self) -> None:
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _run(self) -> None:
        while True:
            try:
                await asyncio.sleep(self.interval_seconds)
                self._check_all()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("Health check error: %s", exc)

    def _check_all(self) -> None:
        registry = get_worker_registry()
        now = datetime.now(timezone.utc)
        for w in registry.all_workers():
            if w.last_heartbeat is None:
                continue
            elapsed = (now - w.last_heartbeat).total_seconds()
            if elapsed > self.interval_seconds * self.missed_heartbeat_threshold:
                logger.warning("Worker %s marked OFFLINE (no heartbeat for %.0fs)",
                                w.worker_id, elapsed)
                w.status = WorkerStatus.OFFLINE
