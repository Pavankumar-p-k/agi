from __future__ import annotations

import logging
from typing import Any

from core.distribution.contracts import WorkerResponse
from core.distribution.registry import get_worker_registry
from core.runtime import RuntimeContext

logger = logging.getLogger(__name__)


class FederatedObservationHub:
    """Observation hub that forwards observations to remote subscribers.

    Wraps the local ``ObservationHub`` and publishes to remote workers
    that have subscribed for observation events.
    """

    def __init__(self) -> None:
        self._remote_subscribers: dict[str, Any] = {}

    async def publish(self, ctx: RuntimeContext, observation: Any) -> None:
        from core.observation.hub import get_hub

        hub = get_hub()
        await hub.publish(observation)

        for worker_id, transport in self._remote_subscribers.items():
            try:
                await transport.send({
                    "type": "observation",
                    "observation": observation,
                    "activity_id": ctx.activity_id,
                    "request_id": ctx.request_id,
                }, address=worker_id)
            except Exception as exc:
                logger.warning("Failed to forward observation to worker %s: %s",
                                worker_id, exc)

    def subscribe_remote(self, worker_id: str, transport: Any) -> None:
        self._remote_subscribers[worker_id] = transport

    def unsubscribe_remote(self, worker_id: str) -> None:
        self._remote_subscribers.pop(worker_id, None)


class RemoteObservationCollector:
    """Collects observations emitted by remote workers during execution."""

    def __init__(self) -> None:
        self._observations: list[dict[str, Any]] = []

    def collect(self, response: WorkerResponse) -> list[dict[str, Any]]:
        collected: list[dict[str, Any]] = []
        for obs in response.observations:
            entry = {
                "activity_id": obs.activity_id,
                "source": obs.source,
                "type": obs.type,
                "payload": obs.payload,
                "worker_id": getattr(obs, "worker_id", None),
            }
            collected.append(entry)
            self._observations.append(entry)
        return collected
