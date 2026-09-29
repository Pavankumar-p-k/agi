"""Canonical request-processing pipeline (ADR-006/007/009).

StageOutcome/StageResult/STAGE_OWNERSHIP are defined in core.pipeline.base
(the contract imports them from there) and re-exported here for callers
that import from core.pipeline.pipeline.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from core.pipeline.base import (  # noqa: F401 — canonical definitions
    STAGE_OWNERSHIP,
    PipelineStage,
    StageOutcome,
    StageResult,
)
from core.pipeline.context import PipelineContext  # noqa: F401 — canonical context
from core.pipeline.messages import Request, Response  # noqa: F401 — canonical messages
import dataclasses  # noqa: F401 — used by StageResult re-export consumers
class _Hooks:
    def __init__(self) -> None:
        self._before: dict[str, list] = {}
        self._after: dict[str, list] = {}

    def on_before(self, stage: str, fn) -> None:
        self._before.setdefault(stage, []).append(fn)

    def on_after(self, stage: str, fn) -> None:
        self._after.setdefault(stage, []).append(fn)

    async def run_before(self, stage: str, ctx: PipelineContext) -> None:
        for fn in self._before.get(stage, []):
            try:
                res = fn(stage, ctx)
                if asyncio.iscoroutine(res):
                    await res
            except Exception:
                pass

    async def run_after(self, stage: str, ctx: PipelineContext) -> None:
        for fn in self._after.get(stage, []):
            try:
                res = fn(stage, ctx)
                if asyncio.iscoroutine(res):
                    await res
            except Exception:
                pass


_STATE_BY_OUTCOME = {
    StageOutcome.FAIL: "failed",
    StageOutcome.SHORT_CIRCUIT: "short_circuited",
    StageOutcome.DEFER: "deferred",
    StageOutcome.CANCELLED: "cancelled",
}


class Pipeline:
    """Ordered stage runner with retry/timeout/hooks/cancel and metrics."""

    def __init__(self) -> None:
        self.stages: list[PipelineStage] = []
        self.hooks = _Hooks()
        self._cancelled = False

    # ── registration ────────────────────────────────────────────────
    def add_stage(self, stage: PipelineStage) -> "Pipeline":
        self.stages.append(stage)
        return self

    def insert_stage(self, index: int, stage: PipelineStage) -> "Pipeline":
        self.stages.insert(index, stage)
        return self

    def remove_stage(self, name: str) -> bool:
        for i, s in enumerate(self.stages):
            if s.name == name:
                del self.stages[i]
                return True
        return False

    def cancel(self) -> None:
        self._cancelled = True

    # ── streaming ───────────────────────────────────────────────────
    async def stream(self, ctx: Optional[PipelineContext] = None):
        """Yield StreamEvents while running the stages (observability path).

        Mirrors ``execute()`` stage-for-stage but reports every transition so
        a transport can push progress to the client. Terminal events are
        ``pipeline_end`` (success), ``pipeline_error`` (stage failure) and
        ``pipeline_cancelled``.
        """
        from core.pipeline.stream import StreamEvent

        if ctx is None:
            ctx = PipelineContext(request_id=uuid.uuid4().hex, transport="unknown")

        yield StreamEvent(
            event_type="pipeline_start",
            data={"request_id": ctx.request_id,
                  "pipeline_version": ctx.pipeline_version},
        )

        if self._cancelled:
            ctx.execution_state = "cancelled"
            yield StreamEvent(event_type="pipeline_cancelled",
                              data={"execution_state": "cancelled",
                                    "_context": ctx})
            return

        for stage in self.stages:
            stage_name = stage.name
            if self._cancelled:
                ctx.execution_state = "cancelled"
                yield StreamEvent(event_type="pipeline_cancelled", stage=stage_name,
                                  data={"execution_state": "cancelled",
                                        "_context": ctx})
                return

            yield StreamEvent(event_type="stage_start", stage=stage_name)
            await self.hooks.run_before(stage_name, ctx)
            try:
                result = await stage.execute(ctx)
            except Exception as exc:  # noqa: BLE001 — reported as an event
                ctx.execution_state = "failed"
                ctx.error = str(exc)
                yield StreamEvent(event_type="stage_error", stage=stage_name,
                                  error=str(exc))
                yield StreamEvent(event_type="pipeline_error", stage=stage_name,
                                  error=str(exc),
                                  data={"execution_state": "failed",
                                        "_context": ctx})
                return
            await self.hooks.run_after(stage_name, ctx)

            if getattr(result, "error", None):
                ctx.error = result.error
            outcome = getattr(result, "outcome", StageOutcome.CONTINUE)

            if outcome == StageOutcome.CONTINUE:
                yield StreamEvent(
                    event_type="stage_end",
                    stage=stage_name,
                    data={"metrics": dict(getattr(result, "metrics", None) or {}),
                          "context": ctx},
                )
                continue

            ctx.execution_state = _STATE_BY_OUTCOME.get(outcome, "failed")
            error_text = getattr(result, "error", None) or (
                f"stage '{stage_name}' ended with "
                f"{getattr(outcome, 'value', outcome)}"
            )
            yield StreamEvent(event_type="stage_error", stage=stage_name,
                              error=error_text)
            yield StreamEvent(event_type="pipeline_error", stage=stage_name,
                              error=error_text,
                              data={"execution_state": ctx.execution_state,
                                    "_context": ctx})
            return

        self._finalize(ctx)
        yield StreamEvent(
            event_type="pipeline_end",
            data={"execution_state": ctx.execution_state,
                  "metadata": response_metadata(ctx),
                  "_context": ctx},
        )

    # ── execution ───────────────────────────────────────────────────
    async def execute(self, ctx: Optional[PipelineContext] = None) -> PipelineContext:
        if ctx is None:
            ctx = PipelineContext(request_id=uuid.uuid4().hex, transport="unknown")
        if self._cancelled:
            ctx.execution_state = "cancelled"
            return ctx

        for stage in self.stages:
            if self._cancelled:
                ctx.execution_state = "cancelled"
                return ctx

            stage_name = stage.name
            await self.hooks.run_before(stage_name, ctx)

            attempts = 0
            max_attempts = max(1, int(getattr(stage, "max_retries", 1) or 0) + 1)
            while attempts < max_attempts:
                attempts += 1
                started = time.monotonic()
                try:
                    timeout = getattr(stage, "timeout", None)
                    if timeout:
                        result = await asyncio.wait_for(stage.execute(ctx), timeout=timeout)
                    else:
                        result = await stage.execute(ctx)
                except asyncio.TimeoutError:
                    if attempts < max_attempts:
                        continue
                    ctx.execution_state = "failed"
                    ctx.error = f"stage '{stage_name}' timed out"
                    return ctx
                except Exception as exc:  # noqa: BLE001
                    if attempts < max_attempts:
                        continue
                    ctx.execution_state = "failed"
                    ctx.error = str(exc)
                    return ctx

                elapsed_ms = int((time.monotonic() - started) * 1000)
                ctx.metrics.setdefault("_stage", {})[stage_name] = {"elapsed_ms": elapsed_ms}

                outcome = result.outcome
                if result.metrics:
                    ctx.metrics[stage_name] = dict(result.metrics)
                if result.error:
                    ctx.error = result.error

                if outcome == StageOutcome.CONTINUE:
                    break
                if outcome == StageOutcome.RETRY:
                    if attempts < max_attempts:
                        continue
                    ctx.execution_state = "failed"
                    ctx.error = (f"stage '{stage_name}' exhausted retries: "
                                 f"{result.error or 'unspecified'}")
                    return ctx
                if outcome in _STATE_BY_OUTCOME:
                    ctx.execution_state = _STATE_BY_OUTCOME[outcome]
                    return ctx
                break

            await self.hooks.run_after(stage_name, ctx)

        self._finalize(ctx)
        return ctx

    # ── finalization ────────────────────────────────────────────────
    @staticmethod
    def _finalize(ctx: "PipelineContext") -> None:
        """Build the runtime Outcome artifact + architecture metrics."""
        # Promote to completed only when a stage actually produced output —
        # bare pass-through pipelines stay "pending".
        if ctx.execution_state == "pending" and (
            ctx.execution_result is not None
            or ctx.verification_result is not None
            or ctx.formatted_response is not None
        ):
            ctx.execution_state = "completed"
        if not ctx.activity_id:
            ctx.activity_id = ctx.request_id or uuid.uuid4().hex
        try:
            from core.pipeline.architecture_metrics import ArchitectureMetrics
            from core.pipeline.outcome import Outcome
            # Observation creation belongs to the Execution stage (Rule 10).
            from core.pipeline.stages.execution import terminal_observations

            aid = ctx.activity_id
            scope = getattr(ctx, "resource_scope", None)
            observations = terminal_observations(ctx)

            # Set the outcome first — metrics derivation must never prevent
            # the runtime artifact from being recorded.
            if ctx.outcome is None:
                ctx.outcome = Outcome(
                    activity_id=aid,
                    success=ctx.execution_state == "completed",
                    observations=observations,
                    status=ctx.execution_state,
                    resource_scope=scope,
                    metrics=dict(ctx.metrics),
                )

            if ctx.architecture_metrics is None:
                try:
                    ctx.architecture_metrics = ArchitectureMetrics.from_context(ctx)
                except Exception:  # noqa: BLE001
                    pass
        except Exception:  # noqa: BLE001 — finalization must never fail the run
            pass

    # ── convenience ─────────────────────────────────────────────────
    async def process_message(self, text: str, transport: str,
                              user_id: Optional[str] = None,
                              session_id: Optional[str] = None,
                              attachments: Optional[list] = None) -> PipelineContext:
        ctx = PipelineContext(
            request_id=uuid.uuid4().hex,
            transport=transport,
            user_id=user_id,
            session_id=session_id,
            raw_input=text,
            attachments=attachments,
        )
        return await self.execute(ctx)


# ── module-level singleton ───────────────────────────────────────────
_default_pipeline: Optional[Pipeline] = None


def get_pipeline() -> Pipeline:
    global _default_pipeline
    if _default_pipeline is None:
        from core.pipeline.stages import DEFAULT_STAGES
        p = Pipeline()
        for _name, cls in DEFAULT_STAGES:
            p.add_stage(cls())
        _default_pipeline = p
    return _default_pipeline


def set_pipeline(pipeline: Pipeline) -> None:
    global _default_pipeline
    _default_pipeline = pipeline


def build_context(request: Request) -> PipelineContext:
    """Materialize a PipelineContext from a Request.

    Resource scope is assigned here and nowhere else (Rule 19): the tenant
    resolves later, but ownership is known from the request.
    """
    ctx = PipelineContext(
        request_id=uuid.uuid4().hex,
        transport=request.transport,
        user_id=request.user_id,
        session_id=request.session_id,
        raw_input=request.text,
        attachments=request.attachments,
        metadata=dict(request.metadata or {}),
    )
    from core.identity.resource_scope import default_scope
    ctx.resource_scope = default_scope(
        owner_id=request.user_id or None,
        user_id=request.user_id or None,
    )
    # Identity propagation: explicit identity wins; else resolve from the
    # raw user/session claims so downstream stages see the principal.
    if request.identity is not None:
        ctx.identity = request.identity
    elif ctx.user_id or ctx.session_id:
        from core.identity.service import get_identity_service
        svc = get_identity_service()
        ctx.identity = svc.create_context(
            user_id=ctx.user_id,
            session_id=ctx.session_id,
            agent_type=request.transport or "test",
        )
    return ctx


def response_metadata(ctx: PipelineContext) -> dict:
    """Trace identifiers every response/stream-terminal event carries."""
    return {
        "activity_id": ctx.activity_id or ctx.request_id,
        "trace_id": ctx.trace_id or ctx.request_id,
        "pipeline_version": ctx.pipeline_version,
    }


async def process_message(request: Request) -> Response:
    """Full request → Response convenience over the default pipeline."""
    ctx = build_context(request)
    pipeline = get_pipeline()
    result = await pipeline.execute(ctx)

    metadata = response_metadata(result)

    if result.formatted_response:
        return Response(
            text=str(result.formatted_response.get("text", "")),
            error=result.error,
            data=result.formatted_response,
            metadata=metadata,
        )
    if result.execution_state in ("failed", "cancelled"):
        return Response(text="", error=result.error or result.execution_state,
                        metadata=metadata)
    return Response(text=result.raw_input or "", error=result.error, metadata=metadata)
