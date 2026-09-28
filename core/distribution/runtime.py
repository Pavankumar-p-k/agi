"""RemoteExecutionRuntime — dispatches work to the best compatible worker.

Dispatch always goes through the :class:`Transport` protocol (Rule 37). When
no compatible worker is available the runtime falls back to running the
canonical pipeline locally via ``process_message`` (Rule 36), so a degraded
cluster never drops work.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from core.distribution.contracts import (
    ExecutionAffinity,
    WorkerRequest,
    WorkerResponse,
)
from core.distribution.registry import (
    PIPELINE_VERSION,
    RUNTIME_SPEC_VERSION,
    WorkerRegistration,
    get_worker_registry,
)
from core.distribution.transport import InProcessTransport, Transport

logger = logging.getLogger(__name__)


class RemoteExecutionRuntime:
    """Worker-aware execution runtime."""

    def __init__(
        self,
        pipeline_version: str = PIPELINE_VERSION,
        runtime_spec_version: str = RUNTIME_SPEC_VERSION,
        registry: Any = None,
        transport: Optional[Transport] = None,
        worker_protocol_version: str = "1.0",
    ) -> None:
        self.pipeline_version = pipeline_version
        self.runtime_spec_version = runtime_spec_version
        self.worker_protocol_version = worker_protocol_version
        self.registry = registry
        self.transport = transport
        self.last_worker_id: str = ""
        self._affinity: ExecutionAffinity = ExecutionAffinity()

    # ── helpers ─────────────────────────────────────────────────────
    def _registry(self) -> Any:
        return self.registry if self.registry is not None else get_worker_registry()

    def _compatible(self, registration: WorkerRegistration) -> bool:
        return self._registry().check_version_compatibility(
            registration, self.pipeline_version, self.runtime_spec_version,
        ).compatible

    @staticmethod
    def _to_request(payload: Any, affinity: ExecutionAffinity) -> WorkerRequest:
        if isinstance(payload, WorkerRequest):
            return payload
        if isinstance(payload, dict):
            text = payload.get("text") or payload.get("request") or ""
            transport = payload.get("transport") or "remote"
            metadata = {k: v for k, v in payload.items()
                        if k not in ("text", "request", "transport")}
        else:
            text, transport, metadata = str(payload), "remote", {}
        return WorkerRequest(
            request={"text": text, "transport": transport, **metadata},
            pipeline_version="1.0",
            runtime_spec_version="1.0",
            worker_protocol_version="1.0",
            tenant_id=affinity.tenant_id,
            capability=affinity.capability,
        )

    def select_worker(self, affinity: ExecutionAffinity) -> Optional[WorkerRegistration]:
        """Pick the first compatible, eligible worker (None if none)."""
        registry = self._registry()
        candidates = registry.discover(
            tenant_id=affinity.tenant_id, capability=affinity.capability,
        )
        if affinity.worker_id:
            for reg in candidates:
                if reg.worker_id == affinity.worker_id:
                    return reg
            return None
        for reg in candidates:
            if self._compatible(reg):
                return reg
        return None

    # ── dispatch ────────────────────────────────────────────────────
    async def execute(self, request: Any, affinity: Optional[ExecutionAffinity] = None) -> WorkerResponse:
        """Dispatch *request*, or run it locally when no worker matches."""
        affinity = affinity or ExecutionAffinity()
        self._affinity = affinity
        registration = self.select_worker(affinity)
        if registration is None:
            return await self._execute_local(request)

        payload = self._to_request(request, affinity)
        payload.worker_id = registration.worker_id
        payload.pipeline_version = self.pipeline_version
        payload.runtime_spec_version = self.runtime_spec_version
        payload.worker_protocol_version = self.worker_protocol_version
        self.last_worker_id = registration.worker_id

        transport = self.transport
        if transport is None:
            worker_fn = getattr(registration.worker, "execute", None)
            if worker_fn is None:
                logger.warning("worker %s has no execute() — running locally",
                               registration.worker_id)
                return await self._execute_local(request)
            transport = InProcessTransport(worker_fn=worker_fn)
        return await transport.send(payload)

    async def _execute_local(self, request: Any, **kwargs: Any) -> WorkerResponse:
        """Canonical local execution: the pipeline's own process_message()."""
        from core.pipeline.messages import Request
        from core.pipeline.pipeline import process_message

        if isinstance(request, WorkerRequest):
            body = request.request
        else:
            body = request
        if isinstance(body, Request):
            msg = body
        elif isinstance(body, dict):
            text = body.get("text") or body.get("request") or ""
            msg = Request(text=str(text), transport=str(body.get("transport") or "remote"))
        else:
            msg = Request(text=str(body or ""), transport="remote")
        response = await process_message(msg)
        return WorkerResponse(
            outcome=response,
            observations=(),
            metrics=None,
            worker_id="local",
            error=getattr(response, "error", None),
            success=not getattr(response, "error", None),
        )


__all__ = ["RemoteExecutionRuntime"]
