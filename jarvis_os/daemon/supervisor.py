"""Local supervisor loop for proactive goals and queued work."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("jarvis.os.supervisor")


class LocalSupervisor:
    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._queue: asyncio.Queue = asyncio.Queue()
        self._history: List[Dict[str, Any]] = []
        self._processor = None

    async def initialize(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("[LocalSupervisor] started")

    async def shutdown(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def enqueue_goal(self, payload: Dict[str, Any]):
        await self._queue.put({"queued_at": time.time(), **payload})

    def set_processor(self, processor):
        self._processor = processor

    def status(self) -> Dict[str, Any]:
        return {
            "running": self._running,
            "queued": self._queue.qsize(),
            "recent": self._history[-10:],
        }

    async def _loop(self):
        while self._running:
            try:
                item = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                item["started_at"] = time.time()
                item["status"] = "running"
                if self._processor:
                    try:
                        result = await self._processor(item)
                        item["status"] = "completed"
                        item["result"] = result
                    except Exception as exc:
                        item["status"] = "failed"
                        item["error"] = str(exc)
                item["completed_at"] = time.time()
                self._history.append(item)
                self._history = self._history[-100:]
            except asyncio.TimeoutError:
                continue
