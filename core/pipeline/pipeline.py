from __future__ import annotations

import logging
import uuid

from core.pipeline.base import PipelineStage, StageOutcome
from core.pipeline.context import PipelineContext

logger = logging.getLogger(__name__)


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

            result = await stage.execute(context)

            # Merge any metrics the stage emitted
            if result.metrics:
                context.metrics[stage_name] = result.metrics

            outcome = result.outcome

            if outcome == StageOutcome.CONTINUE:
                context = result.context
                context.span_stack.pop()
                continue

            if outcome == StageOutcome.SHORT_CIRCUIT:
                logger.info(
                    "Pipeline short-circuited at stage '%s' — reason: %s",
                    stage_name, result.error,
                )
                context = result.context
                context.execution_state = "short_circuited"
                context.span_stack.pop()
                break

            if outcome == StageOutcome.RETRY:
                logger.warning(
                    "Stage '%s' requested retry (%d/%d)",
                    stage_name, result.retry_count, 3,
                )

            if outcome == StageOutcome.FAIL:
                logger.error(
                    "Pipeline failed at stage '%s' — %s",
                    stage_name, result.error,
                )
                context = result.context
                context.execution_state = "failed"
                context.span_stack.pop()
                break

            if outcome == StageOutcome.DEFER:
                logger.info(
                    "Pipeline deferred at stage '%s' — %s",
                    stage_name, result.error,
                )
                context = result.context
                context.execution_state = "deferred"
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
    ) -> PipelineContext:
        """Convenience wrapper: build a context and execute.

        This is the signature that transport adapters call.
        """
        context = PipelineContext(
            request_id=uuid.uuid4().hex,
            transport=transport,
            user_id=user_id,
            session_id=session_id,
            raw_input=raw_input,
        )
        return await self.execute(context)
