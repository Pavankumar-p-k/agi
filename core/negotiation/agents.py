"""Agent providers — each produces an opinion from a different subsystem.

Agents:
  - PlannerAgent: recommends a strategy using ComparativeScorer
  - ResearchAgent: finds relevant facts from ResearchStore
  - RiskAgent: assesses risk using PlanEvidenceEngine
  - ReviewerAgent: checks completeness, identifies gaps
  - ExecutionAgent: estimates feasibility, duration, cost
"""

from __future__ import annotations

import logging
from typing import Any

from core.negotiation.models import AgentOpinion

logger = logging.getLogger(__name__)


class PlannerAgent:
    """Recommends a strategy using comparative scoring."""

    def produce_opinion(self, goal: str) -> AgentOpinion:
        from core.planner.strategies import StrategyGenerator, infer_strategies
        from core.planner.comparison import ComparativeScorer

        strategies = infer_strategies(goal)
        generator = StrategyGenerator()
        candidates = generator.generate(goal, strategies)
        scorer = ComparativeScorer()

        if not candidates:
            return AgentOpinion(
                agent_name="planner",
                position="no_recommendation",
                confidence=0.0,
                reasoning="Could not generate any candidate plans for this goal",
                evidence_sources=[],
            )

        comparison = scorer.compare(goal, candidates)
        recommended = comparison.get("recommended")
        if not recommended:
            return AgentOpinion(
                agent_name="planner",
                position="no_consensus",
                confidence=0.0,
                reasoning="Scorer could not determine a clear recommendation",
            )

        strat_label = recommended.get("strategy_label", recommended.get("strategy_key", "unknown"))
        score = recommended.get("overall_score", 0.0)
        reasoning = recommended.get("reasoning", "")

        evidence = []
        for c in comparison.get("candidates", []):
            evidence.append(f"{c.get('strategy_label', '?')}: score {c.get('overall_score', 0):.2f}")

        return AgentOpinion(
            agent_name="planner",
            position=strat_label,
            confidence=min(1.0, max(0.1, score)),
            reasoning=reasoning[:200] or f"Recommended {strat_label} with score {score:.2f}",
            evidence_sources=evidence,
        )


class ResearchAgent:
    """Finds relevant facts and evidence from ResearchStore."""

    def produce_opinion(self, goal: str) -> AgentOpinion:
        try:
            from core.research.storage import FactStore
            store = FactStore()
            facts = store.get_all_facts()
        except Exception:
            facts = []

        # Filter facts relevant to the goal
        goal_lower = goal.lower()
        relevant = []
        for f in facts:
            content = (getattr(f, 'claim', '') or getattr(f, 'content', '') or '').lower()
            if any(word in content for word in goal_lower.split()[:5]):
                relevant.append(f)

        evidence = []
        for f in relevant[:5]:
            content = (getattr(f, 'claim', '') or getattr(f, 'content', '') or '')
            evidence.append(content[:100])

        if evidence:
            # Try to deduce a position from the evidence
            position = "evidence_supports_current"
            confidence = min(1.0, 0.5 + len(relevant) * 0.05)
            reasoning = f"Found {len(relevant)} relevant research findings"
        else:
            position = "insufficient_evidence"
            confidence = 0.3
            reasoning = "No directly relevant research findings found"

        return AgentOpinion(
            agent_name="research",
            position=position,
            confidence=round(confidence, 2),
            reasoning=reasoning,
            evidence_sources=evidence,
        )


class RiskAgent:
    """Assesses risk using PlanEvidenceEngine."""

    def produce_opinion(self, goal: str) -> AgentOpinion:
        # Use evidence engine patterns to assess generic risk
        from core.planner.evidence import PlanEvidenceEngine

        eng = PlanEvidenceEngine()
        try:
            patterns = eng._get_failure_memory().get_all_patterns()
        except Exception:
            patterns = {}

        # Count matching patterns
        goal_lower = goal.lower()
        matching = []
        for key, pattern in (patterns or {}).items():
            if any(w in key.lower() for w in goal_lower.split()[:5]):
                matching.append(key)

        evidence = []
        for m in matching[:5]:
            evidence.append(f"Pattern: {m}")

        risk_level = len(matching)
        if risk_level >= 3:
            position = "high_risk"
            confidence = 0.85
            reasoning = f"Found {risk_level} matching failure patterns in knowledge base"
        elif risk_level >= 1:
            position = "moderate_risk"
            confidence = 0.6
            reasoning = f"Found {risk_level} matching failure pattern(s)"
        else:
            position = "low_risk"
            confidence = 0.3
            reasoning = "No matching failure patterns found"

        return AgentOpinion(
            agent_name="risk",
            position=position,
            confidence=round(confidence, 2),
            reasoning=reasoning,
            evidence_sources=evidence,
        )


class ReviewerAgent:
    """Checks completeness, identifies gaps in the goal."""

    def produce_opinion(self, goal: str) -> AgentOpinion:
        goal_lower = goal.lower()

        gaps = []
        # Check for common missing elements
        checks = {
            "mobile": ["ios", "android", "mobile"],
            "backend": ["api", "backend", "server", "database"],
            "ui": ["ui", "interface", "design", "frontend"],
            "auth": ["auth", "login", "signup", "user management"],
            "testing": ["test", "testing", "qa"],
            "deployment": ["deploy", "release", "ci/cd", "delivery"],
        }

        present = []
        for category, keywords in checks.items():
            if any(k in goal_lower for k in keywords):
                present.append(category)
            else:
                gaps.append(category)

        evidence = [f"Present: {', '.join(present)}"] if present else []
        if gaps:
            evidence.append(f"Gaps: {', '.join(gaps[:4])}")
            position = "needs_clarification"
            confidence = min(1.0, 0.5 + len(gaps) * 0.1)
            reasoning = f"Missing considerations: {', '.join(gaps[:4])}"
        else:
            position = "goal_complete"
            confidence = 0.9
            reasoning = "Goal covers all common considerations"

        return AgentOpinion(
            agent_name="reviewer",
            position=position,
            confidence=round(confidence, 2),
            reasoning=reasoning,
            evidence_sources=evidence,
        )


class ExecutionAgent:
    """Estimates feasibility, duration, and cost."""

    def produce_opinion(self, goal: str) -> AgentOpinion:
        from core.planner.strategies import StrategyGenerator, infer_strategies
        from core.planner.comparison import ComparativeScorer

        strategies = infer_strategies(goal)
        generator = StrategyGenerator()
        candidates = generator.generate(goal, strategies)

        if not candidates:
            return AgentOpinion(
                agent_name="execution",
                position="unknown",
                confidence=0.0,
                reasoning="Could not estimate feasibility",
            )

        # Average duration and cost across candidates
        durations = [c.get("estimated_duration_days", 10) for c in candidates]
        avg_dur = sum(durations) / max(len(durations), 1)

        if avg_dur <= 7:
            feasibility = "highly_feasible"
            confidence = 0.9
        elif avg_dur <= 21:
            feasibility = "feasible"
            confidence = 0.7
        elif avg_dur <= 60:
            feasibility = "ambitious"
            confidence = 0.5
        else:
            feasibility = "highly_ambitious"
            confidence = 0.3

        costs = [c.get("estimated_cost", "medium") for c in candidates]
        cost_counts = {}
        for c in costs:
            cost_counts[c] = cost_counts.get(c, 0) + 1
        avg_cost = max(cost_counts, key=cost_counts.get) if cost_counts else "medium"

        evidence = [
            f"Avg duration: {avg_dur:.0f} days",
            f"Cost range: {', '.join(sorted(set(costs)))}",
        ]
        reasoning = f"Estimated {avg_dur:.0f}d, predominantly {avg_cost} cost — {feasibility.replace('_', ' ')}"

        return AgentOpinion(
            agent_name="execution",
            position=feasibility,
            confidence=round(confidence, 2),
            reasoning=reasoning,
            evidence_sources=evidence,
        )
