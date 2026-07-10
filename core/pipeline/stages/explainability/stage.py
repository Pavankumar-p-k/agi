"""ExplainabilityStage — wraps the decision chain into a structured explanation.

Adapts ``core/research/synthesizer.py::FactSynthesizer`` to produce
``ExplanationResult``, consuming all prior pipeline artifacts
(reasoning, knowledge, planning, reflection) to generate a holistic
explanation.

Pipeline position: after Metrics, before Formatter (Sprint 7).
"""
from __future__ import annotations

from typing import Any

from core.pipeline.base import PipelineStage, StageOutcome, StageResult
from core.pipeline.context import PipelineContext
from core.pipeline.explanation_result import ExplanationResult
from core.research.synthesizer import FactSynthesizer


class ExplainabilityStage(PipelineStage):
    """Canonical explainability stage.

    Consumes all prior pipeline artifacts and produces a structured
    ``ExplanationResult`` that the Formatter stage renders into the
    final response.
    """

    def __init__(self, synthesizer: FactSynthesizer | None = None) -> None:
        self._synthesizer = synthesizer or FactSynthesizer()

    @property
    def name(self) -> str:
        return "explainability"

    async def execute(self, context: PipelineContext) -> StageResult:
        # ── Gather all prior artifacts ──────────────────────────────────
        reasoning = context.reasoning_result
        knowledge = context.knowledge_result
        planner = context.planner_result
        reflection = context.reflection_result
        verification = context.verification_result or {}
        plan = context.plan or {}
        outcome = context.outcome

        # Build reasoning trace from available artifacts
        trace = self._build_reasoning_trace(context)

        # Build fact list from reasoning beliefs
        facts = self._build_facts(context)

        # Build key findings from reasoning + knowledge + reflection
        findings = self._build_key_findings(context)

        # Build contradictions from reasoning
        contradictions = self._build_contradictions(reasoning)

        # Build knowledge sources
        sources = self._build_knowledge_sources(knowledge)

        # Compute overall confidence
        confidence = self._compute_confidence(reasoning, reflection, knowledge)

        # Run synthesizer if we have facts, otherwise build a minimal explanation
        if facts:
            report = self._synthesizer.synthesize(
                topic=context.raw_input or "Request",
                facts=facts,
            )
            summary = report.summary
            if not sources:
                sources = tuple(report.sources_consulted)
            confidence = report.overall_confidence
        else:
            ctx_summary = _build_summary_from_context(context)
            summary = ctx_summary

        # Build structured detail dumps
        reasoning_detail = _dump_reasoning(reasoning)
        plan_detail = _dump_plan(plan, planner)
        reflection_detail = _dump_reflection(reflection)

        explanation_id = _make_explanation_id(context.services)

        explanation = ExplanationResult(
            explanation_id=explanation_id,
            request_id=context.request_id,
            summary=summary,
            confidence=round(confidence, 2),
            reasoning_trace=tuple(trace),
            key_findings=tuple(findings),
            contradictions=tuple(contradictions),
            knowledge_sources=tuple(sources),
            reasoning_detail=reasoning_detail,
            plan_detail=plan_detail,
            reflection_detail=reflection_detail,
        )

        context.explanation = explanation

        return StageResult(outcome=StageOutcome.CONTINUE, context=context)

    def _build_reasoning_trace(self, context: PipelineContext) -> list[str]:
        trace: list[str] = []
        if context.classification:
            trace.append(f"intent_classification={context.classification.get('mode', 'unknown')}")
        if context.reasoning_result:
            trace.append(f"reasoning=completed")
        if context.planner_result:
            trace.append(f"planning={context.planner_result.total_candidates}_strategies")
        if context.execution_state:
            trace.append(f"execution={context.execution_state}")
        if context.reflection_result:
            trace.append(f"reflection=completed")
        return trace

    def _build_facts(self, context: PipelineContext) -> list[Any]:
        """Build Fact objects from pipeline artifacts."""
        from core.research.models import Fact

        facts: list[Fact] = []
        reasoning = context.reasoning_result

        if reasoning:
            for belief in (reasoning.beliefs or ()):
                facts.append(Fact(
                    fact_id=context.services.uuid4(),
                    source_url="reasoning",
                    claim=belief.claim,
                    confidence=belief.confidence,
                    category="reasoning",
                ))

        knowledge = context.knowledge_result
        if knowledge:
            for entity in (knowledge.entities or ()):
                facts.append(Fact(
                    fact_id=context.services.uuid4(),
                    source_url="knowledge_graph",
                    claim=str(entity)[:200],
                    confidence=0.7,
                    category="knowledge",
                ))

        return facts

    def _build_key_findings(self, context: PipelineContext) -> list[str]:
        findings: list[str] = []
        reasoning = context.reasoning_result
        reflection = context.reflection_result
        outcome = context.outcome

        if reasoning:
            for b in (reasoning.beliefs or ()):
                if b.confidence >= 0.7:
                    findings.append(b.claim)

        if reflection:
            for lesson in (reflection.lessons or ()):
                findings.append(f"Lesson: {lesson}")

        if outcome and hasattr(outcome, 'observations'):
            for obs in (outcome.observations or []):
                text = str(obs)[:150]
                findings.append(text)

        return findings

    def _build_contradictions(self, reasoning: Any) -> list[str]:
        if not reasoning:
            return []
        return [str(c) for c in (reasoning.contradictions or ())]

    def _build_knowledge_sources(self, knowledge: Any) -> list[str]:
        if not knowledge:
            return []
        sources: list[str] = []
        if hasattr(knowledge, 'entities') and knowledge.entities:
            sources.append("knowledge_graph")
        return sources

    def _compute_confidence(self, reasoning: Any, reflection: Any, knowledge: Any) -> float:
        scores: list[float] = []
        if reasoning:
            scores.append(reasoning.confidence)
        if reflection:
            scores.append(reflection.overall_confidence)
        if scores:
            return sum(scores) / len(scores)
        return 0.5


def _make_explanation_id(services: Any) -> str:
    """Generate a deterministic or random explanation id."""
    raw = services.uuid4()
    if isinstance(raw, str):
        return f"exp_{raw[:24]}"
    return f"exp_{raw.hex[:24]}"


def _build_summary_from_context(context: PipelineContext) -> str:
    """Build a fallback summary when the synthesizer has no facts."""
    parts: list[str] = []
    raw = context.raw_input or ""
    classification = context.classification or {}
    execution = context.execution_state or "completed"

    parts.append(f"Processed request: '{raw[:100]}'")
    parts.append(f"Classification: {classification.get('mode', 'unknown')}")
    parts.append(f"Execution state: {execution}")

    if context.reflection_result:
        rf = context.reflection_result
        parts.append(f"Reflection: success_rating={rf.success_rating}, "
                      f"confidence={rf.overall_confidence}")

    return " | ".join(parts)


def _dump_reasoning(reasoning: Any) -> dict[str, Any]:
    if not reasoning:
        return {}
    return {
        "belief_count": len(getattr(reasoning, 'beliefs', []) or []),
        "evidence_count": len(getattr(reasoning, 'evidence', []) or []),
        "contradiction_count": len(getattr(reasoning, 'contradictions', []) or []),
        "confidence": getattr(reasoning, 'confidence', 0.0),
    }


def _dump_plan(plan: dict[str, Any], planner: Any) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if plan:
        result["goal"] = plan.get("goal", "")
        result["step_count"] = len(plan.get("steps", []))
    if planner:
        result["strategy_count"] = getattr(planner, 'total_candidates', 0)
    return result


def _dump_reflection(reflection: Any) -> dict[str, Any]:
    if not reflection:
        return {}
    return {
        "success_rating": getattr(reflection, 'success_rating', 0.0),
        "lessons": list(getattr(reflection, 'lessons', []) or []),
        "patterns": list(getattr(reflection, 'patterns', []) or []),
        "overall_confidence": getattr(reflection, 'overall_confidence', 0.0),
    }
