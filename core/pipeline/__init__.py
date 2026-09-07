"""Pipeline package exports."""
from __future__ import annotations

from core.pipeline.authentication_result import AuthenticationResult
from core.pipeline.authorization_result import AuthorizationResult
from core.pipeline.context import PipelineContext
from core.pipeline.stream import StreamEvent
from core.pipeline.messages import Request, Response
from core.pipeline.pipeline import Pipeline, async_get_pipeline, async_process_message, async_set_pipeline, get_pipeline, process_message, set_pipeline
from core.pipeline.base import PipelineStage, StageOutcome, StageResult, STAGE_OWNERSHIP
from dataclasses import dataclass, field
import time


@dataclass(frozen=True)
class Decision:
    activity_id: str
    stage: str
    timestamp: float
    inputs: dict
    outputs: dict
    rationale: str
    confidence: float = 0.0
    metadata: dict = field(default_factory=dict)


_STAGE_NAMES = (
    "receive", "load_context", "authentication", "tenant_resolution",
    "authorization", "resource_access", "rate_limit", "intent",
    "context_retrieval", "knowledge", "reasoning", "planner",
    "plan_validator", "activity", "capability_selection", "execution",
    "verification", "epistemic", "reflection", "learning",
    "policy_optimization", "memory", "notification", "metrics",
    "explainability", "formatter",
)
from core.pipeline import stages as _stages
DEFAULT_STAGES = tuple((name, getattr(_stages, _class_name, getattr(_stages, name.title() + "Stage", None)))
                       for name, _class_name in (
                           ("receive", "ReceiveStage"), ("load_context", "LoadContextStage"),
                           ("authentication", "AuthenticationStage"), ("tenant_resolution", "TenantResolutionStage"),
                           ("authorization", "AuthorizationStage"), ("resource_access", "ResourceAccessStage"),
                           ("rate_limit", "RateLimitStage"), ("intent", "IntentStage"),
                           ("context_retrieval", "ContextRetrievalStage"), ("knowledge", "KnowledgeStage"),
                           ("reasoning", "ReasoningStage"), ("planner", "PlannerStage"),
                           ("plan_validator", "PlanValidatorStage"), ("activity", "ActivityStage"),
                           ("capability_selection", "CapabilitySelectionStage"), ("execution", "ExecutionStage"),
                           ("verification", "VerificationStage"), ("epistemic", "EpistemicTaggingStage"),
                           ("reflection", "ReflectionStage"), ("learning", "LearningStage"),
                           ("policy_optimization", "PolicyOptimizationStage"), ("memory", "MemoryStage"),
                           ("notification", "NotificationStage"), ("metrics", "MetricsStage"),
                           ("explainability", "ExplainabilityStage"), ("formatter", "FormatterStage")))

__all__ = [
    "AuthenticationResult",
    "AuthorizationResult",
    "PipelineContext",
    "Request",
    "Response",
    "Pipeline",
    "get_pipeline",
    "set_pipeline",
    "process_message",
    "async_get_pipeline",
    "async_set_pipeline",
    "async_process_message",
    "PipelineStage",
    "StageOutcome",
    "StageResult",
    "STAGE_OWNERSHIP",
    "DEFAULT_STAGES",
    "Decision",
    "StreamEvent",
]


async def stream_pipeline(request: Request):
    context = PipelineContext(
        request_id=getattr(request, "session_id", None) or getattr(request, "request_id", ""),
        transport=getattr(request, "transport", ""),
        raw_input=getattr(request, "text", getattr(request, "raw_input", None)),
        metadata=dict(getattr(request, "metadata", {}) or {}),
    )
    async for event in get_pipeline().stream(context):
        yield event
