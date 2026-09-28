"""MetricsStage — per-request metrics accumulation (intel_* fields)."""
from typing import Any

from core.pipeline.base import PipelineStage, StageOutcome, StageResult
from core.pipeline.pipeline import PipelineContext

INTELLIGENCE_STAGES = ("knowledge", "reasoning", "planner", "reflection",
                       "learning", "epistemic")


class MetricsStage(PipelineStage):
    @property
    def name(self) -> str:
        return "metrics"

    async def execute(self, context: PipelineContext) -> StageResult:
        metrics: dict[str, Any] = {}
        if isinstance(context.classification, dict):
            metrics["intent"] = context.classification.get("mode")
        if isinstance(context.execution_result, dict):
            if "tokens" in context.execution_result:
                metrics["tokens"] = context.execution_result["tokens"]
            if "provider" in context.execution_result:
                metrics["provider"] = context.execution_result["provider"]

        # Intelligence metrics
        rr = context.reasoning_result
        metrics["intel_beliefs"] = len(getattr(rr, "beliefs", ()) or ())
        metrics["intel_evidence"] = len(getattr(rr, "evidence", ()) or ())
        metrics["intel_reasoning_confidence"] = getattr(rr, "confidence", 0.0)
        metrics["intel_reasoning_complexity"] = getattr(rr, "complexity", "")

        kr = context.knowledge_result
        metrics["intel_knowledge_entities"] = len(getattr(kr, "entities", ()) or ())
        metrics["intel_knowledge_facts"] = len(getattr(kr, "facts", ()) or ())
        metrics["intel_knowledge_edges"] = int(getattr(kr, "edge_count", 0) or 0)
        metrics["intel_knowledge_nodes"] = int(getattr(kr, "node_count", 0) or 0)

        refl = context.reflection_result
        metrics["intel_reflection_success"] = float(
            getattr(refl, "success_rating", 0.0) or 0.0)
        pr = context.planner_result
        metrics["intel_plan_strategies"] = len(
            getattr(getattr(pr, "ranking", None), "strategies", ()) or ())

        # Per-stage timing for intelligence stages only
        stage_timings = context.metrics.get("_stage", {})
        for sname in INTELLIGENCE_STAGES:
            if sname in stage_timings:
                metrics[f"intel_timing_{sname}"] = stage_timings[sname].get(
                    "elapsed_ms", 0)

        context.metrics.update(metrics)
        return StageResult(outcome=StageOutcome.CONTINUE, context=context)


__all__ = ["MetricsStage", "INTELLIGENCE_STAGES"]
