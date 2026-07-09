from __future__ import annotations

import logging

from core.distribution.contracts import (
    HealthStatus,
    WorkerRequest,
    WorkerResponse,
)
from core.distribution.worker import WorkerControl, WorkerEndpoint

logger = logging.getLogger(__name__)


class LocalWorker(WorkerEndpoint, WorkerControl):
    """A worker that executes the pipeline in the current process.

    Always available — never goes OFFLINE.  Used as fallback when
    no remote worker is compatible.
    """

    async def execute(self, request: WorkerRequest) -> WorkerResponse:
        from core.pipeline.pipeline import process_message

        logger.info("LocalWorker executing request %s", request.request.text[:50])
        response = await process_message(request.request)
        outcome = response if hasattr(response, "observations") else None
        return WorkerResponse(
            outcome=outcome,
            observations=(),
            metrics=None,
        )

    async def health(self) -> HealthStatus:
        return HealthStatus.HEALTHY

    async def heartbeat(self) -> None:
        pass

    async def shutdown(self) -> None:
        pass
