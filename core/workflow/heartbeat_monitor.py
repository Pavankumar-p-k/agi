"""Heartbeat monitor: periodic detection and recovery of stale workflows."""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


class HeartbeatMonitor:
    """Background loop that recovers workflows whose heartbeat went stale."""

    def __init__(self, engine, interval: float = 5.0,
                 stale_seconds: float = 60.0) -> None:
        self.engine = engine
        self.interval = interval
        self.stale_seconds = stale_seconds
        self._task: asyncio.Task | None = None
        self._stopped = False

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stopped = False
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._stopped = True
        task = self._task
        self._task = None
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: PERF203
                pass

    async def _loop(self) -> None:
        from core.workflow.recovery import recover_active_workflows

        while not self._stopped:
            try:
                await recover_active_workflows(
                    self.engine, stale_seconds=self.stale_seconds
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 — monitor must keep running
                logger.warning("heartbeat sweep failed: %s", exc)
            try:
                await asyncio.sleep(self.interval)
            except asyncio.CancelledError:
                raise
