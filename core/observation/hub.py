from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Callable

from core.event_bus import Event, Subscription, global_event_bus

if TYPE_CHECKING:
    from core.pipeline.observation import Observation

logger = logging.getLogger(__name__)

OBSERVATION_OBSERVED = "observation.observed"
OBSERVATION_CREATED = "observation.created"

_observation_hub: ObservationHub | None = None


class ObservationHub:
    """Publishes Observation events to the canonical EventBus.

    Design:
    - Thin adapter — no business logic, no subscriber awareness.
    - Converts Observation objects to Event objects and publishes via EventBus.
    - Uses ``observation.observed`` as the primary event type.
    - ``get_hub()`` returns a singleton for convenience; the hub can also be
      instantiated directly with a custom EventBus for testing.
    """

    def __init__(self, bus: EventBus | None = None):
        self._bus = bus or global_event_bus

    def publish_observation(self, observation: Observation, *,
                            source: str = "observation.hub") -> None:
        """Publish a single Observation as an Event on the bus."""
        event = Event(
            type=OBSERVATION_OBSERVED,
            source=source,
            payload=observation.to_dict(),
        )
        self._bus.publish_sync(event)

    async def publish_observation_async(self, observation: Observation, *,
                                        source: str = "observation.hub") -> None:
        """Async variant of publish_observation."""
        event = Event(
            type=OBSERVATION_OBSERVED,
            source=source,
            payload=observation.to_dict(),
        )
        await self._bus.publish(event)

    def publish_observations(self, observations: list[Observation], *,
                             source: str = "observation.hub") -> None:
        """Publish multiple Observations."""
        for obs in observations:
            self.publish_observation(obs, source=source)

    async def publish_observations_async(self, observations: list[Observation], *,
                                         source: str = "observation.hub") -> None:
        """Async variant of publish_observations."""
        for obs in observations:
            await self.publish_observation_async(obs, source=source)

    def subscribe(self, handler: Callable[[Event], Any],
                  pattern: str = OBSERVATION_OBSERVED) -> Subscription:
        """Subscribe to observation events with a pattern filter.

        Default pattern matches all observation events.  Use a more specific
        pattern (e.g. ``"observation.created"``) to filter.
        """
        return self._bus.subscribe(pattern, handler)

    def subscribe_stream(self) -> Any:
        """Return an asyncio.Queue that receives observation events."""
        return self._bus.subscribe_stream()


def get_hub() -> ObservationHub:
    global _observation_hub
    if _observation_hub is None:
        _observation_hub = ObservationHub()
    return _observation_hub


def reset_hub() -> None:
    global _observation_hub
    _observation_hub = None
