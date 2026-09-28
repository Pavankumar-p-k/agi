"""Forward observations produced by remote workers.

Every forwarded observation is stamped with the originating ``worker_id``
so traces remain attributable across the cluster (Rule 40).
"""
from __future__ import annotations

import dataclasses
import logging
from typing import Any, Iterable, Optional

logger = logging.getLogger(__name__)


def stamp_worker_id(observation: Any, worker_id: str) -> Any:
    """Return *observation* with ``worker_id`` set (frozen-safe)."""
    if observation is None or not worker_id:
        return observation
    if getattr(observation, "worker_id", None) == worker_id:
        return observation
    try:
        return dataclasses.replace(observation, worker_id=worker_id)
    except (TypeError, ValueError):
        try:
            object.__setattr__(observation, "worker_id", worker_id)
        except Exception:  # noqa: BLE001 — best effort
            pass
        return observation


def stamp_observations(observations: Iterable[Any], worker_id: str) -> tuple:
    """Stamp a batch of observations with the producing worker's id."""
    return tuple(stamp_worker_id(o, worker_id) for o in (observations or ()))


async def publish_worker_observations(observations: Iterable[Any], worker_id: str,
                                      hub: Optional[Any] = None) -> int:
    """Publish a remote worker's observations to the observation hub."""
    stamped = list(stamp_observations(observations, worker_id))
    if not stamped:
        return 0
    if hub is None:
        try:
            from core.observation.hub import get_hub
            hub = get_hub()
        except Exception as exc:  # noqa: BLE001 — hub is optional
            logger.debug("observation hub unavailable: %s", exc)
            return 0
    publisher = getattr(hub, "publish", None) or getattr(hub, "publish_observation_async", None)
    if publisher is None:
        return 0
    for observation in stamped:
        result = publisher(observation)
        if hasattr(result, "__await__"):
            await result
    return len(stamped)


__all__ = ["stamp_worker_id", "stamp_observations", "publish_worker_observations"]
