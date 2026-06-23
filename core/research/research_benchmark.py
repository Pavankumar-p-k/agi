"""Phase 7.4 Research Planning Benchmarks — P1 through P5.

Tests the research planning pipeline:
  P1 — Question decomposition
  P2 — Research plan generation
  P3 — Gap detection
  P4 — Evidence tracking
  P5 — End-to-end research loop
"""

from __future__ import annotations

from typing import Any

from core.research.evidence_tracker import EvidenceTracker
from core.research.gap_detector import GapDetector
from core.research.hypothesis import HypothesisManager
from core.research.planner import (
    GoalStatus,
    PlanStatus,
    ResearchPlanner,
    SearchQuery,
)
from core.research.reflection import ResearchReflection


# ── Sample questions ────────────────────────────────────────────────────

_SIMPLE_QUESTION = "What is the pricing for Company X Product Y?"
_COMPLEX_QUESTION = "Compare Company X vs Company Z pricing and features."
_MULTI_ENTITY = "What are the costs, features, and technology of Product Y?"


# ── Benchmarks ──────────────────────────────────────────────────────────


def question_decomposition_benchmark() -> dict[str, Any]:
    """P1 — Question decomposition into research goals."""
    planner = ResearchPlanner()

    # Simple question
    simple_plan = planner.plan(_SIMPLE_QUESTION)
    simple_goals = len(simple_plan.goals)
    simple_has_goals = simple_goals >= 1

    # Complex question (comparison)
    complex_plan = planner.plan(_COMPLEX_QUESTION)
    complex_goals = len(complex_plan.goals)
    complex_has_goals = complex_goals >= 1

    # Multi-entity question
    multi_plan = planner.plan(_MULTI_ENTITY)
    multi_goals = len(multi_plan.goals)
    multi_has_goals = multi_goals >= 2

    return {
        "benchmark": "P1 — Question decomposition",
        "pass": simple_has_goals and complex_has_goals and multi_has_goals,
        "metrics": {
            "simple_question_goals": simple_goals,
            "complex_question_goals": complex_goals,
            "multi_entity_goals": multi_goals,
        },
        "details": {
            "simple_questions": [g.question[:60] for g in simple_plan.goals],
            "complex_questions": [g.question[:60] for g in complex_plan.goals],
            "multi_entity_questions": [g.question[:60] for g in multi_plan.goals],
        },
    }


def research_plan_generation_benchmark() -> dict[str, Any]:
    """P2 — Research plan structure and search query generation."""
    planner = ResearchPlanner()
    plan = planner.plan("What are the pricing options for Product Y?")

    # Check plan structure
    has_plan_id = bool(plan.plan_id)
    has_question = plan.question == "What are the pricing options for Product Y?"
    has_goals = len(plan.goals) >= 1
    has_status = plan.status == PlanStatus.ACTIVE
    has_max_iterations = plan.max_iterations == 5

    # Check goals have search queries
    goals_with_queries = sum(1 for g in plan.goals if len(g.search_queries) >= 1)
    all_goals_have_queries = goals_with_queries == len(plan.goals)

    # Check summary works
    summary = plan.summary()
    has_summary = len(summary) > 10

    return {
        "benchmark": "P2 — Research plan generation",
        "pass": (has_plan_id and has_question and has_goals
                 and all_goals_have_queries and has_summary),
        "metrics": {
            "goals_count": len(plan.goals),
            "goals_with_queries": goals_with_queries,
            "total_queries": sum(len(g.search_queries) for g in plan.goals),
        },
        "details": {
            "has_plan_id": has_plan_id,
            "has_question": has_question,
            "has_goals": has_goals,
            "has_status": has_status,
            "has_max_iterations": has_max_iterations,
            "all_goals_have_queries": all_goals_have_queries,
            "has_summary": has_summary,
            "goal_details": [g.summary() for g in plan.goals],
        },
    }


def gap_detection_benchmark() -> dict[str, Any]:
    """P3 — Gap detection with varying evidence quality."""
    planner = ResearchPlanner()
    detector = GapDetector()

    # Plan for a pricing question
    plan = planner.plan("What is the pricing for Product Y?")

    # Scenario 1: Insufficient evidence (1 fact, 1 source)
    weak_facts = [
        {"fact_id": "f1", "claim": "Product Y is a cloud service.",
         "confidence": 0.6, "source_url": "https://companyx.com",
         "category": "general"},
    ]
    weak_plan = planner.refine(plan, weak_facts)
    weak_analysis = detector.analyze(weak_plan, weak_facts)
    weak_not_sufficient = not weak_analysis.sufficient

    # Scenario 2: Sufficient evidence (3+ facts, 2+ sources)
    good_facts = [
        {"fact_id": "f1", "claim": "Product Y costs $10 per month.",
         "confidence": 0.8, "source_url": "https://techcrunch.com",
         "category": "pricing"},
        {"fact_id": "f2", "claim": "Product Y offers a premium plan.",
         "confidence": 0.7, "source_url": "https://arstechnica.com",
         "category": "pricing"},
        {"fact_id": "f3", "claim": "Product Y has an enterprise tier.",
         "confidence": 0.9, "source_url": "https://companyx.com",
         "category": "pricing"},
    ]
    good_plan = planner.plan("What is the pricing for Product Y?")
    planner.refine(good_plan, good_facts)
    good_analysis = detector.analyze(good_plan, good_facts)
    good_sufficient = good_analysis.sufficient

    # Scenario 3: Contradictory evidence
    conflict_facts = [
        {"fact_id": "f1", "claim": "Product Y costs $10 per month.",
         "confidence": 0.9, "source_url": "https://techcrunch.com",
         "category": "pricing"},
        {"fact_id": "f2", "claim": "Product Y costs $12 per month.",
         "confidence": 0.9, "source_url": "https://arstechnica.com",
         "category": "pricing"},
    ]
    conflict_plan = planner.plan("What is the pricing for Product Y?")
    planner.refine(conflict_plan, conflict_facts)
    conflict_analysis = detector.analyze(conflict_plan, conflict_facts)
    conflict_detected = len(conflict_analysis.goals_contradicted) > 0

    # Verify recommendation exists
    has_recommendation = bool(weak_analysis.recommendation)

    return {
        "benchmark": "P3 — Gap detection",
        "pass": (weak_not_sufficient and good_sufficient
                 and conflict_detected and has_recommendation),
        "metrics": {
            "weak_confidence": weak_analysis.confidence,
            "good_confidence": good_analysis.confidence,
            "conflict_count": len(conflict_analysis.goals_contradicted),
            "weak_sufficient": weak_analysis.sufficient,
            "good_sufficient": good_analysis.sufficient,
            "conflict_detected": conflict_detected,
        },
        "details": {
            "weak_analysis": weak_analysis.summary(),
            "good_analysis": good_analysis.summary(),
            "conflict_analysis": conflict_analysis.summary(),
        },
    }


def evidence_tracking_benchmark() -> dict[str, Any]:
    """P4 — Evidence-to-goal mapping and coverage tracking."""
    tracker = EvidenceTracker()
    from core.research.models import Fact

    # Register goals
    tracker.register_goal("g1", "What is the pricing for Product Y?")
    tracker.register_goal("g2", "What features does Product Y support?")

    # Link facts to goals
    facts = [
        Fact(fact_id="f1", claim="Product Y costs $10 per month.",
             source_url="https://techcrunch.com", confidence=0.8,
             category="pricing"),
        Fact(fact_id="f2", claim="Product Y costs $12 per month.",
             source_url="https://arstechnica.com", confidence=0.7,
             category="pricing"),
        Fact(fact_id="f3", claim="Product Y supports REST APIs.",
             source_url="https://companyx.com", confidence=0.9,
             category="technical"),
    ]
    tracker.link_fact_to_goal(facts[0], "g1")
    tracker.link_fact_to_goal(facts[1], "g1")
    tracker.link_fact_to_goal(facts[2], "g2")

    # Check goal 1 coverage
    g1_coverage = tracker.get_coverage("g1")
    g1_has_facts = g1_coverage.total_facts >= 2
    g1_has_conf = g1_coverage.average_confidence > 0.5

    # Check goal 2 coverage
    g2_coverage = tracker.get_coverage("g2")
    g2_has_fact = g2_coverage.total_facts >= 1

    # Summarize
    summary = tracker.summarize_coverage()
    has_summary = summary.total_goals == 2
    has_goals_list = len(summary.goals) == 2

    return {
        "benchmark": "P4 — Evidence tracking",
        "pass": (g1_has_facts and g1_has_conf and g2_has_fact
                 and has_summary and has_goals_list),
        "metrics": {
            "goal_1_facts": g1_coverage.total_facts,
            "goal_1_confidence": g1_coverage.average_confidence,
            "goal_2_facts": g2_coverage.total_facts,
            "total_goals": summary.total_goals,
            "covered_goals": summary.covered_goals,
            "overall_confidence": summary.overall_confidence,
        },
        "details": {
            "g1_sufficient": g1_coverage.sufficient,
            "g1_gaps": g1_coverage.gaps,
            "g2_sufficient": g2_coverage.sufficient,
            "g2_gaps": g2_coverage.gaps,
        },
    }


def research_loop_benchmark() -> dict[str, Any]:
    """P5 — End-to-end research loop with planning, gap detection, and reflection."""
    planner = ResearchPlanner()
    detector = GapDetector()
    tracker = EvidenceTracker()
    hypothesis_mgr = HypothesisManager()
    reflection = ResearchReflection()

    # — Step 1: Plan —
    plan = planner.plan("What is the pricing and features of Product Y?")
    plan_created = len(plan.goals) >= 1

    # — Step 2: First pass —
    pass1_facts = [
        {"fact_id": "f1", "claim": "Product Y costs $10 per month.",
         "confidence": 0.8, "source_url": "https://techcrunch.com",
         "category": "pricing"},
        {"fact_id": "f2", "claim": "Product Y supports REST APIs.",
         "confidence": 0.9, "source_url": "https://techcrunch.com",
         "category": "technical"},
    ]
    plan = planner.refine(plan, pass1_facts)
    analysis1 = detector.analyze(plan, pass1_facts)
    gap_detected = not analysis1.sufficient
    follow_up_generated = len(analysis1.follow_up_queries) > 0

    # — Step 3: Second pass with more evidence —
    pass2_facts = [
        {"fact_id": "f3", "claim": "Product Y has a $12 premium tier.",
         "confidence": 0.85, "source_url": "https://arstechnica.com",
         "category": "pricing"},
        {"fact_id": "f4", "claim": "Product Y provides GraphQL support.",
         "confidence": 0.75, "source_url": "https://arstechnica.com",
         "category": "technical"},
        {"fact_id": "f5", "claim": "Product Y enterprise plan costs $10.",
         "confidence": 0.9, "source_url": "https://companyx.com",
         "category": "pricing"},
    ]
    all_facts = pass1_facts + pass2_facts
    plan = planner.refine(plan, all_facts)
    analysis2 = detector.analyze(plan, all_facts)
    multi_iteration_worked = plan.iteration == 2

    # — Step 4: Track evidence —
    from core.research.models import Fact
    fact_objects = [Fact(
        fact_id=f["fact_id"], claim=f["claim"],
        source_url=f["source_url"], confidence=f["confidence"],
        category=f["category"],
    ) for f in all_facts]
    for i, g in enumerate(plan.goals):
        tracker.register_goal(g.goal_id, g.question)
        for f in fact_objects:
            if "pricing" in f.claim.lower() and i == 0:
                tracker.link_fact_to_goal(f, g.goal_id)
            elif "support" in f.claim.lower() and i == 1:
                tracker.link_fact_to_goal(f, g.goal_id)
    coverage = tracker.summarize_coverage()
    tracking_works = coverage.total_goals >= 1

    # — Step 5: Form hypothesis —
    hyp = hypothesis_mgr.create_hypothesis("Product Y costs $10-12 per month")
    for f in fact_objects:
        hypothesis_mgr.add_evidence(hyp.hypothesis_id, f)
    hypothesis_evaluated = hyp.status != "unverified"

    # — Step 6: Reflect —
    plan_summary = planner.get_research_summary(plan)
    ref_result = reflection.analyze(
        activity_id="act_bench_p5",
        question=plan.question,
        plan_summary=plan_summary,
        facts_count=len(all_facts),
        coverage=coverage,
    )
    reflection_works = ref_result.success_rating > 0

    return {
        "benchmark": "P5 — End-to-end research loop",
        "pass": (plan_created and gap_detected and follow_up_generated
                 and multi_iteration_worked and tracking_works
                 and hypothesis_evaluated and reflection_works),
        "metrics": {
            "goals_created": len(plan.goals),
            "iterations": plan.iteration,
            "facts_collected": len(all_facts),
            "gap_detected": gap_detected,
            "follow_up_queries": len(analysis2.follow_up_queries),
            "goal_completion": plan.completion_ratio(),
            "hypothesis_confidence": hyp.confidence,
            "reflection_success": ref_result.success_rating,
        },
        "details": {
            "plan_created": plan_created,
            "gap_detected": gap_detected,
            "follow_up_generated": follow_up_generated,
            "multi_iteration_worked": multi_iteration_worked,
            "tracking_works": tracking_works,
            "hypothesis_evaluated": hypothesis_evaluated,
            "reflection_works": reflection_works,
        },
    }


def run_all() -> dict[str, Any]:
    """Run all P1-P5 benchmarks and return aggregated results."""
    results: dict[str, Any] = {
        "phase": "7.4",
        "benchmarks": {},
        "summary": {},
    }

    for name, fn in [
        ("P1", question_decomposition_benchmark),
        ("P2", research_plan_generation_benchmark),
        ("P3", gap_detection_benchmark),
        ("P4", evidence_tracking_benchmark),
        ("P5", research_loop_benchmark),
    ]:
        try:
            result = fn()
            results["benchmarks"][name] = result
        except Exception as e:
            results["benchmarks"][name] = {
                "benchmark": name,
                "pass": False,
                "error": str(e),
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
