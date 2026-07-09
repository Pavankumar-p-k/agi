from __future__ import annotations

import logging
from typing import Any

from core.distribution.contracts import (
    ExecutionAffinity,
    VersionCheck,
    WorkerRequest,
    WorkerResponse,
)
from core.distribution.registry import get_worker_registry
from core.distribution.transport import InProcessTransport, Transport

logger = logging.getLogger(__name__)


class RemoteExecutionRuntime:
    """Execution runtime that dispatches to remote workers.

    Discovers workers via ``WorkerRegistry``, checks version compatibility,
    and sends via the configured ``Transport``.  Falls back to local
    execution when no compatible worker is available.
    """

    def __init__(
        self,
        transport: Transport | None = None,
        pipeline_version: str = "1.0",
        runtime_spec_version: str = "1.0",
        worker_protocol_version: str = "1.0",
    ) -> None:
        self._transport = transport or InProcessTransport()
        self._pipeline_version = pipeline_version
        self._runtime_spec_version = runtime_spec_version
        self._worker_protocol_version = worker_protocol_version

    async def execute(
        self,
        request: Any,
        affinity: ExecutionAffinity | None = None,
    ) -> WorkerResponse:
        from core.pipeline.messages import Request as PipelineRequest
        from core.runtime import RuntimeContext

        if not isinstance(request, PipelineRequest):
            req = self._to_pipeline_request(request)
        else:
            req = request

        registry = get_worker_registry()
        ctx = RuntimeContext.__new__(RuntimeContext)
        worker_req = WorkerRequest(
            runtime_context=ctx,
            request=req,
            pipeline_version=self._pipeline_version,
            runtime_spec_version=self._runtime_spec_version,
            worker_protocol_version=self._worker_protocol_version,
        )

        tenant = affinity.tenant_id if affinity else None
        workers = registry.discover(tenant_id=tenant)

        # Filter by version compatibility
        compatible: list[Any] = []
        for w in workers:
            check = registry.check_version_compatibility(
                w, self._pipeline_version, self._runtime_spec_version
            )
            if check.compatible:
                compatible.append(w)

        if not compatible:
            logger.info("No compatible remote worker found, executing locally")
            return await self._execute_local(worker_req)

        target = compatible[0]
        logger.info("Dispatching to worker %s (tenant=%s)", target.worker_id, tenant)

        response = await self._transport.send(worker_req, address=target.address)
        return response

    async def _execute_local(self, request: WorkerRequest) -> WorkerResponse:
        from core.pipeline.pipeline import process_message

        response = await process_message(request.request)
        outcome = response if hasattr(response, "observations") else None
        return WorkerResponse(
            outcome=outcome,
            observations=(),
            metrics=None,
        )

    def _to_pipeline_request(self, raw: Any) -> Any:
        from core.pipeline.messages import Request as PipelineRequest

        if isinstance(raw, dict):
            return PipelineRequest(
                text=raw.get("text", ""),
                transport=raw.get("transport", "distribution"),
                user_id=raw.get("user_id"),
                metadata=raw.get("metadata", {}),
            )
        return raw
