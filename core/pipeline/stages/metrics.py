"""Metrics stage.

Aggregates timing, token counts, and intelligence metrics collected by
earlier stages and emits them through ``core.event_bus``.

Enhanced in Sprint 8 to collect all intelligence-specific metrics from
``ArchitectureMetrics`` and per-stage timing data.
"""
from __future__ import annotations

from typing import Any

from core.pipeline.architecture_metrics import ArchitectureMetrics
from core.pipeline.base import PipelineStage, StageOutcome, StageResult
from core.pipeline.context import PipelineContext


# ── Intelligence metric key prefixes ──────────────────────────────────────────
# All intelligence metrics are stored under ``context.metrics["intel_*"]``
# for clean separation from operational metrics (tokens, provider, etc.).

INTEL_METRICS_MAP: dict[str, str] = {
    "belief_count": "intel_beliefs",
    "evidence_count": "intel_evidence",
    "contradiction_count": "intel_contradictions",
    "counter_hypothesis_count": "intel_counter_hypotheses",
    "reasoning_confidence": "intel_reasoning_confidence",
    "reasoning_complexity": "intel_reasoning_complexity",
    "knowledge_entity_count": "intel_knowledge_entities",
    "knowledge_fact_count": "intel_knowledge_facts",
    "knowledge_edge_count": "intel_knowledge_edges",
    "knowledge_nodes_traversed": "intel_knowledge_nodes",
    "plan_strategy_count": "intel_plan_strategies",
    "plan_ranking_margin": "intel_plan_ranking_margin",
    "plan_selected_confidence": "intel_plan_confidence",
    "plan_steps": "intel_plan_steps",
    "reflection_success_rating": "intel_reflection_success",
    "reflection_lessons_count": "intel_reflection_lessons",
    "reflection_patterns_count": "intel_reflection_patterns",
    "learning_records_count": "intel_learning_records",
    "learning_store_decisions": "intel_learning_stores",
    "learning_skip_decisions": "intel_learning_skips",
    "policy_optimization_applied": "intel_policy_opt_applied",
    "policy_suggested_profile": "intel_policy_opt_profile",
    "policy_rate_limit_multiplier": "intel_policy_opt_multiplier",
    "explanation_produced": "intel_explanation_produced",
    "explanation_confidence": "intel_explanation_confidence",
}

# Stages whose timing data should be collected
INTELLIGENCE_STAGES = frozenset({
    "knowledge", "reasoning", "planner", "reflection",
    "learning", "policy_optimization", "explainability",
})


class MetricsStage(PipelineStage):
    """Aggregate and emit observability data for this request.

    Collects:
    - Operational metrics: intent, provider, token counts.
    - Intelligence metrics: all ``ArchitectureMetrics`` fields mapped to
      ``intel_*`` keys in ``context.metrics``.
    - Per-intelligence-stage timing: duration of each intelligence stage,
      stored as ``intel_timing_<stage>`` in milliseconds.
    """

    @property
    def name(self) -> str:
        return "metrics"

    async def execute(self, context: PipelineContext) -> StageResult:
        # ── Operational metrics (backward compat) ─────────────────────────
        context.metrics.setdefault(
            "intent",
            context.classification.get("mode", "unknown") if context.classification else "unknown",
        )
        context.metrics.setdefault(
            "provider",
            context.execution_result.get("provider", "unknown") if context.execution_result else "unknown",
        )
        context.metrics.setdefault(
            "tokens",
            context.execution_result.get("tokens", 0) if context.execution_result else 0,
        )

        # ── Intelligence metrics from ArchitectureMetrics ─────────────────
        am = ArchitectureMetrics.from_context(context)
        am_dict = am.to_dict()

        for src_key, dst_key in INTEL_METRICS_MAP.items():
            value = am_dict.get(src_key)
            if value is not None:
                context.metrics[dst_key] = value

        # ── Per-stage timing ──────────────────────────────────────────────
        stage_metrics = context.metrics.get("_stage", {})
        if isinstance(stage_metrics, dict):
            for stage_name, sm in stage_metrics.items():
                if stage_name in INTELLIGENCE_STAGES and isinstance(sm, dict):
                    elapsed_ms = sm.get("elapsed_ms", 0) or 0
                    context.metrics[f"intel_timing_{stage_name}"] = elapsed_ms

        return StageResult(outcome=StageOutcome.CONTINUE, context=context)
