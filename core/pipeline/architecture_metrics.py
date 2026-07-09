from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from core.runtime_version import RUNTIME_VERSION

if TYPE_CHECKING:
    from core.pipeline.context import PipelineContext


@dataclass
class ArchitectureMetrics:
    """Per-request architecture metrics, populated after pipeline execution.

    These are structural measurements of the request's path through the
    architecture — not performance timings.  A separate ``MetricsCollector``
    (not part of this dataclass) aggregates across requests.

    Every snapshot carries ``tenant_id`` and ``workspace_id`` so that
    replay and analysis are tenant-local rather than global.
    """

    reasoning_complexity: str = "unknown"
    """Output of the Reasoner stage (e.g. ``"simple"``, ``"multi_step"``)."""

    plan_steps: int = 0
    """Number of steps in the logical plan."""

    selected_capabilities: int = 0
    """Number of capability bindings made."""

    observations: int = 0
    """Number of Observations produced by the Execution stage."""

    verifiers: int = 0
    """Number of verifier checks that ran."""

    memory_operations: int = 0
    """Number of memory operations (extractions, writes, contradictions)."""

    activity_depth: int = 0
    """Depth of the Activity span tree (0 if no Activity created)."""

    retries: int = 0
    """Total retries across all stages."""

    execution_state: str = "pending"
    """Final execution state: completed, failed, short_circuited, etc."""

    tenant_id: str = ""
    """Tenant that owned this request.  Populated from ``resource_scope``."""
    workspace_id: str = ""
    """Workspace within the tenant, if applicable."""

    # ── Intelligence metrics (Phase 7, Sprint 1) ─────────────────────────

    belief_count: int = 0
    """Number of Beliefs constructed by the Reasoning stage."""

    evidence_count: int = 0
    """Number of EvidenceItems collected during reasoning."""

    contradiction_count: int = 0
    """Number of cross-source contradictions detected."""

    counter_hypothesis_count: int = 0
    """Number of counter-hypotheses generated."""

    reasoning_confidence: float = 0.0
    """Overall confidence score from the Reasoning stage."""

    # ── Knowledge metrics (Phase 7, Sprint 2) ────────────────────────────

    knowledge_entity_count: int = 0
    """Number of entity nodes in the knowledge graph."""

    knowledge_fact_count: int = 0
    """Number of fact nodes in the knowledge graph."""

    knowledge_edge_count: int = 0
    """Number of edges in the knowledge graph."""

    knowledge_nodes_traversed: int = 0
    """Number of nodes traversed during knowledge queries."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "reasoning_complexity": self.reasoning_complexity,
            "plan_steps": self.plan_steps,
            "selected_capabilities": self.selected_capabilities,
            "observations": self.observations,
            "verifiers": self.verifiers,
            "memory_operations": self.memory_operations,
            "activity_depth": self.activity_depth,
            "retries": self.retries,
            "execution_state": self.execution_state,
            "tenant_id": self.tenant_id,
            "workspace_id": self.workspace_id,
            "belief_count": self.belief_count,
            "evidence_count": self.evidence_count,
            "contradiction_count": self.contradiction_count,
            "counter_hypothesis_count": self.counter_hypothesis_count,
            "reasoning_confidence": self.reasoning_confidence,
            "knowledge_entity_count": self.knowledge_entity_count,
            "knowledge_fact_count": self.knowledge_fact_count,
            "knowledge_edge_count": self.knowledge_edge_count,
            "knowledge_nodes_traversed": self.knowledge_nodes_traversed,
        }

    def to_snapshot_dict(self) -> dict[str, Any]:
        """Like ``to_dict()`` but includes the active ``RuntimeVersion``."""
        d = self.to_dict()
        d["runtime_version"] = RUNTIME_VERSION.to_dict()
        return d

    @staticmethod
    def from_context(ctx: PipelineContext) -> ArchitectureMetrics:
        """Extract architecture metrics from a completed PipelineContext."""

        plan = ctx.plan or {}
        reasoning = ctx.reasoning_assessment or {}
        verification = ctx.verification_result or {}
        outcome = ctx.outcome
        scope = ctx.resource_scope
        rsn = ctx.reasoning_result
        kn = ctx.knowledge_result

        return ArchitectureMetrics(
            reasoning_complexity=reasoning.get("complexity", "unknown"),
            plan_steps=len(plan.get("steps", [])),
            selected_capabilities=len(ctx.selected_capabilities or {}),
            observations=len(outcome.observations) if outcome else 0,
            verifiers=len(verification.get("verdicts", [])),
            memory_operations=1 if ctx.store_decision else 0,
            activity_depth=1 if ctx.activity_id else 0,
            retries=0,  # populated by Pipeline.execute retry tracking
            execution_state=ctx.execution_state,
            tenant_id=scope.tenant_id if scope else "",
            workspace_id=scope.workspace_id or "" if scope else "",
            belief_count=len(rsn.beliefs) if rsn else 0,
            evidence_count=len(rsn.evidence) if rsn else 0,
            contradiction_count=len(rsn.contradictions) if rsn else 0,
            counter_hypothesis_count=len(rsn.counter_hypotheses) if rsn else 0,
            reasoning_confidence=rsn.confidence if rsn else 0.0,
            knowledge_entity_count=len(kn.entities) if kn else 0,
            knowledge_fact_count=len(kn.facts) if kn else 0,
            knowledge_edge_count=kn.edge_count if kn else 0,
            knowledge_nodes_traversed=kn.node_count if kn else 0,
        )
