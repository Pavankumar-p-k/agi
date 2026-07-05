from core.pipeline.stages.auth import AuthenticationStage
from core.pipeline.stages.capability_selection import CapabilitySelectionStage
from core.pipeline.stages.epistemic import EpistemicTaggingStage
from core.pipeline.stages.execution import ExecutionStage
from core.pipeline.stages.formatter import FormatterStage
from core.pipeline.stages.intent import IntentStage
from core.pipeline.stages.load_context import LoadContextStage
from core.pipeline.stages.memory import MemoryStage
from core.pipeline.stages.metrics import MetricsStage
from core.pipeline.stages.planner import PlannerStage
from core.pipeline.stages.rate_limit import RateLimitStage
from core.pipeline.stages.receive import ReceiveStage
from core.pipeline.stages.verification import VerificationStage

__all__ = [
    "AuthenticationStage",
    "CapabilitySelectionStage",
    "EpistemicTaggingStage",
    "ExecutionStage",
    "FormatterStage",
    "IntentStage",
    "LoadContextStage",
    "MemoryStage",
    "MetricsStage",
    "PlannerStage",
    "RateLimitStage",
    "ReceiveStage",
    "VerificationStage",
]

# ── Default pipeline (ADR-006 order) ────────────────────────────────────────
DEFAULT_STAGES = [
    ("receive", ReceiveStage),
    ("load_context", LoadContextStage),
    ("authentication", AuthenticationStage),
    ("rate_limit", RateLimitStage),
    ("intent", IntentStage),
    ("capability_selection", CapabilitySelectionStage),
    ("planner", PlannerStage),
    ("execution", lambda: ExecutionStage().with_default_providers()),
    ("verification", VerificationStage),
    ("epistemic", EpistemicTaggingStage),
    ("memory", MemoryStage),
    ("metrics", MetricsStage),
    ("formatter", FormatterStage),
]
