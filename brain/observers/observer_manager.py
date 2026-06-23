from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any

from brain.events.event_bus import Event, global_event_bus, EventBus

logger = logging.getLogger(__name__)


class Observer(ABC):
    """Base class for all environment observers.

    An observer watches some aspect of the environment and publishes
    events to the EventBus when something happens.
    """

    def __init__(self, name: str, event_bus: EventBus | None = None,
                 poll_interval: float = 30.0):
        self.name = name
        self.bus = event_bus or global_event_bus
        self.poll_interval = poll_interval
        self._running = False
        self._task: asyncio.Task | None = None

    @abstractmethod
    async def observe(self) -> list[Event]:
        """Called on each tick. Return zero or more events to publish."""
        ...

    async def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run())
        logger.info("[Observer] %s started (poll=%ss)", self.name, self.poll_interval)

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("[Observer] %s stopped", self.name)

    async def _run(self):
        while self._running:
            try:
                events = await self.observe()
                for event in events:
                    await self.bus.publish(event)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception("[Observer] %s observe error: %s", self.name, e)
            await asyncio.sleep(self.poll_interval)


class ObserverManager:
    """Manages multiple observers — start/stop all, get status."""

    def __init__(self, event_bus: EventBus | None = None):
        self.bus = event_bus or global_event_bus
        self._observers: dict[str, Observer] = {}

    def register(self, observer: Observer):
        self._observers[observer.name] = observer
        logger.info("[ObserverManager] registered: %s", observer.name)

    def unregister(self, name: str):
        self._observers.pop(name, None)

    def get(self, name: str) -> Observer | None:
        return self._observers.get(name)

    async def start_all(self):
        for name, observer in self._observers.items():
            await observer.start()
        logger.info("[ObserverManager] started %d observers", len(self._observers))

    async def stop_all(self):
        for name, observer in self._observers.items():
            await observer.stop()
        logger.info("[ObserverManager] stopped %d observers", len(self._observers))

    def list_observers(self) -> list[dict]:
        return [
            {"name": o.name, "running": o._running, "poll_interval": o.poll_interval}
            for o in self._observers.values()
        ]


observer_manager = ObserverManager()
