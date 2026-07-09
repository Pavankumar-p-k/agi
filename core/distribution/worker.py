from __future__ import annotations

from typing import Protocol

from core.distribution.contracts import (
    HealthStatus,
    WorkerRequest,
    WorkerResponse,
)


class WorkerEndpoint(Protocol):
    """Remote worker execution contract.

    Responsible for receiving a ``WorkerRequest`` and returning a
    ``WorkerResponse``.  The worker must execute the exact same pipeline
    (``process_message``) as the local runtime.
    """

    async def execute(self, request: WorkerRequest) -> WorkerResponse:
        ...


class WorkerControl(Protocol):
    """Worker lifecycle management.

    Separate from ``WorkerEndpoint`` so that monitoring and orchestration
    can check health or trigger shutdown without mixing execution concerns.
    """

    async def health(self) -> HealthStatus:
        ...

    async def heartbeat(self) -> None:
        ...

    async def shutdown(self) -> None:
        ...
