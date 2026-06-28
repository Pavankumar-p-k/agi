from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)

PollCallback = Callable[[dict[str, Any]], Awaitable[None]]


class ActivityUpdateService:
    """
    Unified background poller for activity state.

    One timer, one backend connection. Screens subscribe via callback
    and receive the full activity cache on each tick.
    """
    def __init__(self, jarvis_client: Any, poll_interval: float = 3.0):
        self._client = jarvis_client
        self._interval = poll_interval
        self._task: asyncio.Task | None = None
        self._callbacks: list[PollCallback] = []
        self._cache: dict[str, Any] = {"activities": [], "counts": {}}

    @property
    def cache(self) -> dict[str, Any]:
        return self._cache

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    @property
    def subscriber_count(self) -> int:
        return len(self._callbacks)

    def subscribe(self, callback: PollCallback) -> None:
        if callback not in self._callbacks:
            self._callbacks.append(callback)
            asyncio.ensure_future(callback(self._cache))

    def unsubscribe(self, callback: PollCallback) -> None:
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.ensure_future(self._run())

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _run(self) -> None:
        while True:
            try:
                await self._poll()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("ActivityUpdateService poll: %s", e)
            await asyncio.sleep(self._interval)

    async def _poll(self) -> None:
        activities = await self._client.get_activities()
        counts = await self._client.get_activity_counts()
        self._cache = {"activities": activities, "counts": counts}
        for cb in self._callbacks:
            try:
                await cb(self._cache)
            except Exception as e:
                logger.warning("ActivityUpdateService callback: %s", e)
