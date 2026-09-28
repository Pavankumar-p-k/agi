"""Canonical 26-stage set (ADR-007/009).

Early/mechanical stages are defined here. Stages that own dedicated
abstractions live in their own modules (audit Rules 1/6/7/50/51/52) and
are re-exported below so ``core.pipeline.stages`` remains the single
import surface.
"""
from __future__ import annotations

from core.pipeline.base import PipelineStage, StageOutcome, StageResult
from core.pipeline.pipeline import PipelineContext


def _ok(ctx: PipelineContext) -> StageResult:
    return StageResult(outcome=StageOutcome.CONTINUE, context=ctx)


class ReceiveStage(PipelineStage):
    @property
    def name(self) -> str:
        return "receive"

    async def execute(self, context: PipelineContext) -> StageResult:
        parsed = {"text": context.raw_input}
        if context.attachments:
            parsed["attachment_count"] = len(context.attachments)
        context.parsed_request = parsed
        return _ok(context)


class LoadContextStage(PipelineStage):
    @property
    def name(self) -> str:
        return "load_context"

    async def execute(self, context: PipelineContext) -> StageResult:
        context.metadata.setdefault("transport", context.transport)
        from core.identity.resource_scope import default_scope
        if context.resource_scope is None:
            context.resource_scope = default_scope()
        return _ok(context)


class TenantResolutionStage(PipelineStage):
    @property
    def name(self) -> str:
        return "tenant_resolution"

    async def execute(self, context: PipelineContext) -> StageResult:
        from core.identity.tenant_resolver import DefaultTenantResolver
        result = DefaultTenantResolver().resolve(context)
        context.tenant_id = result.tenant_id
        context.tenant_resolution_result = result
        return _ok(context)


class RateLimitStage(PipelineStage):
    @property
    def name(self) -> str:
        return "rate_limit"

    async def execute(self, context: PipelineContext) -> StageResult:
        class _RL:
            allowed = True
            remaining = 100
            limit = 100
        context.rate_limit_result = _RL()
        return _ok(context)


class IntentStage(PipelineStage):
    @property
    def name(self) -> str:
        return "intent"

    async def execute(self, context: PipelineContext) -> StageResult:
        raw = (context.raw_input or "").strip().lower()
        if any(k in raw for k in ("build", "write", "create", "fix", "code")):
            mode = "code"
        elif any(k in raw for k in ("search", "find", "research", "look up")):
            mode = "research"
        else:
            mode = "chat"
        context.classification = {
            "mode": mode, "confidence": 0.8, "sub_type": "",
        }
        return _ok(context)


class ContextRetrievalStage(PipelineStage):
    @property
    def name(self) -> str:
        return "context_retrieval"

    async def execute(self, context: PipelineContext) -> StageResult:
        context.retrieved_context = {
            "items": [], "transport": context.transport,
            "request_id": context.request_id,
        }
        return _ok(context)


class ActivityStage(PipelineStage):
    @property
    def name(self) -> str:
        return "activity"

    async def execute(self, context: PipelineContext) -> StageResult:
        context.activity_id = context.request_id
        context.trace_id = context.trace_id or context.request_id
        return _ok(context)


class EpistemicTaggingStage(PipelineStage):
    @property
    def name(self) -> str:
        return "epistemic"

    async def execute(self, context: PipelineContext) -> StageResult:
        rr = getattr(context, "reasoning_result", None)
        confidence = float(getattr(rr, "confidence", 0.7) or 0.7) if rr else 0.7
        context.epistemic_tags = {
            "confidence": confidence,
            "complexity": getattr(rr, "complexity", "simple") if rr else "simple",
        }
        return _ok(context)


class NotificationStage(PipelineStage):
    @property
    def name(self) -> str:
        return "notification"

    async def execute(self, context: PipelineContext) -> StageResult:
        context.notification_result = {"sent": False}
        return _ok(context)


class FormatterStage(PipelineStage):
    @property
    def name(self) -> str:
        return "formatter"

    async def execute(self, context: PipelineContext) -> StageResult:
        if context.error:
            text = f"Error: {context.error}"
        else:
            exec_result = context.execution_result or {}
            text = str(exec_result.get("text", context.raw_input)) \
                if isinstance(exec_result, dict) else context.raw_input
        context.formatted_response = {
            "text": text,
            "epistemic": dict(context.epistemic_tags or {}),
        }
        return _ok(context)


# ── Stages with dedicated module homes (re-exports) ────────────────────────
from core.pipeline.stages.auth import AuthenticationStage  # noqa: E402
from core.pipeline.stages.authorization import AuthorizationStage  # noqa: E402
from core.pipeline.stages.resource_access import ResourceAccessStage  # noqa: E402
from core.pipeline.stages.execution import (  # noqa: E402
    ExecutionStage,
    LiteLLMProvider,
    MockProvider,
    OllamaFallbackProvider,
    Provider,
    ProviderResult,
)
from core.pipeline.stages.verification import VerificationStage  # noqa: E402
from core.pipeline.stages.knowledge import KnowledgeStage  # noqa: E402
from core.pipeline.stages.reasoner import ReasonerStage  # noqa: E402
from core.pipeline.stages.planner import PlannerStage  # noqa: E402
from core.pipeline.stages.plan_validator import PlanValidatorStage  # noqa: E402
from core.pipeline.stages.capability_selection import CapabilitySelectionStage  # noqa: E402
from core.pipeline.stages.reflection import ReflectionStage  # noqa: E402
from core.pipeline.stages.learning import LearningStage  # noqa: E402
from core.pipeline.stages.policy_optimization import PolicyOptimizationStage  # noqa: E402
from core.pipeline.stages.memory import MemoryStage  # noqa: E402
from core.pipeline.stages.metrics import MetricsStage  # noqa: E402
from core.pipeline.stages.explainability import ExplainabilityStage  # noqa: E402

# ReasonerStage alias (ReasoningStage is the same abstraction — Rule 6).
ReasoningStage = ReasonerStage

DEFAULT_STAGES = (
    ("receive", ReceiveStage),
    ("load_context", LoadContextStage),
    ("authentication", AuthenticationStage),
    ("tenant_resolution", TenantResolutionStage),
    ("authorization", AuthorizationStage),
    ("resource_access", ResourceAccessStage),
    ("rate_limit", RateLimitStage),
    ("intent", IntentStage),
    ("context_retrieval", ContextRetrievalStage),
    ("knowledge", KnowledgeStage),
    ("reasoning", ReasonerStage),
    ("planner", PlannerStage),
    ("plan_validator", PlanValidatorStage),
    ("activity", ActivityStage),
    ("capability_selection", CapabilitySelectionStage),
    ("execution", ExecutionStage),
    ("verification", VerificationStage),
    ("epistemic", EpistemicTaggingStage),
    ("reflection", ReflectionStage),
    ("learning", LearningStage),
    ("policy_optimization", PolicyOptimizationStage),
    ("memory", MemoryStage),
    ("notification", NotificationStage),
    ("metrics", MetricsStage),
    ("explainability", ExplainabilityStage),
    ("formatter", FormatterStage),
)
