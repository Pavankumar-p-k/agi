"""ReasoningStage — canonical pipeline stage for belief-driven reasoning.

This stage adapts the existing ``core/research/`` reasoning engines
(ReasoningEngine, FactReasoner, EvidenceTracker) into the pipeline.
It contains minimal business logic — the actual reasoning is delegated
to the wrapped engines.

Pipeline position: after ContextRetrieval, before Planner.

Legacy contract: ``context.reasoning_assessment`` is still populated
for backward compatibility until Sprint 3 completes the Planner
migration.
"""
from __future__ import annotations

import uuid
from typing import Any

from core.pipeline.base import PipelineStage, StageOutcome, StageResult
from core.pipeline.context import PipelineContext
from core.pipeline.reasoning_result import ReasoningResult
from core.research.evidence_tracker import EvidenceTracker
from core.research.reasoner import FactReasoner
from core.research.reasoning import ReasoningEngine


class ReasoningStage(PipelineStage):
    """Canonical reasoning stage.

    Front-door for all reasoning in the pipeline.  Delegates to the
    existing ``core/research/`` engines rather than implementing its
    own algorithms.
    """

    def __init__(self) -> None:
        self._engine = ReasoningEngine()
        self._fact_reasoner = FactReasoner()
        self._evidence_tracker = EvidenceTracker()

    @property
    def name(self) -> str:
        return "reasoning"

    async def execute(self, context: PipelineContext) -> StageResult:
        classification = context.classification or {}
        raw_input = context.raw_input or ""
        retrieved = context.retrieved_context or {}

        # ── Step 1: Complexity assessment (preserved from legacy ReasonerStage) ─
        complexity = self._assess_complexity(classification, raw_input)
        requirements = self._assess_requirements(classification, raw_input, retrieved)
        constraints = self._assess_constraints(classification, raw_input)
        legacy_confidence = self._compute_confidence(classification, complexity)
        estimated_steps = self._estimate_steps(complexity, requirements)

        # ── Step 2: Evidence collection ────────────────────────────────────────
        facts = self._collect_facts(raw_input, retrieved)

        # ── Step 3: Belief construction ────────────────────────────────────────
        state = self._engine.initialize(raw_input)
        if facts:
            self._engine.add_evidence(state, facts)

        # ── Step 4: Contradiction detection ────────────────────────────────────
        comparison = self._fact_reasoner.analyze(facts) if facts else None

        # ── Step 5: Counter-hypothesis generation ──────────────────────────────
        counter_hypotheses: list[Any] = []
        for belief in state.uncertain_beliefs():
            ch = self._engine.generate_challenge(state, belief)
            if ch is not None:
                counter_hypotheses.append(ch)

        # ── Step 6: Belief revision ────────────────────────────────────────────
        overall_confidence = self._derive_overall_confidence(
            state, legacy_confidence, complexity,
        )

        # ── Step 7: Build ReasoningResult ──────────────────────────────────────
        reasoning_id = _make_reasoning_id(context.services)
        reason_trace = self._build_trace(complexity, len(facts), state)

        result = ReasoningResult(
            reasoning_id=reasoning_id,
            activity_id=context.activity_id or "",
            complexity=complexity,
            beliefs=tuple(state.beliefs),
            evidence=tuple(
                item
                for belief in state.beliefs
                for item in belief.evidence
            ),
            contradictions=tuple(comparison.contradictions) if comparison else (),
            counter_hypotheses=tuple(counter_hypotheses),
            confidence=overall_confidence,
            reasoning_trace=tuple(reason_trace),
            metadata={
                "requirements": requirements,
                "constraints": constraints,
                "estimated_steps": estimated_steps,
                "legacy_classifier_confidence": legacy_confidence,
                "retrieved_facts": len(facts),
                "source_count": len(comparison.sources_analyzed) if comparison else 0,
            },
        )

        # ── Write to context (dual-write for backward compat) ──────────────────
        context.reasoning_result = result
        context.reasoning_assessment = result.to_assessment_dict()

        return StageResult(outcome=StageOutcome.CONTINUE, context=context)

    # ── Legacy complexity classifier (preserved from ReasonerStage) ──────────

    def _assess_complexity(
        self, classification: dict[str, Any], raw_input: str,
    ) -> str:
        mode = classification.get("mode", "chat")
        sub_type = classification.get("sub_type", "")
        agent_kw = {"agent", "autonomous", "delegate", "multi-step", "workflow"}
        multi_kw = {"research", "compare", "analyze", "investigate", "build",
                    "create", "develop"}
        if mode == "agent" or any(k in raw_input.lower() for k in agent_kw):
            return "agentic"
        if mode in ("action", "codebase") or any(k in raw_input.lower() for k in multi_kw):
            return "multi_step"
        return "simple"

    def _assess_requirements(
        self, classification: dict[str, Any], raw_input: str, retrieved: dict[str, Any],
    ) -> list[str]:
        reqs: list[str] = []
        lower = raw_input.lower()
        if any(k in lower for k in {"search", "find", "research", "look up",
                                     "what is", "who is", "weather", "news"}):
            reqs.append("research")
        if any(k in lower for k in {"open", "navigate", "browse", "website",
                                     "url", "http"}):
            reqs.append("browser")
        if any(k in lower for k in {"code", "program", "function", "class",
                                     "implement", "refactor", "debug", "test"}):
            reqs.append("coding")
        if any(k in lower for k in {"remember", "recall", "forget", "my name",
                                     "preference"}):
            reqs.append("memory")
        return reqs

    def _assess_constraints(
        self, classification: dict[str, Any], raw_input: str,
    ) -> list[str]:
        constraints: list[str] = []
        lower = raw_input.lower()
        if any(k in lower for k in {"urgent", "asap", "quick", "fast", "immediately"}):
            constraints.append("speed")
        if any(k in lower for k in {"accurate", "precise", "exact", "fact-check"}):
            constraints.append("accuracy")
        if any(k in lower for k in {"real-time", "live", "streaming", "current"}):
            constraints.append("freshness")
        return constraints

    def _compute_confidence(
        self, classification: dict[str, Any], complexity: str,
    ) -> float:
        confidence = classification.get("confidence", 0.5)
        if complexity == "simple":
            return min(confidence + 0.3, 1.0)
        if complexity == "multi_step":
            return confidence
        return max(confidence - 0.2, 0.1)

    def _estimate_steps(
        self, complexity: str, requirements: list[str],
    ) -> int:
        if complexity == "simple":
            return 1
        if complexity == "multi_step":
            return max(len(requirements) + 1, 2)
        return max(len(requirements) + 2, 3)

    # ── Research engine integration ──────────────────────────────────────────

    def _collect_facts(
        self, raw_input: str, retrieved: dict[str, Any],
    ) -> list[Any]:
        from core.research.models import Fact

        facts: list[Fact] = []
        if not retrieved:
            return facts

        memories = retrieved.get("memories", [])
        for mem in memories:
            content = ""
            if isinstance(mem, dict):
                content = mem.get("content", mem.get("text", ""))
            elif hasattr(mem, "content"):
                content = getattr(mem, "content")
            if content:
                facts.append(Fact(
                    fact_id=f"mem_{len(facts)}",
                    source_url=mem.get("source_url", "") if isinstance(mem, dict) else "",
                    claim=content if isinstance(content, str) else str(content),
                    confidence=mem.get("confidence", 0.5) if isinstance(mem, dict) else 0.5,
                ))
        return facts

    def _derive_overall_confidence(
        self, state: Any, legacy_confidence: float, complexity: str,
    ) -> float:
        if state.beliefs:
            avg_belief_conf = (
                sum(b.confidence for b in state.beliefs) / len(state.beliefs)
            )
            return round((legacy_confidence * 0.3 + avg_belief_conf * 0.7), 3)
        return legacy_confidence

    def _build_trace(
        self, complexity: str, fact_count: int, state: Any,
    ) -> list[str]:
        trace = [
            f"complexity={complexity}",
            f"facts_collected={fact_count}",
            f"beliefs_initialized={len(state.beliefs)}" if state.beliefs else "no_beliefs",
        ]
        if state.beliefs:
            confirmed = len(state.confirmed_beliefs())
            challenged = len(state.challenged_beliefs())
            trace.append(f"confirmed={confirmed}")
            trace.append(f"challenged={challenged}")
        return [t for t in trace if t is not None]


def _make_reasoning_id(services: Any) -> str:
    """Generate a deterministic or random reasoning id."""
    try:
        return f"rsn_{services.uuid4().hex[:24]}"
    except Exception:
        return f"rsn_{uuid.uuid4().hex[:24]}"
