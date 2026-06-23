"""Phase 7.5 Reasoning Benchmarks — R1 through R5.

Tests the research reasoning pipeline:
  R1 — Belief initialization and evidence addition
  R2 — Belief revision with conflicting evidence
  R3 — Counter-hypothesis generation
  R4 — Challenge resolution
  R5 — End-to-end reasoning loop
"""

from __future__ import annotations

from typing import Any

from core.research.models import Fact
from core.research.reasoning import ReasoningEngine


# ── Sample data ──────────────────────────────────────────────────────────

_FACT_A_SUPPORT = Fact(
    fact_id="f1", source_url="https://techcrunch.com",
    claim="Product Y costs $10 per month.",
    confidence=0.85, category="pricing",
)
_FACT_B_SUPPORT = Fact(
    fact_id="f2", source_url="https://arstechnica.com",
    claim="Product Y premium plan costs $10 per month.",
    confidence=0.80, category="pricing",
)
_FACT_C_CONTRADICT = Fact(
    fact_id="f3", source_url="https://companyx.com",
    claim="Product Y costs $12 per month.",
    confidence=0.90, category="pricing",
)
_FACT_D_UNRELATED = Fact(
    fact_id="f4", source_url="https://blog.com",
    claim="Weather was sunny yesterday.",
    confidence=0.50, category="general",
)
_FACT_E_STRONG_SUPPORT = Fact(
    fact_id="f5", source_url="https://official.com",
    claim="The confirmed price of Product Y is $10 per month.",
    confidence=0.95, category="pricing",
)
_FACT_F_CONTRADICT_2 = Fact(
    fact_id="f6", source_url="https://reviewer.com",
    claim="Product Y pricing starts at $15 per month.",
    confidence=0.70, category="pricing",
)


# ── Benchmarks ──────────────────────────────────────────────────────────


def belief_initialization_benchmark() -> dict[str, Any]:
    """R1 — Belief initialization and evidence addition."""
    engine = ReasoningEngine()
    state = engine.initialize("What does Product Y cost?")

    # Check belief state structure
    has_beliefs = len(state.beliefs) >= 1
    has_topic = state.topic == "What does Product Y cost?"
    has_timestamps = bool(state.created_at) and bool(state.updated_at)

    # Add supporting evidence
    updated = engine.add_evidence(state, [_FACT_A_SUPPORT, _FACT_B_SUPPORT])
    belief_updated = len(updated) >= 1

    # Check confidence increased
    belief = state.beliefs[0] if state.beliefs else None
    confidence_increased = belief is not None and belief.confidence > 0.3

    # Check evidence tracked
    has_evidence = belief is not None and len(belief.evidence) >= 2

    # Check source diversity
    has_sources = belief is not None and belief.source_count() >= 2

    return {
        "benchmark": "R1 — Belief initialization and evidence",
        "pass": (has_beliefs and has_topic and belief_updated
                 and confidence_increased and has_evidence and has_sources),
        "metrics": {
            "belief_count": len(state.beliefs),
            "evidence_per_belief": len(belief.evidence) if belief else 0,
            "confidence": belief.confidence if belief else 0,
            "sources": belief.source_count() if belief else 0,
        },
        "details": {
            "has_beliefs": has_beliefs,
            "has_topic": has_topic,
            "belief_updated": belief_updated,
            "confidence_increased": confidence_increased,
            "has_evidence": has_evidence,
            "has_sources": has_sources,
        },
    }


def belief_revision_benchmark() -> dict[str, Any]:
    """R2 — Belief revision when contradictory evidence arrives."""
    engine = ReasoningEngine()
    state = engine.initialize("What does Product Y cost?")
    belief = state.beliefs[0]

    # Add supporting evidence first
    engine.add_evidence(state, [_FACT_A_SUPPORT, _FACT_B_SUPPORT])
    initial_confidence = belief.confidence
    initial_revisions = len(belief.revisions)

    # Add contradicting evidence
    engine.add_evidence(state, [_FACT_C_CONTRADICT])

    # Check confidence decreased
    confidence_decreased = belief.confidence < initial_confidence

    # Check revision recorded
    has_new_revision = len(belief.revisions) > initial_revisions

    # Check both directions tracked
    has_support = len(belief.supporting_evidence()) >= 1
    has_contradict = len(belief.contradicting_evidence()) >= 1

    # Check status updated to challenged
    is_challenged = belief.status == "revised" or belief.status == "rejected"

    # Verify unrelated fact doesn't affect belief
    engine.add_evidence(state, [_FACT_D_UNRELATED])
    unrelated_ignored = len(belief.evidence) == 3  # Only pricing facts added

    return {
        "benchmark": "R2 — Belief revision",
        "pass": (confidence_decreased and has_new_revision
                 and has_support and has_contradict),
        "metrics": {
            "initial_confidence": round(initial_confidence, 3),
            "revised_confidence": belief.confidence,
            "revisions_count": len(belief.revisions),
            "supporting_count": len(belief.supporting_evidence()),
            "contradicting_count": len(belief.contradicting_evidence()),
        },
        "details": {
            "confidence_decreased": confidence_decreased,
            "has_new_revision": has_new_revision,
            "has_support_and_contradict": has_support and has_contradict,
            "unrelated_ignored": unrelated_ignored,
            "status": belief.status,
        },
    }


def counter_hypothesis_benchmark() -> dict[str, Any]:
    """R3 — Counter-hypothesis generation and evidence collection."""
    engine = ReasoningEngine()
    state = engine.initialize("What does Product Y cost?")
    belief = state.beliefs[0]

    # Add some evidence (not enough for high confidence)
    engine.add_evidence(state, [_FACT_A_SUPPORT])
    initial_conf = belief.confidence

    # Generate challenge
    counter = engine.generate_challenge(state, belief)
    challenge_generated = counter is not None
    has_counter_claim = counter is not None and len(counter.counter_claim) > 10
    has_search_queries = counter is not None and len(counter.search_queries) >= 1
    is_linked = belief.counter_hypothesis_id is not None

    # Resolve challenge with additional confirming evidence
    if counter:
        engine.resolve_challenge(state, counter,
                                  [_FACT_B_SUPPORT, _FACT_E_STRONG_SUPPORT])
        resolved = counter.resolved
        final_conf = belief.confidence
        confidence_grew = final_conf > initial_conf
    else:
        resolved = False
        confidence_grew = False
        final_conf = belief.confidence

    return {
        "benchmark": "R3 — Counter-hypothesis generation",
        "pass": (challenge_generated and has_counter_claim
                 and has_search_queries and is_linked
                 and resolved and confidence_grew),
        "metrics": {
            "challenge_generated": challenge_generated,
            "search_queries": len(counter.search_queries) if counter else 0,
            "initial_confidence": round(initial_conf, 3),
            "final_confidence": round(final_conf, 3),
        },
        "details": {
            "generated": challenge_generated,
            "has_counter_claim": has_counter_claim,
            "has_search_queries": has_search_queries,
            "linked_to_belief": is_linked,
            "challenge_resolved": resolved,
            "confidence_grew": confidence_grew,
        },
    }


def challenge_resolution_benchmark() -> dict[str, Any]:
    """R4 — Resolving challenges with counter-evidence."""
    engine = ReasoningEngine()
    state = engine.initialize("What does Product Y cost?")
    belief = state.beliefs[0]

    # Add supporting evidence
    engine.add_evidence(state, [_FACT_A_SUPPORT])
    pre_challenge_conf = belief.confidence

    # Generate and resolve challenge with contradictory evidence
    counter = engine.generate_challenge(state, belief)
    if counter:
        # Directly add contradictory evidence via normal pipeline
        engine.resolve_challenge(state, counter, [_FACT_C_CONTRADICT])

    post_challenge_conf = belief.confidence
    challenged_reduced = post_challenge_conf < pre_challenge_conf

    # Add strong supporting evidence to recover
    engine.add_evidence(state, [_FACT_E_STRONG_SUPPORT, _FACT_B_SUPPORT])
    final_conf = belief.confidence
    recovered = final_conf > post_challenge_conf

    has_revision_history = len(belief.revisions) >= 3

    return {
        "benchmark": "R4 — Challenge resolution",
        "pass": (challenged_reduced and recovered
                 and has_revision_history),
        "metrics": {
            "pre_challenge": round(pre_challenge_conf, 3),
            "post_challenge": round(post_challenge_conf, 3),
            "final_confidence": round(final_conf, 3),
            "revisions": len(belief.revisions),
        },
        "details": {
            "challenged_reduced_confidence": challenged_reduced,
            "recovered_with_evidence": recovered,
            "has_revision_history": has_revision_history,
            "status": belief.status,
        },
    }


def end_to_end_reasoning_benchmark() -> dict[str, Any]:
    """R5 — Complete reasoning loop: initialize → evidence → challenge → conclusion."""
    engine = ReasoningEngine()

    # Step 1: Initialize
    state = engine.initialize("What is the pricing of Product Y?")
    has_state = len(state.beliefs) >= 1

    # Step 2: Add mixed evidence (one support + one contradict = uncertain)
    engine.add_evidence(state, [
        _FACT_A_SUPPORT, _FACT_C_CONTRADICT,
    ])
    belief = state.beliefs[0]
    has_mixed_evidence = (len(belief.supporting_evidence()) >= 1
                          and len(belief.contradicting_evidence()) >= 1)

    # Step 3: Generate counter-hypothesis
    counter = engine.generate_challenge(state, belief)
    has_challenge = counter is not None

    # Step 4: Resolve with additional strong supporting evidence
    if counter:
        engine.resolve_challenge(state, counter,
                                  [_FACT_E_STRONG_SUPPORT, _FACT_B_SUPPORT])
        challenge_resolved = counter.resolved
    else:
        challenge_resolved = False

    # Step 5: Final confidence
    final_confidence = belief.confidence

    # Step 6: Synthesize conclusion
    conclusion = engine.synthesize_conclusion(state)
    has_findings = len(conclusion.findings) >= 1
    has_confidence = conclusion.overall_confidence > 0
    has_uncertainties = isinstance(conclusion.uncertainties, list)
    has_recommendations = len(conclusion.recommended_actions) >= 1
    has_summary = len(conclusion.summary()) > 20

    ev_summary = conclusion.evidence_summary
    summary_has_fields = all(k in ev_summary for k in [
        "total_beliefs", "total_evidence", "unique_sources", "average_confidence"
    ])

    return {
        "benchmark": "R5 — End-to-end reasoning loop",
        "pass": (has_state and has_mixed_evidence and has_challenge
                 and challenge_resolved and has_findings
                 and has_confidence and has_recommendations
                 and has_summary and summary_has_fields),
        "metrics": {
            "beliefs": len(state.beliefs),
            "evidence": len(belief.evidence),
            "revisions": len(belief.revisions),
            "final_confidence": round(final_confidence, 3),
            "conclusion_confidence": conclusion.overall_confidence,
            "findings": len(conclusion.findings),
            "uncertainties": len(conclusion.uncertainties),
            "recommendations": len(conclusion.recommended_actions),
        },
        "details": {
            "has_state": has_state,
            "has_mixed_evidence": has_mixed_evidence,
            "has_challenge": has_challenge,
            "challenge_resolved": challenge_resolved,
            "has_findings": has_findings,
            "has_confidence": has_confidence,
            "has_recommendations": has_recommendations,
            "has_summary": has_summary,
            "summary_has_fields": summary_has_fields,
            "evidence_summary": ev_summary,
        },
    }


def run_all() -> dict[str, Any]:
    """Run all R1-R5 reasoning benchmarks."""
    results: dict[str, Any] = {
        "phase": "7.5",
        "benchmarks": {},
        "summary": {},
    }

    for name, fn in [
        ("R1", belief_initialization_benchmark),
        ("R2", belief_revision_benchmark),
        ("R3", counter_hypothesis_benchmark),
        ("R4", challenge_resolution_benchmark),
        ("R5", end_to_end_reasoning_benchmark),
    ]:
        try:
            result = fn()
            results["benchmarks"][name] = result
        except Exception as e:
            import traceback
            results["benchmarks"][name] = {
                "benchmark": name,
                "pass": False,
                "error": str(e),
                "traceback": traceback.format_exc(),
            }

    passed = sum(1 for b in results["benchmarks"].values() if b.get("pass"))
    total = len(results["benchmarks"])
    results["summary"] = {
        "passed": passed,
        "total": total,
        "pass_rate": f"{passed}/{total}",
        "status": "PASS" if passed == total else f"{passed}/{total}",
    }

    return results
