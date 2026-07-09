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
