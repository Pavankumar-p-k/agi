"""LocalWorker — an in-process worker endpoint.

Executes through the canonical ``process_message`` (Rule 36) so a local
worker and a remote worker behave identically.
"""
from __future__ import annotations

import time
from typing import Any, Optional

from core.distribution.contracts import (
    HealthStatus,
    WorkerRequest,
    WorkerResponse,
)


class LocalWorker:
    """Runs requests against the local pipeline."""

    def __init__(self, worker_id: str = "local", pipeline: Any = None) -> None:
        self.worker_id = worker_id
        self.pipeline = pipeline
        self.execution_count = 0

    async def execute(self, request: WorkerRequest) -> WorkerResponse:
        from core.pipeline.messages import Request
        from core.pipeline.pipeline import process_message

        self.execution_count += 1
        started = time.monotonic()
        body = request.request if isinstance(request, WorkerRequest) else request
        if isinstance(body, Request):
            msg = body
        elif isinstance(body, dict):
            msg = Request(text=str(body.get("text") or ""),
                          transport=str(body.get("transport") or "worker"))
        else:
            msg = Request(text=str(body or ""), transport="worker")
        try:
            response = await process_message(msg)
        except Exception as exc:  # noqa: BLE001 — surface as a failed response
            return WorkerResponse(
                outcome=None, observations=(), metrics=None,
                worker_id=self.worker_id, error=f"{type(exc).__name__}: {exc}",
                success=False,
                duration_ms=(time.monotonic() - started) * 1000,
            )
        return WorkerResponse(
            outcome=response,
            observations=(),
            metrics=None,
            worker_id=self.worker_id,
            error=getattr(response, "error", None),
            success=not getattr(response, "error", None),
            duration_ms=(time.monotonic() - started) * 1000,
        )

    async def health(self) -> HealthStatus:
        return HealthStatus.HEALTHY

    async def heartbeat(self) -> None:
        return None

    async def shutdown(self) -> None:
        return None


__all__ = ["LocalWorker"]
