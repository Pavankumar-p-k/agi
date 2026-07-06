from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from core.pipeline.base import HookRegistry, PipelineStage, StageOutcome
from core.pipeline.context import PipelineContext
from core.pipeline.messages import Request, Response
from core.pipeline.stages import DEFAULT_STAGES

logger = logging.getLogger(__name__)

# ── Activity-aware logging adapter ───────────────────────────────────────────


class _ActivityAdapter(logging.LoggerAdapter):
    """LoggerAdapter that injects activity context into every log record."""

    def process(self, msg: str, kwargs: Any) -> tuple[str, Any]:
        ctx = kwargs.pop("_ctx", None)
        stage = kwargs.pop("_stage", None)
        extra = kwargs.setdefault("extra", {})
        if ctx:
            extra["activity_id"] = ctx.activity_id
            extra["request_id"] = ctx.request_id
        if stage:
            extra["stage"] = stage
        return msg, kwargs


_logger = _ActivityAdapter(logger, {})


# ── Default pipeline instance (populated by bootstrap code) ──────────────────

_default_pipeline: Pipeline | None = None


def get_pipeline() -> Pipeline:
    """Return the application-wide default pipeline instance.

    The instance is created lazily on first call with the default stages
    (ADR-006 order).  Bootstrap code may call ``add_stage`` / ``remove_stage``
    to customise for the deployment.
    """
    global _default_pipeline
    if _default_pipeline is None:
        _default_pipeline = Pipeline()
        for _name, stage_factory in DEFAULT_STAGES:
            _default_pipeline.add_stage(stage_factory())
    return _default_pipeline


def set_pipeline(pipeline: Pipeline) -> None:
    """Override the default pipeline (used in tests)."""
    global _default_pipeline
    _default_pipeline = pipeline


async def process_message(request: Request) -> Response:
    """Canonical entry point for all request processing.

    Every transport adapter calls this single function.  It:
    1. Creates a ``PipelineContext`` from the given ``Request``
    2. Runs the default pipeline
    3. Extracts the result into a ``Response``

    Args:
        request: Transport-agnostic request.

    Returns:
        A ``Response`` containing the result text, optional structured data,
        and metadata (token counts, duration, traces, …).
    """
    pipeline = get_pipeline()
    ctx = PipelineContext(
        request_id=uuid.uuid4().hex,
        transport=request.transport,
        user_id=request.user_id,
        session_id=request.session_id,
        raw_input=request.text,
        attachments=request.attachments,
        metadata=dict(request.metadata),
    )
    ctx.trace_id = ctx.request_id
    ctx = await pipeline.execute(ctx)

    response_metadata: dict[str, Any] = dict(ctx.metrics)
    if ctx.epistemic_tags:
        response_metadata["epistemic_tags"] = list(ctx.epistemic_tags)
    if ctx.formatted_response and ctx.formatted_response.get("epistemic"):
        response_metadata["epistemic"] = ctx.formatted_response["epistemic"]
    response_metadata["pipeline_version"] = ctx.pipeline_version
    response_metadata["activity_id"] = ctx.activity_id
    response_metadata["trace_id"] = ctx.trace_id

    return Response(
        text=ctx.formatted_response.get("text", "") if ctx.formatted_response else "",
        error=ctx.error,
        data=ctx.formatted_response.get("data") if ctx.formatted_response else None,
        metadata=response_metadata,
    )


class Pipeline:
    """Canonical request processing pipeline.

    Stages are registered in order and executed sequentially for each request.
    The pipeline is transport-agnostic — transports call ``execute()`` through
    ``process_message()`` and receive a populated ``PipelineContext`` back.
    """

    version: str = "1.0"
    """Pipeline architecture version.  Increment on breaking changes."""

    def __init__(self) -> None:
        self._stages: list[PipelineStage] = []
        self._hooks = HookRegistry()
        self._cancelled: bool = False

    # ── Stage Registration ──────────────────────────────────────────────────

    @property
    def stages(self) -> list[PipelineStage]:
        return list(self._stages)

    def add_stage(self, stage: PipelineStage) -> Pipeline:
        self._stages.append(stage)
        return self

    def insert_stage(self, index: int, stage: PipelineStage) -> Pipeline:
        self._stages.insert(index, stage)
        return self

    def remove_stage(self, name: str) -> bool:
        for i, s in enumerate(self._stages):
            if s.name == name:
                del self._stages[i]
                return True
        return False

    # ── Hook Registration ───────────────────────────────────────────────────

    @property
    def hooks(self) -> HookRegistry:
        """Lifecycle hook registry for plugin integration."""
        return self._hooks

    # ── Cancellation ────────────────────────────────────────────────────────

    def cancel(self) -> None:
        """Request cancellation of the current pipeline execution.

        The pipeline checks the ``cancelled`` flag between stages.
        Long-running stages may also check ``context.cancelled``.
        """
        self._cancelled = True

    # ── Execution ───────────────────────────────────────────────────────────

    async def execute(self, context: PipelineContext | None = None) -> PipelineContext:
        if context is None:
            context = PipelineContext(
                request_id=uuid.uuid4().hex,
                transport="unknown",
            )

        _logger.info("Pipeline start", _ctx=context)
        context.pipeline_version = self.version

        for stage in self._stages:
            # Check for external cancellation
            if self._cancelled or context.cancelled:
                context.execution_state = "cancelled"
                context.error = "Pipeline was cancelled"
                _logger.info(f"Pipeline cancelled at stage '{stage.name}'", _ctx=context, _stage=stage.name)
                break

            stage_name = stage.name
            context.span_stack.append(stage_name)

            # Fire before-hooks
            await self._hooks.fire_before(stage_name, context)

            retry_count = 0
            max_retries = getattr(stage, "max_retries", 3)
            timeout = getattr(stage, "timeout", None)

            while True:
                try:
                    coro = stage.execute(context)
                    if timeout is not None:
                        coro = asyncio.wait_for(coro, timeout=timeout)
                    result = await coro
                except asyncio.TimeoutError:
                    _logger.error(f"Stage '{stage_name}' timed out after {timeout}s", _ctx=context, _stage=stage_name)
                    if retry_count < max_retries:
                        retry_count += 1
                        _logger.warning(f"Retrying stage '{stage_name}' after timeout ({retry_count}/{max_retries})", _ctx=context, _stage=stage_name)
                        continue
                    context.execution_state = "failed"
                    context.error = f"stage '{stage_name}' timed out after {retry_count + 1} attempts"
                    context.span_stack.pop()
                    break
                except Exception as exc:
                    _logger.exception(f"Stage '{stage_name}' raised unexpected exception", _ctx=context, _stage=stage_name)
                    if retry_count < max_retries:
                        retry_count += 1
                        _logger.warning(f"Retrying stage '{stage_name}' after exception ({retry_count}/{max_retries})", _ctx=context, _stage=stage_name)
                        continue
                    context.execution_state = "failed"
                    context.error = f"stage '{stage_name}' raised: {exc}"
                    context.span_stack.pop()
                    break

                # Merge any metrics the stage emitted
                if result.metrics:
                    context.metrics[stage_name] = result.metrics

                outcome = result.outcome
                context = result.context

                if outcome == StageOutcome.CONTINUE:
                    context.span_stack.pop()
                    break

                if outcome == StageOutcome.SHORT_CIRCUIT:
                    _logger.info(f"Pipeline short-circuited at stage '{stage_name}' — reason: {result.error}", _ctx=context, _stage=stage_name)
                    context.execution_state = "short_circuited"
                    context.error = result.error
                    context.span_stack.pop()
                    break

                if outcome == StageOutcome.RETRY:
                    if retry_count < max_retries:
                        retry_count += 1
                        _logger.warning(f"Stage '{stage_name}' requested retry ({retry_count}/{max_retries})", _ctx=context, _stage=stage_name)
                        continue
                    _logger.error(f"Stage '{stage_name}' exhausted retries ({max_retries}) — failing", _ctx=context, _stage=stage_name)
                    context.execution_state = "failed"
                    context.error = f"stage '{stage_name}' exhausted retries: {result.error}" if result.error else f"stage '{stage_name}' exhausted retries"
                    context.span_stack.pop()
                    break

                if outcome == StageOutcome.FAIL:
                    _logger.error(f"Pipeline failed at stage '{stage_name}' — {result.error}", _ctx=context, _stage=stage_name)
                    context.execution_state = "failed"
                    context.error = result.error
                    context.span_stack.pop()
                    break

                if outcome == StageOutcome.DEFER:
                    _logger.info(f"Pipeline deferred at stage '{stage_name}' — {result.error}", _ctx=context, _stage=stage_name)
                    context.execution_state = "deferred"
                    context.error = result.error
                    context.span_stack.pop()
                    break

                if outcome == StageOutcome.CANCELLED:
                    _logger.info(f"Pipeline cancelled at stage '{stage_name}' — {result.error}", _ctx=context, _stage=stage_name)
                    context.execution_state = "cancelled"
                    context.error = result.error or "Stage requested cancellation"
                    context.span_stack.pop()
                    break

            # Fire after-hooks
            await self._hooks.fire_after(stage_name, context)

        _logger.info(f"Pipeline end — state={context.execution_state}", _ctx=context)
        return context

    async def process_message(
        self,
        raw_input: str,
        transport: str,
        *,
        user_id: str | None = None,
        session_id: str | None = None,
        attachments: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> PipelineContext:
        """Convenience wrapper: build a context and execute against *this* pipeline.

        Prefer the module-level :func:`process_message` function for new code.
        This method is kept for cases where a specific pipeline instance is needed.
        """
        context = PipelineContext(
            request_id=uuid.uuid4().hex,
            transport=transport,
            user_id=user_id,
            session_id=session_id,
            raw_input=raw_input,
            attachments=attachments or [],
            metadata=metadata or {},
        )
        return await self.execute(context)
