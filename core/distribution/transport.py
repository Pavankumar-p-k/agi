from __future__ import annotations

import json
import logging
from typing import Any, Protocol

from core.distribution.contracts import WorkerRequest, WorkerResponse

logger = logging.getLogger(__name__)


class Transport(Protocol):
    """Pluggable transport for remote worker communication.

    Implementations handle serialization, networking, and protocol
    details.  ``RemoteExecutionRuntime`` depends only on this protocol.
    """

    async def send(
        self,
        request: WorkerRequest,
        address: str = "",
    ) -> WorkerResponse:
        ...


class InProcessTransport:
    """Transport that calls a worker function directly.

    Used for tests and local-when-possible execution.  No network
    overhead — the worker is a callable or a WorkerEndpoint.

    If *registry* is provided, ``send(address=worker_id)`` will look up
    the worker and call ``execute`` on it.
    """

    def __init__(self, worker_fn: Any = None, registry: Any = None) -> None:
        self._worker_fn = worker_fn
        self._registry = registry

    async def send(self, request: WorkerRequest, address: str = "") -> WorkerResponse:
        from core.pipeline.pipeline import process_message

        # If a worker_fn was provided at construction, use it
        if self._worker_fn is not None:
            if hasattr(self._worker_fn, "execute"):
                return await self._worker_fn.execute(request)
            return await self._worker_fn(request)

        # If an address was given, look up the worker via registry
        if address and self._registry is not None:
            registration = self._registry.get_worker(address)
            if registration is not None and hasattr(registration.worker, "execute"):
                return await registration.worker.execute(request)
            raise RuntimeError(f"No worker found for address: {address}")

        # Default fallback: pipe through process_message
        response = await process_message(request.request)
        outcome = response if hasattr(response, "observations") else None
        return WorkerResponse(
            outcome=outcome,
            observations=(),
            metrics=None,
        )


class HttpTransport:
    """HTTP+JSON transport for remote workers.

    Serialises ``WorkerRequest`` to JSON, sends via POST, and
    deserialises the ``WorkerResponse``.
    """

    def __init__(self, timeout: int = 30) -> None:
        self._timeout = timeout

    async def send(self, request: WorkerRequest, address: str = "") -> WorkerResponse:
        import httpx

        url = f"{address}/execute"
        payload = request.to_dict()

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()

        return self._response_from_dict(data)

    def _response_from_dict(self, data: dict[str, Any]) -> WorkerResponse:
        from core.pipeline.architecture_metrics import ArchitectureMetrics
        from core.pipeline.observation import Observation
        from core.pipeline.outcome import Outcome

        outcome = Outcome(
            success=data.get("outcome", {}).get("success", True),
            outputs=data.get("outcome", {}).get("outputs", {}),
            tool_results=data.get("outcome", {}).get("tool_results", []),
            observations=[],
            metrics=data.get("outcome", {}).get("metrics", {}),
            activity_id=data.get("outcome", {}).get("activity_id", ""),
        )
        observations = tuple(
            Observation.new(
                activity_id=obs.get("activity_id", ""),
                source=obs.get("source", "remote"),
                type_=obs.get("type", "unknown"),
                payload=obs.get("payload", {}),
            )
            for obs in data.get("observations", [])
        )
        metrics = None
        if data.get("metrics"):
            metrics = ArchitectureMetrics(
                observations=len(observations),
                tenant_id=data["metrics"].get("tenant_id"),
                workspace_id=data["metrics"].get("workspace_id"),
            )
        return WorkerResponse(outcome=outcome, observations=observations, metrics=metrics)
