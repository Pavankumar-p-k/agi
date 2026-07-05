from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from core.pipeline.base import PipelineStage, StageOutcome
from core.pipeline.context import PipelineContext
from core.pipeline.messages import Request, Response
from core.pipeline.stages import DEFAULT_STAGES

logger = logging.getLogger(__name__)

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
    ctx = await pipeline.execute(ctx)

    response_metadata: dict[str, Any] = dict(ctx.metrics)
    if ctx.epistemic_tags:
        response_metadata["epistemic_tags"] = list(ctx.epistemic_tags)
    if ctx.formatted_response and ctx.formatted_response.get("epistemic"):
        response_metadata["epistemic"] = ctx.formatted_response["epistemic"]

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

    def __init__(self) -> None:
        self._stages: list[PipelineStage] = []

    # ── Stage Registration ──────────────────────────────────────────────────

    @property
    def stages(self) -> list[PipelineStage]:
        return list(self._stages)

    def add_stage(self, stage: PipelineStage) -> Pipeline:
        """Append *stage* to the end of the pipeline.

        Returns ``self`` for fluent registration::

            pipeline = Pipeline()
            pipeline.add_stage(ReceiveStage()).add_stage(LoadContextStage())
        """
        self._stages.append(stage)
        return self

    def insert_stage(self, index: int, stage: PipelineStage) -> Pipeline:
        """Insert *stage* at *index*.

        Returns ``self`` for fluent registration.
        """
        self._stages.insert(index, stage)
        return self

    def remove_stage(self, name: str) -> bool:
        """Remove the first stage whose ``.name`` matches *name*.

        Returns ``True`` if a stage was removed.
        """
        for i, s in enumerate(self._stages):
            if s.name == name:
                del self._stages[i]
                return True
        return False

    # ── Execution ───────────────────────────────────────────────────────────

    async def execute(self, context: PipelineContext | None = None) -> PipelineContext:
        """Run every registered stage in order against *context*.

        Args:
            context: An optional pre-populated context.  If ``None``, a minimal
                     context is created with a generated ``request_id`` and
                     ``transport="unknown"``.

        Returns:
            The final ``PipelineContext`` after all stages have run (or after
            a short-circuit / failure).
        """
        if context is None:
            context = PipelineContext(
                request_id=uuid.uuid4().hex,
                transport="unknown",
            )

        for stage in self._stages:
            stage_name = stage.name
            context.span_stack.append(stage_name)

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
                    logger.error("Stage '%s' timed out after %ss", stage_name, timeout)
                    if retry_count < max_retries:
                        retry_count += 1
                        logger.warning(
                            "Retrying stage '%s' after timeout (%d/%d)",
                            stage_name, retry_count, max_retries,
                        )
                        continue
                    context.execution_state = "failed"
                    context.error = f"stage '{stage_name}' timed out after {retry_count + 1} attempts"
                    context.span_stack.pop()
                    break
                except Exception as exc:
                    logger.exception("Stage '%s' raised unexpected exception", stage_name)
                    if retry_count < max_retries:
                        retry_count += 1
                        logger.warning(
                            "Retrying stage '%s' after exception (%d/%d)",
                            stage_name, retry_count, max_retries,
                        )
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
                    logger.info(
                        "Pipeline short-circuited at stage '%s' — reason: %s",
                        stage_name, result.error,
                    )
                    context.execution_state = "short_circuited"
                    context.error = result.error
                    context.span_stack.pop()
                    break

                if outcome == StageOutcome.RETRY:
                    if retry_count < max_retries:
                        retry_count += 1
                        logger.warning(
                            "Stage '%s' requested retry (%d/%d)",
                            stage_name, retry_count, max_retries,
                        )
                        continue
                    logger.error(
                        "Stage '%s' exhausted retries (%d) — failing",
                        stage_name, max_retries,
                    )
                    context.execution_state = "failed"
                    context.error = f"stage '{stage_name}' exhausted retries: {result.error}" if result.error else f"stage '{stage_name}' exhausted retries"
                    context.span_stack.pop()
                    break

                if outcome == StageOutcome.FAIL:
                    logger.error(
                        "Pipeline failed at stage '%s' — %s",
                        stage_name, result.error,
                    )
                    context.execution_state = "failed"
                    context.error = result.error
                    context.span_stack.pop()
                    break

                if outcome == StageOutcome.DEFER:
                    logger.info(
                        "Pipeline deferred at stage '%s' — %s",
                        stage_name, result.error,
                    )
                    context.execution_state = "deferred"
                    context.error = result.error
                    context.span_stack.pop()
                    break

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
