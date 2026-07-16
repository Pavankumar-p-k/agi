from core.pipeline.stages.auth import AuthenticationStage
from core.pipeline.stages.authorization import AuthorizationStage
from core.pipeline.stages.capability_selection import CapabilitySelectionStage
from core.pipeline.stages.context_retrieval import ContextRetrievalStage
from core.pipeline.stages.epistemic import EpistemicTaggingStage
from core.pipeline.stages.execution import ExecutionStage
from core.pipeline.stages.explainability import ExplainabilityStage
from core.pipeline.stages.formatter import FormatterStage
from core.pipeline.stages.intent import IntentStage
from core.pipeline.stages.knowledge import KnowledgeStage
from core.pipeline.stages.learning import LearningStage
from core.pipeline.stages.load_context import LoadContextStage
from core.pipeline.stages.memory import MemoryStage
from core.pipeline.stages.metrics import MetricsStage
from core.pipeline.stages.notification import NotificationStage
from core.pipeline.stages.plan_validator import PlanValidatorStage
from core.pipeline.stages.planner import PlannerStage
from core.pipeline.stages.policy_optimization import PolicyOptimizationStage
from core.pipeline.stages.rate_limit import RateLimitStage
from core.pipeline.stages.reasoner import ReasonerStage  # legacy, use ReasoningStage for new code
from core.pipeline.stages.reasoning import ReasoningStage
from core.pipeline.stages.reflection import ReflectionStage
from core.pipeline.stages.receive import ReceiveStage
from core.pipeline.stages.resource_access import ResourceAccessStage
from core.pipeline.stages.tenant_resolution import TenantResolutionStage
from core.pipeline.stages.verification import VerificationStage

__all__ = [
    "AuthenticationStage",
    "AuthorizationStage",
    "ResourceAccessStage",
    "TenantResolutionStage",
    "CapabilitySelectionStage",
    "ContextRetrievalStage",
    "EpistemicTaggingStage",
    "ExecutionStage",
    "ExplainabilityStage",
    "FormatterStage",
    "IntentStage",
    "KnowledgeStage",
    "LearningStage",
    "LoadContextStage",
    "MemoryStage",
    "MetricsStage",
    "NotificationStage",
    "PlanValidatorStage",
    "PlannerStage",
    "PolicyOptimizationStage",
    "RateLimitStage",
    "ReasonerStage",   # legacy
    "ReasoningStage",
    "ReflectionStage",
    "ReceiveStage",
    "VerificationStage",
]

# ── Default pipeline (ADR-007 order) ────────────────────────────────────────
DEFAULT_STAGES = [
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
    ("reasoning", ReasoningStage),
    ("planner", PlannerStage),
    ("plan_validator", PlanValidatorStage),
    ("capability_selection", CapabilitySelectionStage),
    ("execution", lambda: ExecutionStage().with_default_providers()),
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
]
