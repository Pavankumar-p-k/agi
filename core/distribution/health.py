from __future__ import annotations

from datetime import datetime, timezone
from .contracts import WorkerStatus
from .registry import get_worker_registry


class HealthChecker:
    def __init__(self, interval_seconds=10.0, missed_heartbeat_threshold=3):
        self.interval_seconds = interval_seconds
        self.missed_heartbeat_threshold = missed_heartbeat_threshold

    def _check_all(self):
        now = datetime.now(timezone.utc)
        timeout = self.interval_seconds * self.missed_heartbeat_threshold
        for worker in get_worker_registry().all_workers():
            heartbeat = worker.last_heartbeat
            if heartbeat is not None:
                if heartbeat.tzinfo is None:
                    heartbeat = heartbeat.replace(tzinfo=timezone.utc)
                if (now - heartbeat).total_seconds() > timeout:
                    worker.status = WorkerStatus.OFFLINE

    async def run(self):
        import asyncio
        while True:
            self._check_all()
            await asyncio.sleep(self.interval_seconds)
