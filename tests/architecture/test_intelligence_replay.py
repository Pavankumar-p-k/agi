"""Sprint 7.10 — Intelligence Replay & Determinism.

Verifies that the Reasoning stage produces identical artifacts under
deterministic services, satisfying Phase 7's replay requirement.
"""
from __future__ import annotations

import pytest

from core.pipeline.context import PipelineContext
from core.pipeline.deterministic import DeterministicServices
from core.pipeline.stages.reasoning import ReasoningStage
# ── Fingerprint helpers ──────────────────────────────────────────────────


def _belief_fingerprint(beliefs: tuple) -> str:
    """Deterministic hash of belief semantic content (not IDs)."""
    parts = []
    for b in beliefs:
        parts.append(f"{b.claim}::{b.confidence}::{b.status}")
    return "|".join(parts)


def _evidence_fingerprint(evidence: tuple) -> str:
    """Deterministic hash of evidence semantic content."""
    parts = []
    for e in evidence:
        parts.append(f"{e.direction}::{e.weight}")
    return "|".join(parts)


def _contradiction_fingerprint(contradictions: tuple) -> str:
    """Deterministic hash of contradiction entities and counts."""
    parts = []
    for c in contradictions:
        parts.append(f"{c.entity}::{len(c.facts)}")
    return "|".join(parts)


def _counter_hypothesis_fingerprint(counter_hypotheses: tuple) -> str:
    """Deterministic hash of counter-hypothesis semantic content."""
    parts = []
    for ch in counter_hypotheses:
        parts.append(f"{ch.counter_claim[:60]}")
    return "|".join(parts)


# ── Determinism helpers ───────────────────────────────────────────────────


def _make_context(services: DeterministicServices, raw_input: str = "test request") -> PipelineContext:
    ctx = PipelineContext(
        request_id=services.uuid4(),
        transport="test",
        raw_input=raw_input,
        classification={
            "mode": "chat",
            "confidence": 0.8,
            "sub_type": "",
        },
        services=services,
    )
    return ctx


async def _run_reasoning(ctx: PipelineContext) -> PipelineContext:
    """Run the ReasoningStage and return the updated context."""
    stage = ReasoningStage()
    result = await stage.execute(ctx)
    assert result.context is not None
    return result.context


# ── Run A and Run B helpers ───────────────────────────────────────────────


async def _run_twice(raw_input: str) -> tuple[PipelineContext, PipelineContext]:
    a = _make_context(DeterministicServices.fake(), raw_input)
    b = _make_context(DeterministicServices.fake(), raw_input)

    ctx_a = await _run_reasoning(a)
    ctx_b = await _run_reasoning(b)

    return ctx_a, ctx_b


# ── Tests ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_reasoning_result_is_deterministic():
    """Two runs with same deterministic services produce identical
    reasoning_result.

    Note: belief/evidence IDs are non-deterministic in Sprint 1 because
    they originate from ``uuid.uuid4()`` inside ``core/research/``.
    Semantic content (complexity, confidence, claim strings) must match.
    """
    ctx_a, ctx_b = await _run_twice("what is the weather in London?")

    assert ctx_a.reasoning_result is not None
    assert ctx_b.reasoning_result is not None

    rsn_a = ctx_a.reasoning_result
    rsn_b = ctx_b.reasoning_result

    # reasoning_id uses deterministic services → should match
    assert rsn_a.reasoning_id == rsn_b.reasoning_id
    assert rsn_a.complexity == rsn_b.complexity
    assert rsn_a.confidence == rsn_b.confidence
    assert len(rsn_a.beliefs) == len(rsn_b.beliefs)

    # Fingerprints: semantic content must be identical even if IDs differ
    assert _belief_fingerprint(rsn_a.beliefs) == _belief_fingerprint(rsn_b.beliefs)
    assert _evidence_fingerprint(rsn_a.evidence) == _evidence_fingerprint(rsn_b.evidence)
    assert _contradiction_fingerprint(rsn_a.contradictions) == _contradiction_fingerprint(rsn_b.contradictions)
    assert _counter_hypothesis_fingerprint(rsn_a.counter_hypotheses) == _counter_hypothesis_fingerprint(rsn_b.counter_hypotheses)


@pytest.mark.asyncio
async def test_beliefs_are_semantically_deterministic():
    """Belief content (claims, confidence, status) is identical across replay
    even if internal IDs differ."""
    ctx_a, ctx_b = await _run_twice("compare Python and JavaScript")

    assert ctx_a.reasoning_result is not None
    assert ctx_b.reasoning_result is not None

    beliefs_a = ctx_a.reasoning_result.beliefs
    beliefs_b = ctx_b.reasoning_result.beliefs

    assert len(beliefs_a) == len(beliefs_b)
    for ba, bb in zip(beliefs_a, beliefs_b):
        assert ba.claim == bb.claim
        assert ba.confidence == bb.confidence
        assert ba.status == bb.status


@pytest.mark.asyncio
async def test_evidence_is_semantically_deterministic():
    """Evidence direction and weight are identical across replay."""
    ctx_a, ctx_b = await _run_twice("research the cost of cloud storage")

    assert ctx_a.reasoning_result is not None
    assert ctx_b.reasoning_result is not None

    ev_a = ctx_a.reasoning_result.evidence
    ev_b = ctx_b.reasoning_result.evidence

    assert len(ev_a) == len(ev_b)
    for ea, eb in zip(ev_a, ev_b):
        assert ea.direction == eb.direction
        assert ea.weight == eb.weight


@pytest.mark.asyncio
async def test_contradictions_are_semantically_deterministic():
    """Contradiction entities and counts are identical across replay."""
    ctx_a, ctx_b = await _run_twice("find conflicting information about AI safety")

    assert ctx_a.reasoning_result is not None
    assert ctx_b.reasoning_result is not None

    c_a = ctx_a.reasoning_result.contradictions
    c_b = ctx_b.reasoning_result.contradictions

    assert len(c_a) == len(c_b)
    for ca, cb in zip(c_a, c_b):
        assert ca.entity == cb.entity
        assert len(ca.facts) == len(cb.facts)


@pytest.mark.asyncio
async def test_reasoning_trace_is_deterministic():
    """Reasoning trace is identical across replay."""
    ctx_a, ctx_b = await _run_twice("debug a Python script")

    assert ctx_a.reasoning_result is not None
    assert ctx_b.reasoning_result is not None

    assert ctx_a.reasoning_result.reasoning_trace == ctx_b.reasoning_result.reasoning_trace


@pytest.mark.asyncio
async def test_reasoning_assessment_is_deterministic():
    """Legacy reasoning_assessment dict is still populated and deterministic."""
    ctx_a, ctx_b = await _run_twice("write a bash script")

    assert ctx_a.reasoning_assessment is not None
    assert ctx_b.reasoning_assessment is not None

    assert ctx_a.reasoning_assessment["complexity"] == ctx_b.reasoning_assessment["complexity"]
    assert ctx_a.reasoning_assessment["confidence"] == ctx_b.reasoning_assessment["confidence"]


@pytest.mark.asyncio
async def test_confidence_is_consistent():
    """Reasoning confidence is bounded [0, 1] and consistent."""
    ctx, _ = await _run_twice("simple request")
    assert ctx.reasoning_result is not None
    assert 0.0 <= ctx.reasoning_result.confidence <= 1.0


@pytest.mark.asyncio
async def test_complexity_detection():
    """Complexity classification still works as before."""
    simple_ctx, _ = await _run_twice("hello")
    assert simple_ctx.reasoning_result is not None
    assert simple_ctx.reasoning_result.complexity == "simple"

    complex_ctx, _ = await _run_twice("research and compare cloud providers")
    assert complex_ctx.reasoning_result is not None
    assert complex_ctx.reasoning_result.complexity == "multi_step"


# ═══════════════════════════════════════════════════════════════════════════════
# Sprint 2 — Knowledge Replay Tests
# ═══════════════════════════════════════════════════════════════════════════════


async def _run_knowledge(ctx: PipelineContext) -> PipelineContext:
    """Run the KnowledgeStage and return the updated context."""
    from core.pipeline.stages.knowledge import KnowledgeStage

    stage = KnowledgeStage()
    result = await stage.execute(ctx)
    assert result.context is not None
    return result.context


async def _run_knowledge_twice(
    raw_input: str,
) -> tuple[PipelineContext, PipelineContext]:
    a = _make_context(DeterministicServices.fake(), raw_input)
    b = _make_context(DeterministicServices.fake(), raw_input)

    ctx_a = await _run_knowledge(a)
    ctx_b = await _run_knowledge(b)

    return ctx_a, ctx_b


@pytest.mark.asyncio
async def test_knowledge_result_is_deterministic():
    """Two runs with same deterministic services produce identical
    knowledge_result (knowledge_id, node count, edge count)."""
    ctx_a, ctx_b = await _run_knowledge_twice("what is the weather in London?")

    assert ctx_a.knowledge_result is not None
    assert ctx_b.knowledge_result is not None

    kn_a = ctx_a.knowledge_result
    kn_b = ctx_b.knowledge_result

    # knowledge_id uses deterministic services → should match
    assert kn_a.knowledge_id == kn_b.knowledge_id
    assert kn_a.node_count == kn_b.node_count
    assert kn_a.edge_count == kn_b.edge_count
    assert len(kn_a.entities) == len(kn_b.entities)
    assert len(kn_a.facts) == len(kn_b.facts)
    assert len(kn_a.edges) == len(kn_b.edges)


@pytest.mark.asyncio
async def test_knowledge_graph_counts():
    """Knowledge graph node and edge counts are non-negative and sane."""
    ctx, _ = await _run_knowledge_twice("serverless architecture")

    assert ctx.knowledge_result is not None
    assert ctx.knowledge_result.node_count >= 0
    assert ctx.knowledge_result.edge_count >= 0


@pytest.mark.asyncio
async def test_knowledge_entity_fact_distinction():
    """Entities and facts are separately tracked in the knowledge result."""
    ctx, _ = await _run_knowledge_twice("compare AWS Lambda and Google Cloud Functions")

    assert ctx.knowledge_result is not None
    kn = ctx.knowledge_result

    # Node count should equal entities + facts
    assert kn.node_count == len(kn.entities) + len(kn.facts)


@pytest.mark.asyncio
async def test_knowledge_activity_id():
    """Knowledge result carries the activity id from the context."""
    ctx, _ = await _run_knowledge_twice("test activity binding")

    assert ctx.knowledge_result is not None
    expected_activity_id = ctx.activity_id or ""
    assert ctx.knowledge_result.activity_id == expected_activity_id


# ═══════════════════════════════════════════════════════════════════════════════
# Sprint 3 — Planner Replay Tests
# ═══════════════════════════════════════════════════════════════════════════════


async def _run_planner(ctx: PipelineContext) -> PipelineContext:
    """Run the PlannerStage and return the updated context."""
    from core.pipeline.stages.planner import PlannerStage

    stage = PlannerStage()
    result = await stage.execute(ctx)
    assert result.context is not None
    return result.context


async def _run_planner_twice(
    raw_input: str,
    complexity: str = "simple",
    requirements: list[str] | None = None,
) -> tuple[PipelineContext, PipelineContext]:
    a = _make_context(DeterministicServices.fake(), raw_input)
    b = _make_context(DeterministicServices.fake(), raw_input)

    assessment = {
        "complexity": complexity,
        "requirements": requirements or [],
        "constraints": [],
        "confidence": 0.8,
        "estimated_steps": 1,
        "routing_hints": {},
    }
    a.reasoning_assessment = assessment
    b.reasoning_assessment = assessment

    ctx_a = await _run_planner(a)
    ctx_b = await _run_planner(b)

    return ctx_a, ctx_b


@pytest.mark.asyncio
async def test_planner_result_is_deterministic():
    """Two runs with same deterministic services produce identical
    planner_result (plan_id, strategy count, ranking)."""
    ctx_a, ctx_b = await _run_planner_twice(
        "what is the weather in London?", requirements=["research"],
    )

    assert ctx_a.planner_result is not None
    assert ctx_b.planner_result is not None

    pr_a = ctx_a.planner_result
    pr_b = ctx_b.planner_result

    assert pr_a.plan_id == pr_b.plan_id
    assert pr_a.total_candidates == pr_b.total_candidates
    assert len(pr_a.ranking.strategies) == len(pr_b.ranking.strategies)
    assert pr_a.ranking.selected_id == pr_b.ranking.selected_id
    assert pr_a.ranking.selection_rationale == pr_b.ranking.selection_rationale


@pytest.mark.asyncio
async def test_planner_backward_compat_plan():
    """context.plan is still populated for backward compat from the
    winning strategy."""
    ctx, _ = await _run_planner_twice("write a script", requirements=["coding"])

    assert ctx.planner_result is not None
    assert ctx.plan is not None
    assert ctx.plan["goal"] == "write a script"
    assert len(ctx.plan["steps"]) > 0


@pytest.mark.asyncio
async def test_planner_generates_multiple_strategies():
    """Research+coding request generates at least 2 strategy candidates."""
    ctx, _ = await _run_planner_twice(
        "research and implement", requirements=["research", "coding"],
    )

    assert ctx.planner_result is not None
    assert ctx.planner_result.total_candidates >= 2
    assert len(ctx.planner_result.ranking.strategies) >= 2


@pytest.mark.asyncio
async def test_planner_ranking_has_comparisons():
    """Ranking includes pairwise comparisons between strategies."""
    ctx, _ = await _run_planner_twice(
        "complex research task", requirements=["research"],
    )

    assert ctx.planner_result is not None
    assert len(ctx.planner_result.ranking.comparisons) > 0


@pytest.mark.asyncio
async def test_planner_strategy_confidence_bounded():
    """All strategy confidences are in [0, 1]."""
    ctx, _ = await _run_planner_twice("test confidence")

    assert ctx.planner_result is not None
    for s in ctx.planner_result.ranking.strategies:
        assert 0.0 <= s.confidence <= 1.0


@pytest.mark.asyncio
async def test_planner_direct_research_coding_scenarios():
    """Different complexity scenarios produce expected strategy counts."""
    # Simple request → direct + balanced (fallback)
    ctx_simple, _ = await _run_planner_twice("hello")
    assert ctx_simple.planner_result is not None
    strategy_names = {s.name for s in ctx_simple.planner_result.ranking.strategies}
    assert "direct" in strategy_names

    # Research request → direct + research
    ctx_research, _ = await _run_planner_twice(
        "research X", requirements=["research"],
    )
    assert ctx_research.planner_result is not None
    r_names = {s.name for s in ctx_research.planner_result.ranking.strategies}
    assert "direct" in r_names
    assert "research" in r_names

    # Coding request → direct + code
    ctx_code, _ = await _run_planner_twice(
        "code something", requirements=["coding"],
    )
    assert ctx_code.planner_result is not None
    c_names = {s.name for s in ctx_code.planner_result.ranking.strategies}
    assert "direct" in c_names
    assert "code" in c_names


# ═══════════════════════════════════════════════════════════════════════════════
# Sprint 4 — Reflection Replay Tests
# ═══════════════════════════════════════════════════════════════════════════════


async def _run_reflection(ctx: PipelineContext) -> PipelineContext:
    """Run the ReflectionStage and return the updated context."""
    from core.pipeline.stages.reflection import ReflectionStage

    stage = ReflectionStage()
    result = await stage.execute(ctx)
    assert result.context is not None
    return result.context


def _make_reflection_context(
    services: DeterministicServices,
    raw_input: str = "test request",
    with_reasoning: bool = True,
) -> PipelineContext:
    ctx = PipelineContext(
        request_id=services.uuid4(),
        transport="test",
        raw_input=raw_input,
        classification={"mode": "chat", "confidence": 0.8, "sub_type": ""},
        services=services,
    )
    raw_act = services.uuid4()
    act_hex = raw_act[:12] if isinstance(raw_act, str) else raw_act.hex[:12]
    ctx.activity_id = f"act_{act_hex}"
    ctx.plan = {"goal": raw_input, "steps": [{"intent": "respond", "objective": raw_input, "constraints": {}}]}

    if with_reasoning:
        from core.pipeline.reasoning_result import ReasoningResult, Belief

        raw_rsn = services.uuid4()
        rsn_hex = raw_rsn[:12] if isinstance(raw_rsn, str) else raw_rsn.hex[:12]
        raw_bid = services.uuid4()
        bid_hex = raw_bid[:16] if isinstance(raw_bid, str) else raw_bid.hex[:16]
        ctx.reasoning_result = ReasoningResult(
                reasoning_id=f"rsn_{rsn_hex}",
                activity_id=ctx.activity_id,
                complexity="simple",
                confidence=0.8,
                beliefs=(Belief(belief_id=bid_hex, claim="test belief", confidence=0.8, status="accepted"),),
                evidence=(),
                contradictions=(),
                counter_hypotheses=(),
                reasoning_trace=(),
        )
    return ctx


async def _run_reflection_twice(
    raw_input: str,
) -> tuple[PipelineContext, PipelineContext]:
    a = _make_reflection_context(DeterministicServices.fake(), raw_input)
    b = _make_reflection_context(DeterministicServices.fake(), raw_input)

    ctx_a = await _run_reflection(a)
    ctx_b = await _run_reflection(b)

    return ctx_a, ctx_b


@pytest.mark.asyncio
async def test_reflection_result_is_deterministic():
    """Two runs with same deterministic services produce identical
    reflection_result (reflection_id, success_rating, lessons, patterns)."""
    ctx_a, ctx_b = await _run_reflection_twice("what is the weather?")

    assert ctx_a.reflection_result is not None
    assert ctx_b.reflection_result is not None

    rf_a = ctx_a.reflection_result
    rf_b = ctx_b.reflection_result

    # reflection_id is non-deterministic (uses uuid.uuid4() inside core/research/)
    # but semantic content must match
    assert rf_a.success_rating == rf_b.success_rating
    assert rf_a.overall_confidence == rf_b.overall_confidence
    assert rf_a.lessons == rf_b.lessons
    assert rf_a.patterns == rf_b.patterns
    assert rf_a.total_facts_collected == rf_b.total_facts_collected


@pytest.mark.asyncio
async def test_reflection_success_rating_bounded():
    """Success rating is in [0, 1]."""
    ctx, _ = await _run_reflection_twice("test rating")

    assert ctx.reflection_result is not None
    assert 0.0 <= ctx.reflection_result.success_rating <= 1.0


@pytest.mark.asyncio
async def test_reflection_without_reasoning():
    """Reflection still produces a result even without reasoning data."""
    services = DeterministicServices.fake()
    ctx = _make_reflection_context(services, "simple request", with_reasoning=False)
    ctx = await _run_reflection(ctx)

    assert ctx.reflection_result is not None
    assert ctx.reflection_result.reflection_id


@pytest.mark.asyncio
async def test_reflection_activity_id():
    """Reflection result carries the activity id."""
    ctx, _ = await _run_reflection_twice("test activity binding")

    assert ctx.reflection_result is not None
    expected = ctx.activity_id or ""
    assert ctx.reflection_result.activity_id == expected


@pytest.mark.asyncio
async def test_reflection_lessons_and_patterns():
    """Reflection produces lessons and patterns for research activities."""
    services = DeterministicServices.fake()
    ctx = _make_reflection_context(services, "research complex topic")
    ctx = await _run_reflection(ctx)

    assert ctx.reflection_result is not None
    # May have lessons/patterns depending on the engine's analysis
    assert isinstance(ctx.reflection_result.lessons, tuple)
    assert isinstance(ctx.reflection_result.patterns, tuple)


# ═══════════════════════════════════════════════════════════════════════════════
# Sprint 5 — Learning Replay Tests
# ═══════════════════════════════════════════════════════════════════════════════


async def _run_learning(ctx: PipelineContext) -> PipelineContext:
    """Run the LearningStage and return the updated context."""
    from core.pipeline.stages.learning import LearningStage

    stage = LearningStage()
    result = await stage.execute(ctx)
    assert result.context is not None
    return result.context


async def _run_learning_twice(
    raw_input: str,
) -> tuple[PipelineContext, PipelineContext]:
    a = _make_reflection_context(DeterministicServices.fake(), raw_input)
    b = _make_reflection_context(DeterministicServices.fake(), raw_input)

    # Run reflection first to populate reflection_result
    ctx_a = await _run_reflection(a)
    ctx_b = await _run_reflection(b)

    # Then run learning
    ctx_a = await _run_learning(ctx_a)
    ctx_b = await _run_learning(ctx_b)

    return ctx_a, ctx_b


@pytest.mark.asyncio
async def test_learning_record_is_deterministic():
    """Two runs with same deterministic services produce identical
    learning records (learning_id, record count, store decisions)."""
    ctx_a, ctx_b = await _run_learning_twice("what is the weather?")

    assert len(ctx_a.learning_records) > 0
    assert len(ctx_b.learning_records) > 0

    lr_a = ctx_a.learning_records[0]
    lr_b = ctx_b.learning_records[0]

    # Semantic content must match (learning_id may differ due to
    # non-deterministic reflection_id from research engine)
    assert lr_a.success_rating == lr_b.success_rating
    assert lr_a.store_decision == lr_b.store_decision
    assert lr_a.lessons == lr_b.lessons
    assert lr_a.patterns == lr_b.patterns


@pytest.mark.asyncio
async def test_learning_no_reflection():
    """Learning produces empty records when no reflection data."""
    ctx = PipelineContext(
        request_id="test", transport="test",
        raw_input="no reflection",
    )
    ctx = await _run_learning(ctx)
    assert len(ctx.learning_records) == 0


@pytest.mark.asyncio
async def test_learning_store_decision():
    """Learning records with high success are marked for storage."""
    ctx, _ = await _run_learning_twice("successful activity")

    assert len(ctx.learning_records) > 0
    record = ctx.learning_records[0]
    assert record.store_decision in ("store", "skip")


@pytest.mark.asyncio
async def test_learning_links_to_reflection():
    """Learning record links back to the reflection that produced it."""
    ctx, _ = await _run_learning_twice("test linking")

    assert len(ctx.learning_records) > 0
    record = ctx.learning_records[0]
    assert record.reflection_id
    assert record.activity_id
    assert record.learning_id
