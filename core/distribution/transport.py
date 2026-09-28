"""Transport protocol — the only sanctioned remote dispatch path (Rule 37).

``InProcessTransport`` calls a worker directly; network transports
(HTTP/gRPC/queue) implement the same :class:`Transport` surface so the
runtime never needs to know which one it is holding.
"""
from __future__ import annotations

import asyncio
import inspect
from typing import Any, Callable, Optional, Protocol, runtime_checkable

from core.distribution.contracts import WorkerRequest, WorkerResponse


@runtime_checkable
class Transport(Protocol):
    """Dispatch a :class:`WorkerRequest` and return a :class:`WorkerResponse`."""

    async def send(self, request: WorkerRequest) -> WorkerResponse: ...

    async def close(self) -> None: ...


class InProcessTransport:
    """Calls a worker function in the current process (no serialisation)."""

    def __init__(self, worker_fn: Optional[Callable] = None,
                 worker: Any = None, timeout: Optional[float] = None) -> None:
        if worker_fn is None and worker is not None:
            worker_fn = getattr(worker, "execute", None)
        if worker_fn is None:
            raise ValueError("InProcessTransport requires a worker_fn or worker")
        self.worker_fn = worker_fn
        self.worker = worker
        self.timeout = timeout

    async def send(self, request: WorkerRequest) -> WorkerResponse:
        result = self.worker_fn(request)
        if inspect.isawaitable(result):
            if self.timeout:
                result = await asyncio.wait_for(result, timeout=self.timeout)
            else:
                result = await result
        if isinstance(result, WorkerResponse):
            return result
        if isinstance(result, dict):
            return WorkerResponse.from_dict(result)
        return WorkerResponse(outcome=result)

    async def close(self) -> None:  # pragma: no cover - nothing to release
        return None

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"InProcessTransport(worker_fn={getattr(self.worker_fn, '__name__', self.worker_fn)})"


__all__ = ["Transport", "InProcessTransport"]
