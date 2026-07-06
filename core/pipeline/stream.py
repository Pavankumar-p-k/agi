from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Literal

from core.pipeline.base import HookRegistry, PipelineStage, StageOutcome
from core.pipeline.context import PipelineContext
from core.pipeline.messages import Request
from core.pipeline.pipeline import Pipeline, get_pipeline

logger = logging.getLogger(__name__)

StreamEventType = Literal[
    "stage_start",
    "stage_end",
    "stage_error",
    "pipeline_start",
    "pipeline_end",
    "pipeline_error",
    "pipeline_cancelled",
]


@dataclass
class StreamEvent:
    event_type: StreamEventType
    stage: str = ""
    data: dict[str, Any] | None = None
    error: str | None = None


async def stream_pipeline(request: Request) -> AsyncGenerator[StreamEvent, None]:
    """Run the canonical pipeline and yield lifecycle :class:`StreamEvent`\\ s.

    Usage::

        async for event in stream_pipeline(request):
            match event.event_type:
                case "stage_start":
                    print(f"→ {event.stage}")
                case "stage_end":
                    print(f"✓ {event.stage}")
                case "pipeline_end":
                    print(f"Done: {event.data}")

    After iteration completes the caller can inspect ``event.data`` on the
    final ``pipeline_end`` / ``pipeline_error`` event.

    Args:
        request: Transport-agnostic request.

    Yields:
        :class:`StreamEvent` instances for each stage lifecycle transition.
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

    async for event in pipeline.stream(ctx):
        yield event


async def _run_pipeline_and_collect(request: Request) -> tuple[PipelineContext, list[StreamEvent]]:
    """Run the pipeline in streaming mode and collect all events + final context.

    Convenience helper for tests and non-streaming callers that want to
    observe the lifecycle events.
    """
    events: list[StreamEvent] = []
    async for event in stream_pipeline(request):
        events.append(event)
    return events[-1].data.get("_context") if events[-1].data else None, events  # type: ignore[return-value]


# ── Stream support added to Pipeline ──────────────────────────────────────────


async def _pipeline_stream(
    self: Pipeline,
    context: PipelineContext | None = None,
) -> AsyncGenerator[StreamEvent, None]:
    """Execute the pipeline and yield lifecycle :class:`StreamEvent`\\ s.

    This is the low-level streaming entry point.  Most callers should use
    the module-level :func:`stream_pipeline` instead.

    Args:
        context: Optional pre-built context; a new one is created if omitted.

    Yields:
        :class:`StreamEvent` for each stage lifecycle transition.
    """
    if context is None:
        context = PipelineContext(
            request_id=uuid.uuid4().hex,
            transport="unknown",
        )

    logger.info("Pipeline stream start", extra={"activity_id": context.activity_id, "request_id": context.request_id})
    context.pipeline_version = self.version

    yield StreamEvent(
        event_type="pipeline_start",
        data={"request_id": context.request_id, "transport": context.transport},
    )

    for stage in self._stages:
        if self._cancelled or context.cancelled:
            context.execution_state = "cancelled"
            context.error = "Pipeline was cancelled"
            logger.info("Pipeline cancelled at stage '%s'", stage.name)
            yield StreamEvent(
                event_type="pipeline_cancelled",
                stage=stage.name,
                error=context.error,
            )
            break

        stage_name = stage.name
        context.span_stack.append(stage_name)

        yield StreamEvent(event_type="stage_start", stage=stage_name)

        await self._hooks.fire_before(stage_name, context)

        retry_count = 0
        max_retries = getattr(stage, "max_retries", 3)
        timeout = getattr(stage, "timeout", None)

        stage_succeeded = False
        while True:
            try:
                coro = stage.execute(context)
                if timeout is not None:
                    coro = asyncio.wait_for(coro, timeout=timeout)
                result = await coro
            except asyncio.TimeoutError:
                logger.error("Stage '%s' timed out after %ss", stage_name, timeout)
                if retry_count < max_retries:
                    retry_count += 1
                    logger.warning("Retrying stage '%s' after timeout (%d/%d)", stage_name, retry_count, max_retries)
                    yield StreamEvent(
                        event_type="stage_error", stage=stage_name,
                        error=f"Timeout (retry {retry_count}/{max_retries})",
                    )
                    continue
                context.execution_state = "failed"
                context.error = f"stage '{stage_name}' timed out after {retry_count + 1} attempts"
                context.span_stack.pop()
                yield StreamEvent(
                    event_type="stage_error", stage=stage_name,
                    error=context.error,
                )
                break
            except Exception as exc:
                logger.exception("Stage '%s' raised unexpected exception", stage_name)
                if retry_count < max_retries:
                    retry_count += 1
                    logger.warning("Retrying stage '%s' after exception (%d/%d)", stage_name, retry_count, max_retries)
                    yield StreamEvent(
                        event_type="stage_error", stage=stage_name,
                        error=f"Exception (retry {retry_count}/{max_retries}): {exc}",
                    )
                    continue
                context.execution_state = "failed"
                context.error = f"stage '{stage_name}' raised: {exc}"
                context.span_stack.pop()
                yield StreamEvent(
                    event_type="stage_error", stage=stage_name,
                    error=context.error,
                )
                break

            if result.metrics:
                context.metrics[stage_name] = result.metrics

            outcome = result.outcome
            context = result.context

            if outcome == StageOutcome.CONTINUE:
                context.span_stack.pop()
                stage_succeeded = True
                break

            if outcome == StageOutcome.SHORT_CIRCUIT:
                logger.info("Pipeline short-circuited at stage '%s' — reason: %s", stage_name, result.error)
                context.execution_state = "short_circuited"
                context.error = result.error
                context.span_stack.pop()
                yield StreamEvent(
                    event_type="stage_error", stage=stage_name,
                    error=f"Short circuit: {result.error}",
                )
                break

            if outcome == StageOutcome.RETRY:
                if retry_count < max_retries:
                    retry_count += 1
                    logger.warning("Stage '%s' requested retry (%d/%d)", stage_name, retry_count, max_retries)
                    yield StreamEvent(
                        event_type="stage_error", stage=stage_name,
                        error=f"Retry ({retry_count}/{max_retries})",
                    )
                    continue
                logger.error("Stage '%s' exhausted retries (%d) — failing", stage_name, max_retries)
                context.execution_state = "failed"
                context.error = result.error or f"stage '{stage_name}' exhausted retries"
                context.span_stack.pop()
                yield StreamEvent(
                    event_type="stage_error", stage=stage_name,
                    error=context.error,
                )
                break

            if outcome == StageOutcome.FAIL:
                logger.error("Pipeline failed at stage '%s' — %s", stage_name, result.error)
                context.execution_state = "failed"
                context.error = result.error
                context.span_stack.pop()
                yield StreamEvent(
                    event_type="stage_error", stage=stage_name,
                    error=context.error,
                )
                break

            if outcome == StageOutcome.DEFER:
                logger.info("Pipeline deferred at stage '%s' — %s", stage_name, result.error)
                context.execution_state = "deferred"
                context.error = result.error
                context.span_stack.pop()
                yield StreamEvent(
                    event_type="stage_error", stage=stage_name,
                    error=f"Deferred: {result.error}",
                )
                break

            if outcome == StageOutcome.CANCELLED:
                logger.info("Pipeline cancelled at stage '%s' — %s", stage_name, result.error)
                context.execution_state = "cancelled"
                context.error = result.error or "Stage requested cancellation"
                context.span_stack.pop()
                yield StreamEvent(
                    event_type="pipeline_cancelled", stage=stage_name,
                    error=context.error,
                )
                break

        await self._hooks.fire_after(stage_name, context)

        if stage_succeeded:
            metrics = context.metrics.get(stage_name, {})
            yield StreamEvent(
                event_type="stage_end", stage=stage_name,
                data={"metrics": metrics} if metrics else None,
            )

        if context.execution_state in ("failed", "short_circuited", "deferred", "cancelled"):
            break

    # Build response metadata
    response_metadata: dict[str, Any] = dict(context.metrics)
    if context.epistemic_tags:
        response_metadata["epistemic_tags"] = list(context.epistemic_tags)
    if context.formatted_response and context.formatted_response.get("epistemic"):
        response_metadata["epistemic"] = context.formatted_response["epistemic"]
    response_metadata["pipeline_version"] = context.pipeline_version
    response_metadata["activity_id"] = context.activity_id
    response_metadata["trace_id"] = context.trace_id

    if context.execution_state == "failed":
        yield StreamEvent(
            event_type="pipeline_error",
            error=context.error,
            data={"_context": context, "metadata": response_metadata},
        )
    elif context.execution_state == "cancelled":
        yield StreamEvent(
            event_type="pipeline_cancelled",
            error=context.error,
            data={"_context": context, "metadata": response_metadata},
        )
    else:
        yield StreamEvent(
            event_type="pipeline_end",
            data={"_context": context, "execution_state": context.execution_state, "metadata": response_metadata},
        )

    logger.info("Pipeline stream end — state=%s", context.execution_state, extra={"activity_id": context.activity_id, "request_id": context.request_id})


# Monkey-patch Pipeline.stream
Pipeline.stream = _pipeline_stream  # type: ignore[assignment]
