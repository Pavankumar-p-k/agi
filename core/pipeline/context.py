from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from core.identity.models import IdentityContext
from core.identity.resource_scope import ResourceScope
from core.pipeline.architecture_metrics import ArchitectureMetrics
from core.pipeline.authentication_result import AuthenticationResult
from core.pipeline.authorization_result import AuthorizationResult
from core.pipeline.knowledge_result import KnowledgeResult
from core.pipeline.learning_result import LearningRecord
from core.pipeline.planner_result import PlannerResult
from core.pipeline.reflection_result import ReflectionResult
from core.pipeline.resource_access_result import ResourceAccessResult
from core.pipeline.resource_grant import ResourceGrant
from core.pipeline.reasoning_result import ReasoningResult
from core.pipeline.security_context import SecurityContext
from core.identity.tenant_resolver import TenantResolutionResult
from core.pipeline.deterministic import DeterministicServices
from core.pipeline.outcome import Outcome
from core.pipeline.policy_optimization_result import PolicyOptimizationResult
from core.pipeline.explanation_result import ExplanationResult

logger = logging.getLogger(__name__)


@dataclass
class PipelineContext:
    """The single mutable context object flowing through the pipeline.

    Every stage reads from and writes to this context.  No stage interacts
    with external systems without going through the context first.

    **Field ownership** (see ``STAGE_OWNERSHIP`` in ``base.py``): each
    context field is owned by exactly one stage.  Non-owner stages may
    *read* a field but must call ``set_stage_field()`` to *write* it;
    violations produce a runtime warning.
    """

    # ── Identity / Routing ──────────────────────────────────────────────────
    request_id: str
    """Unique identifier for this request."""

    transport: str
    """Name of the transport that originated this request
    (e.g. ``"rest"``, ``"websocket"``, ``"telegram"``, ``"cli"``)."""

    user_id: str | None = None
    session_id: str | None = None
    identity: IdentityContext | None = None
    authentication_result: AuthenticationResult | None = None
    authorization_result: AuthorizationResult | None = None
    resource_grant: ResourceGrant | None = None
    resource_scope: ResourceScope | None = None
    resource_access_result: ResourceAccessResult | None = None
    tenant_resolution_result: TenantResolutionResult | None = None

    # ── Pipeline metadata ───────────────────────────────────────────────────
    pipeline_version: str = "1.0"
    """Version of the pipeline architecture that processed this request."""

    # ── Raw / Parsed Request ────────────────────────────────────────────────
    raw_input: str = ""
    """Original text from the transport."""

    attachments: list[dict[str, Any]] = field(default_factory=list)
    """File attachments included with the request."""

    messages: list[dict[str, Any]] = field(default_factory=list)
    """Chat history (e.g. ``[{"role": "user", "content": …}]``)."""

    parsed_request: dict[str, Any] | None = None
    """Transport-agnostic structured representation of the request,
    set by the Receive stage."""

    # ── Classification / Planning ───────────────────────────────────────────
    classification: dict[str, Any] | None = None
    """Output of Intent Classification — mode, confidence, sub_type, etc."""

    retrieved_context: dict[str, Any] | None = None
    """Context retrieved from memory by ContextRetrieval stage.
    Contains ``memories`` (list of memory dicts) and optionally
    ``formatted_context`` (LLM-readable string)."""

    knowledge_result: KnowledgeResult | None = None
    """Canonical output of the Knowledge stage (Phase 7, Sprint 2).
    Entity graph built from retrieved context.  Frozen dataclass with
    entities, facts, edges, node/edge counts."""

    reasoning_assessment: dict[str, Any] | None = None
    """Output of the Reasoner stage — complexity, requirements,
    constraints, confidence, estimated_steps, routing_hints.

    .. deprecated::
       Use ``reasoning_result`` for new code.
       Removal target: Sprint 3 (multi-strategy planner migration)."""

    reasoning_result: ReasoningResult | None = None
    """Canonical output of the Reasoning stage (Phase 7).
    Replaces ``reasoning_assessment``.  Frozen dataclass with
    beliefs, evidence, contradictions, counter-hypotheses, confidence."""

    planner_result: PlannerResult | None = None
    """Canonical output of the multi-strategy Planner stage (Phase 7, Sprint 3).
    Contains ranked strategy candidates, comparisons, and the selected plan.
    ``context.plan`` is still populated from the winning strategy for backward
    compat."""

    reflection_result: ReflectionResult | None = None
    """Canonical output of the Reflection stage (Phase 7, Sprint 4).
    Post-execution analysis with lessons, patterns, success rating."""

    learning_records: tuple[LearningRecord, ...] = ()
    """Canonical output of the Learning stage (Phase 7, Sprint 5).
    Structured learning records consumed by the Memory stage."""

    policy_optimization_result: PolicyOptimizationResult | None = None
    """Canonical output of the Policy Optimization stage (Phase 7, Sprint 6).
    Policy adjustment signals derived from learning records."""

    policy_profile: str = "developer"
    """Active ``PolicyProfile`` for this request (``"strict"``,
    ``"developer"``, ``"autonomous"``).  Set by PolicyOptimizationStage
    or loaded from storage on pipeline start."""

    plan: dict[str, Any] | None = None
    """Logical plan produced by the Planner stage.
    Structure: ``{"goal": str, "steps": [{"intent": str, "objective": str,
    "constraints": dict}, ...]}``"""

    plan_validated: bool = True
    """Set by PlanValidator. ``True`` if plan structure is valid."""

    selected_capabilities: dict[int, list[Any]] = field(default_factory=dict)
    """Capabilities matched to each plan step.
    Maps step index to a list of capability descriptors."""

    # ── Execution ───────────────────────────────────────────────────────────
    execution_state: str = "pending"
    """One of ``"pending"``, ``"running"``, ``"completed"``, ``"failed"``,
    ``"short_circuited"``, ``"deferred"``, ``"cancelled"``."""

    error: str | None = None
    """Error message if the pipeline failed or was short-circuited."""

    execution_result: Any = None
    """Raw output from the Execution stage (before verification / formatting).
    Kept for backward compatibility; prefer ``outcome`` for new code."""

    outcome: Outcome | None = None
    """Structured Outcome from Execution.  Replaces ``execution_result``."""

    # ── Verification ────────────────────────────────────────────────────────
    verification_result: dict[str, Any] | None = None
    """Output of the Verification stage (safety, quality, schema checks)."""

    # ── Epistemic Tagging ───────────────────────────────────────────────────
    epistemic_tags: dict[str, float] = field(default_factory=dict)
    """Confidence, provenance, source attribution (set by EpistemicTagging)."""

    # ── Memory ──────────────────────────────────────────────────────────────
    memory_refs: list[str] = field(default_factory=list)
    """References stored in the memory facade during the Memory stage."""

    store_decision: dict[str, Any] | None = None
    """Decision from the Memory stage: action (store/skip), type, reason."""

    # ── Activity / Tracing ──────────────────────────────────────────────────
    activity_id: str | None = None
    """ActivityGraph node id for this request (set on pipeline start)."""

    trace_id: str = ""
    """Distributed tracing identifier."""

    span_stack: list[str] = field(default_factory=list)
    """Nested span names for observability within this request."""

    # ── Cancellation ────────────────────────────────────────────────────────
    cancelled: bool = False
    """Set to ``True`` when the pipeline is cancelled externally.
    Stages should check this flag between long-running operations."""

    # ── Response ────────────────────────────────────────────────────────────
    formatted_response: dict[str, Any] | None = None
    """Final response payload (set by the Formatter stage, last in pipeline).
    The transport adapter reads this and sends it to the client."""

    # ── Deterministic Services ───────────────────────────────────────────────
    services: DeterministicServices = field(default_factory=DeterministicServices.real)
    """Injectables that freeze nondeterminism (time, UUIDs, RNG).
    Defaults to ``RealServices`` in production.  Tests inject ``FakeServices``."""

    # ── Architecture Metrics ────────────────────────────────────────────────
    architecture_metrics: ArchitectureMetrics = field(default_factory=ArchitectureMetrics)
    """Per-request structural measurements (plan_steps, observations, …).
    Populated automatically after pipeline execution."""

    # ── Explainability ─────────────────────────────────────────────────────
    explanation: ExplanationResult | None = None
    """Canonical output of the Explainability stage (Phase 7, Sprint 7).
    Structured explanation of the decision chain, consumed by the
    Formatter stage."""

    # ── Metrics / Metadata ──────────────────────────────────────────────────
    metrics: dict[str, Any] = field(default_factory=dict)
    """Aggregated metrics for this request (timing, tokens, retries)."""

    metadata: dict[str, Any] = field(default_factory=dict)
    """Extensible bag for arbitrary metadata that stages may need to share."""

    # ── Field ownership (internal) ──────────────────────────────────────────
    _owned_fields_set: set[str] = field(default_factory=set, repr=False)
    """Tracks which owned fields have been set during this request."""

    @property
    def security(self) -> SecurityContext:
        """Read-only aggregate of all security artifacts.

        Built lazily from the individual context fields.  Downstream stages
        should prefer this over accessing the individual fields directly.
        """
        return SecurityContext(
            identity=self.identity,
            authentication=self.authentication_result,
            authorization=self.authorization_result,
            resource_grant=self.resource_grant,
            resource_scope=self.resource_scope,
            resource_access=self.resource_access_result,
            tenant_resolution=self.tenant_resolution_result,
        )

    def set_stage_field(self, stage_name: str, field_name: str, value: Any) -> None:
        """Set a context field on behalf of *stage_name*.

        If *field_name* is listed in ``STAGE_OWNERSHIP`` for a different
        stage, a runtime warning is logged.  Call this instead of setting
        attributes directly when writing to an owned field.
        """
        from core.pipeline.base import STAGE_OWNERSHIP

        expected_owner = _field_owner(field_name)
        if expected_owner and expected_owner != stage_name:
            logger.warning(
                "Stage '%s' wrote to '%s', which is owned by '%s'",
                stage_name, field_name, expected_owner,
            )
        object.__setattr__(self, field_name, value)
        self._owned_fields_set.add(field_name)


def _field_owner(field_name: str) -> str | None:
    """Return the stage that owns *field_name*, or ``None`` if unowned."""
    from core.pipeline.base import STAGE_OWNERSHIP

    for stage, fields in STAGE_OWNERSHIP.items():
        if field_name in fields:
            return stage
    return None
