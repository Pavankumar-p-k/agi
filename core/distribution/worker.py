"""Worker endpoint and control protocols."""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from core.distribution.contracts import (
    HealthStatus,
    WorkerRequest,
    WorkerResponse,
)


@runtime_checkable
class WorkerEndpoint(Protocol):
    """The surface every worker exposes to a transport."""

    async def execute(self, request: WorkerRequest) -> WorkerResponse: ...
    async def health(self) -> HealthStatus: ...
    async def heartbeat(self) -> None: ...
    async def shutdown(self) -> None: ...


@runtime_checkable
class WorkerControl(Protocol):
    """Administrative surface for supervising a worker."""

    @property
    def worker_id(self) -> str: ...
    def status(self) -> Any: ...
    async def drain(self) -> None: ...


__all__ = ["WorkerEndpoint", "WorkerControl"]
