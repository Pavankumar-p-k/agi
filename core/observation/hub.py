"""ObservationHub — fans observations out to subscribers over the EventBus."""
from __future__ import annotations

import asyncio
from typing import Any, Callable, Optional

from core.event_bus import EventBus, Event, global_event_bus

OBSERVATION_CREATED = "OBSERVATION_CREATED"
OBSERVATION_OBSERVED = "OBSERVATION_OBSERVED"


class ObservationHub:
    """Publishes observations onto the bus, preserving resource scope."""

    def __init__(self, bus: Optional[EventBus] = None) -> None:
        self._bus = bus if bus is not None else global_event_bus
        self._observations: list[Any] = []
        self._streams: list[asyncio.Queue] = []

    @property
    def bus(self) -> EventBus:
        return self._bus

    # ── payload normalization ────────────────────────────────────────
    @staticmethod
    def _payload(observation: Any) -> dict:
        if hasattr(observation, "to_dict"):
            return dict(observation.to_dict())
        return {"observation": str(observation)}

    async def _emit(self, observation: Any) -> None:
        self._observations.append(observation)
        payload = self._payload(observation)
        scope = payload.get("resource_scope") or {}
        event = Event(
            type=OBSERVATION_OBSERVED,
            source="observation.hub",
            payload=payload,
            resource_scope=dict(scope) if isinstance(scope, dict) else {},
        )
        await self.bus.publish(event)
        for q in list(self._streams):
            await q.put({"channel": OBSERVATION_OBSERVED, "payload": payload})

    # ── publishing ───────────────────────────────────────────────────
    async def publish_observation_async(self, observation: Any) -> None:
        await self._emit(observation)

    async def publish_observations_async(self, observations) -> None:
        for obs in observations:
            await self._emit(obs)

    def publish_observation(self, observation: Any) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(self.publish_observation_async(observation))
            return
        loop.create_task(self._emit(observation))

    # ── subscription ─────────────────────────────────────────────────
    def subscribe(self, handler: Callable, pattern: str = OBSERVATION_OBSERVED):
        return self.bus.subscribe(pattern, handler)

    def subscribe_stream(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._streams.append(q)
        return q

    # ── introspection ────────────────────────────────────────────────
    @property
    def observations(self) -> list:
        return list(self._observations)


_default_hub: Optional[ObservationHub] = None


def get_hub() -> ObservationHub:
    global _default_hub
    if _default_hub is None:
        _default_hub = ObservationHub()
    return _default_hub


def reset_hub() -> None:
    global _default_hub
    _default_hub = None


# Backwards-compatible factory alias used by some callers.
def _observation_hub(bus: Optional[EventBus] = None) -> ObservationHub:
    return ObservationHub(bus=bus)


__all__ = ["ObservationHub", "OBSERVATION_OBSERVED", "OBSERVATION_CREATED",
           "get_hub", "reset_hub", "_observation_hub"]
