from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class HeartbeatMonitor:
    def __init__(self, engine: "WorkflowEngine", interval: int = 10, stale_seconds: int = 60) -> None:
        self._engine = engine
        self._interval = interval
        self._stale_seconds = stale_seconds
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._run())
        logger.info("[HEARTBEAT] Monitor started (interval=%ds, stale=%ds)", self._interval, self._stale_seconds)

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await asyncio.wait_for(self._task, timeout=5)
        except (asyncio.CancelledError, TimeoutError):
            pass
        self._task = None
        logger.info("[HEARTBEAT] Monitor stopped")

    async def _run(self) -> None:
        while True:
            try:
                await asyncio.sleep(self._interval)
                await self._check_stale_workflows()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("[HEARTBEAT] Check cycle failed: %s", e)

    async def _check_stale_workflows(self) -> None:
        from core.workflow.models import WorkflowStatus
        from core.workflow.recovery import recover_active_workflows

        now = datetime.utcnow()
        active = self._engine.store.list_active_workflows()
        compensating = self._engine.store.list_compensating_workflows()
        stale_ids = []

        for wf in active + compensating:
            if wf.last_heartbeat:
                age = (now - wf.last_heartbeat).total_seconds()
                if age >= self._stale_seconds:
                    stale_ids.append(wf.workflow_id)

        if stale_ids:
            logger.info("[HEARTBEAT] Found %d stale workflow(s): %s", len(stale_ids), stale_ids)
            recovered = await recover_active_workflows(self._engine)
            if recovered:
                logger.info("[HEARTBEAT] Recovered %d stale workflow(s)", len(recovered))
