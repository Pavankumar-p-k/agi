"""Pipeline orchestration primitives."""
from __future__ import annotations

from typing import Any

from core.pipeline.base import StageOutcome, StageResult
from core.pipeline.context import PipelineContext
from core.pipeline.stream import StreamEvent


class Pipeline:
    _instance: "Pipeline | None" = None

    def __init__(self, stages: list[Any] | None = None, context: PipelineContext | None = None):
        self.stages: list[Any] = list(stages or [])
        self.context = context or PipelineContext()

    def add_stage(self, stage: Any) -> Any:
        self.stages.append(stage)
        return stage

    def cancel(self) -> None:
        self._cancelled = True

    async def stream(self, context: PipelineContext | Any | None = None):
        if context is None:
            context = self.context
        if not isinstance(context, PipelineContext):
            context = PipelineContext(raw_input=context)
        context.pipeline_version = "1.0"
        yield StreamEvent("pipeline_start", data={"_context": context})
        if getattr(self, "_cancelled", False):
            yield StreamEvent("pipeline_cancelled", data={"_context": context})
            self._cancelled = False
            return
        for stage in self.stages:
            name = getattr(stage, "name", stage.__class__.__name__)
            yield StreamEvent("stage_start", stage=name, data={"_context": context})
            try:
                result = await stage.execute(context)
            except Exception as exc:
                yield StreamEvent("stage_error", stage=name, error=str(exc), data={"_context": context})
                yield StreamEvent("pipeline_error", error=str(exc), data={"_context": context})
                return
            if result is not None:
                context = result.context or context
                if result.outcome in {StageOutcome.FAIL, StageOutcome.FAILURE, StageOutcome.ERROR, StageOutcome.STOP}:
                    error = str(result.error or result.outcome.value)
                    yield StreamEvent("stage_error", stage=name, error=error, data={"_context": context})
                    yield StreamEvent("pipeline_error", error=error, data={"_context": context})
                    return
            yield StreamEvent("stage_end", stage=name, data={"_context": context})
            if getattr(self, "_cancelled", False):
                yield StreamEvent("pipeline_cancelled", data={"_context": context})
                self._cancelled = False
                return
        yield StreamEvent("pipeline_end", data={"_context": context, "execution_state": "pending", "metadata": {"pipeline_version": "1.0", "activity_id": context.request_id, "trace_id": context.request_id}})

    async def execute(self, context: PipelineContext | Any | None = None) -> StageResult:
        if context is None:
            context = self.context
        if not isinstance(context, PipelineContext):
            context = PipelineContext(raw_input=context)
        result = StageResult(outcome=StageOutcome.CONTINUE, context=context, identity=context.identity)
        for stage in self.stages:
            stage_result = await stage.execute(context)
            if stage_result is not None:
                result = stage_result
                context = result.context or context
                if result.identity is not None:
                    context.identity = result.identity
                if result.authentication_result is not None:
                    context.authentication_result = result.authentication_result
                if result.authorization_result is not None:
                    context.authorization_result = result.authorization_result
                if result.outcome in {StageOutcome.STOP, StageOutcome.ERROR, StageOutcome.FAILURE}:
                    break
        result.context = context
        if result.identity is None:
            result.identity = context.identity
        if result.authentication_result is None:
            result.authentication_result = getattr(context, "authentication_result", None)
        if result.authorization_result is None:
            result.authorization_result = getattr(context, "authorization_result", None)
        return result


def get_pipeline(*args: Any, **kwargs: Any) -> Pipeline:
    if Pipeline._instance is None:
        Pipeline._instance = Pipeline()
    return Pipeline._instance


async def async_get_pipeline(*args: Any, **kwargs: Any) -> Pipeline:
    return get_pipeline(*args, **kwargs)


async def process_message(request: Any, context: PipelineContext | None = None, **kwargs: Any) -> Any:
    pipeline = kwargs.pop("pipeline", None) or get_pipeline()
    if context is None:
        req = request
        context = PipelineContext(
            request_id=getattr(req, "request_id", ""),
            transport=getattr(req, "transport", ""),
            raw_input=getattr(req, "text", getattr(req, "raw_input", None)),
            metadata=dict(getattr(req, "metadata", {}) or {}),
        )
        context.identity = getattr(req, "identity", None) or context.identity
        if getattr(req, "user_id", None):
            from core.identity.models import UserIdentity
            context.identity = context.identity or __import__("core.identity.models", fromlist=["IdentityContext"]).IdentityContext()
            context.identity.user = UserIdentity(id=req.user_id)
    return await pipeline.execute(context)


async def async_process_message(*args: Any, **kwargs: Any) -> Any:
    return await process_message(*args, **kwargs)


def set_pipeline(pipeline: Pipeline) -> Pipeline:
    Pipeline._instance = pipeline
    return pipeline


async def async_set_pipeline(*args: Any, **kwargs: Any) -> Pipeline:
    return set_pipeline(*args, **kwargs)
