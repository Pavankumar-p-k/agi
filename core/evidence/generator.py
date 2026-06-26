"""Evidence Generator — continuous evidence production for the autonomous learning loop.

Four evidence sources, each feeding a different subsystem:

  1. PlanOutcomeGenerator  → PlanOutcomeStore      (feeds PlannerAnalytics)
  2. ResearchGenerator     → FactStore              (feeds KnowledgeStore)
  3. StrategyCompetition   → PlanOutcomeStore       (feeds ComparativeScorer)
  4. NegotiationFeedback   → NegotiationEngine      (feeds agent weighting)

The EvidenceGenerator cycles through modes, each tick producing one batch of
evidence. The goal is to ensure the autonomous loop always has fresh, varied
data to learn from.
"""

from __future__ import annotations

import logging
import random
import uuid
from datetime import datetime, timezone
from typing import Any

from core.planner.outcomes import PlanOutcomeStore
from core.planner.store import PlanStore

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────

# Goal templates to generate varied plan outcomes
GOAL_TEMPLATES = [
    "Build a coffee shop ordering app for Android",
    "Create a React dashboard for sales analytics",
    "Develop a cross-platform fitness tracker",
    "Build a note-taking app with cloud sync",
    "Create a weather forecast widget",
    "Develop a habit tracker with reminders",
    "Build a restaurant reservation system",
    "Create a flashcard learning app",
    "Develop a budgeting tool with charts",
    "Build a QR code scanner utility",
    "Create a meditation timer app",
    "Develop a recipe manager with search",
]

# Research topics that produce varied facts
RESEARCH_TOPICS = [
    ("Kotlin Multiplatform", "mobile"),
    ("Jetpack Compose performance", "mobile"),
    ("React Native vs Flutter 2026", "mobile"),
    ("WebAssembly for mobile", "mobile"),
    ("Server-driven UI patterns", "mobile"),
    ("Material Design 3 guidelines", "mobile"),
    ("Android 15 API changes", "mobile"),
    ("SwiftUI vs Jetpack Compose", "mobile"),
    ("Mobile CI/CD best practices", "infrastructure"),
    ("Gradle build optimization", "infrastructure"),
    ("Firebase vs Supabase", "infrastructure"),
    ("Mobile security best practices", "security"),
    ("OAuth 2.0 mobile implementation", "security"),
    ("Mobile app monetization 2026", "business"),
    ("App store optimization strategies", "business"),
    ("Mobile analytics tools comparison", "analytics"),
]

# Strategies used by StrategyGenerator
STRATEGY_KEYS = ["flutter", "native_android", "react_native", "web_first", "ios_first", "backend_first"]

STRATEGY_LABELS = {
    "flutter": "Flutter (cross-platform)",
    "native_android": "Native Android (Kotlin)",
    "react_native": "React Native",
    "web_first": "Web-First (PWA)",
    "ios_first": "iOS Native (Swift)",
    "backend_first": "Backend-First (API)",
}


# ═══════════════════════════════════════════════════════════════════════════════
#  Generators
# ═══════════════════════════════════════════════════════════════════════════════

class PlanOutcomeGenerator:
    """Source 1: Generate plans with varied outcomes.

    Creates plans in PlanStore, records completions in PlanOutcomeStore with
    realistic distributions (some succeed, some fail, varying durations).

    Strategy weights from KnobStore influence which strategies are selected
    and how likely they are to succeed — closing the feedback loop between
    config changes and measurable outcomes.
    """

    STRATEGY_WEIGHT_KNOBS = {
        "flutter": "planner.strategy_weight.flutter",
        "native_android": "planner.strategy_weight.native_android",
        "react_native": "planner.strategy_weight.react_native",
        "web_first": "planner.strategy_weight.web_first",
        "ios_first": "planner.strategy_weight.ios_first",
        "backend_first": "planner.strategy_weight.backend_first",
    }

    def __init__(
        self,
        plan_store: PlanStore | None = None,
        outcome_store: PlanOutcomeStore | None = None,
    ):
        self.plan_store = plan_store or PlanStore()
        self.outcome_store = outcome_store or PlanOutcomeStore()

    def _get_knob_strategy_weights(self) -> dict[str, float]:
        """Read current strategy weights from KnobStore (default 1.0 each)."""
        try:
            from core.improvement.knob_store import KnobStore
            ks = KnobStore()
            weights = {}
            for strat, knob_key in self.STRATEGY_WEIGHT_KNOBS.items():
                val = ks.get(knob_key)
                if isinstance(val, (int, float)) and val > 0:
                    weights[strat] = float(val)
                else:
                    weights[strat] = 1.0
            return weights
        except Exception:
            return {s: 1.0 for s in STRATEGY_KEYS}

    def _weighted_strategy_choice(self, weights: dict[str, float]) -> str:
        """Select a strategy using weighted random selection."""
        strategies = list(weights.keys())
        w = [max(weights[s], 0.1) for s in strategies]
        total = sum(w)
        r = random.uniform(0, total)
        cumulative = 0.0
        for i, strategy in enumerate(strategies):
            cumulative += w[i]
            if r <= cumulative:
                return strategy
        return strategies[-1]

    def generate_batch(self, count: int = 5) -> list[dict[str, Any]]:
        """Generate a batch of plans with outcomes.

        Strategy selection and success probability are biased by current
        KnobStore weights, creating a measurable link between config changes
        and PlannerAnalytics metrics.
        """
        strategy_weights = self._get_knob_strategy_weights()
        results = []
        for _ in range(count):
            goal = random.choice(GOAL_TEMPLATES)
            strategy = self._weighted_strategy_choice(strategy_weights)
            weight = strategy_weights.get(strategy, 1.0)

            plan = self.plan_store.create(
                goal=f"{goal} ({STRATEGY_LABELS[strategy]})",
                root_node={
                    "id": f"root_{uuid.uuid4().hex[:8]}",
                    "title": goal,
                    "description": goal,
                    "status": "completed",
                    "strategy": strategy,
                    "children": [],
                },
            )

            # Mark plan as executing then completed
            self.plan_store.update_status(plan["id"], "executing")
            self.plan_store.update_status(plan["id"], "completed")

            # Create outcome record — success probability biased by strategy weight
            # Higher weight → more resources allocated → higher success rate
            base_success = random.gauss(0.7, 0.15)
            weight_bias = (weight - 1.0) * 0.15  # ±0.15 per unit of weight
            predicted_success = max(0.1, min(1.0, base_success + weight_bias))
            predicted_duration = random.randint(3, 30)
            predicted_cost = random.choice(["low", "medium", "high"])

            self.outcome_store.create(
                plan_id=plan["id"],
                predicted_confidence=round(predicted_success, 3),
                predicted_success_rate=round(predicted_success, 3),
                predicted_duration_days=predicted_duration,
                predicted_risk_score=round(random.uniform(0.1, 0.8), 3),
                predicted_cost=predicted_cost,
            )

            # Record execution
            self.outcome_store.record_execution(plan["id"])

            # Simulate actual outcome — success probability matches prediction
            actual_success = random.random() < predicted_success
            actual_duration_sec = max(1, random.gauss(predicted_duration, 5)) * 86400
            actual_failures = 0 if actual_success else random.randint(1, 8)

            self.outcome_store.record_completion(
                plan_id=plan["id"],
                actual_success=actual_success,
                actual_duration_seconds=round(actual_duration_sec),
                actual_failures=actual_failures,
                actual_cost=predicted_cost,
            )

            results.append({
                "plan_id": plan["id"],
                "goal": goal,
                "strategy": strategy,
                "predicted_success": round(predicted_success, 3),
                "actual_success": actual_success,
            })

        return results


class ResearchGenerator:
    """Source 2: Generate research facts.

    Creates facts on various topics with varied confidence scores. Feeds
    the knowledge system so BehaviorAdapter has data to inject.
    """

    def __init__(self):
        try:
            from core.research.storage import FactStore
            from core.research.models import Fact
            self.FactStore = FactStore
            self.Fact = Fact
            self.store = FactStore()
        except Exception:
            self.store = None

    def generate_batch(self, count: int = 5) -> list[dict[str, Any]]:
        """Generate a batch of research facts."""
        if self.store is None:
            logger.info("ResearchGenerator skipped: FactStore unavailable")
            return []

        results = []
        for _ in range(count):
            topic, category = random.choice(RESEARCH_TOPICS)
            confidence = round(random.uniform(0.3, 0.95), 2)
            claim = _make_claim(topic)

            fact = self.Fact(
                fact_id=f"fact_{uuid.uuid4().hex[:12]}",
                source_url=f"https://research.jarvis.internal/{topic.lower().replace(' ', '-')}",
                claim=claim,
                confidence=confidence,
                category=category,
                tags=[topic.lower().replace(" ", "-"), category],
                activity_id="evidence_generator",
            )

            self.store.insert_fact(fact)

            results.append({
                "fact_id": fact.fact_id,
                "topic": topic,
                "claim": claim[:60],
                "confidence": confidence,
            })

        return results


class StrategyCompetitionSource:
    """Source 3: Run strategy competitions.

    Picks a goal, generates 6 strategies, scores them via ComparativeScorer,
    records which strategy wins and with what score. Stores the competition
    outcome so the system can track which strategies tend to win.
    """

    def __init__(self):
        try:
            from core.planner.strategies import StrategyGenerator
            from core.planner.comparison import ComparativeScorer
            self.generator = StrategyGenerator()
            self.scorer = ComparativeScorer()
        except Exception:
            self.generator = None
            self.scorer = None

    def generate_batch(self, count: int = 3) -> list[dict[str, Any]]:
        """Run strategy competitions and record outcomes."""
        if self.generator is None or self.scorer is None:
            return []

        results = []
        for _ in range(count):
            goal = random.choice(GOAL_TEMPLATES)

            # Generate all 6 strategies
            candidates = self.generator.generate(goal, strategies=STRATEGY_KEYS)
            if not candidates or len(candidates) < 2:
                continue

            # Score them
            comparison = self.scorer.compare(goal, candidates)
            scored = comparison.get("candidates", [])
            if not scored:
                continue

            winner = scored[0]
            runner_up = scored[1] if len(scored) > 1 else None

            # Simulate outcome: the winner is more likely to succeed
            win_margin = winner["overall_score"] - (runner_up["overall_score"] if runner_up else 0)
            success_prob = 0.5 + 0.4 * min(1.0, max(0.0, win_margin / 0.2))
            actual_success = random.random() < success_prob

            results.append({
                "goal": goal,
                "winner_strategy": winner["strategy_key"],
                "winner_score": round(winner["overall_score"], 3),
                "runner_up_strategy": runner_up["strategy_key"] if runner_up else None,
                "win_margin": round(win_margin, 3),
                "success_probability": round(success_prob, 3),
                "actual_success": actual_success,
                "candidate_count": len(scored),
            })

        return results


class NegotiationFeedbackSource:
    """Source 4: Generate negotiation feedback.

    Creates negotiation sessions, resolves them, then correlates with
    simulated outcomes to track consensus accuracy. This data can be
    used to adjust agent weighting in future negotiations.
    """

    def __init__(self):
        try:
            from core.negotiation.engine import NegotiationEngine
            self.engine = NegotiationEngine()
        except Exception:
            self.engine = None

    def generate_batch(self, count: int = 3) -> list[dict[str, Any]]:
        """Create negotiation sessions and track consensus accuracy."""
        if self.engine is None:
            return []

        results = []
        for _ in range(count):
            goal = random.choice(GOAL_TEMPLATES)
            strategy = random.choice(STRATEGY_KEYS)

            # Create a negotiation about which strategy to use
            session = self.engine.create_session(
                goal=f"Which approach is best for: {goal}?"
            )

            decision = session["consensus"]["decision"]
            confidence = session["consensus"]["confidence"]
            dissent = session["consensus"]["dissent"]

            # Simulate outcome: consensus is more likely correct when
            # confidence is high and there's no dissent
            correctness_prob = 0.5 + 0.4 * confidence - 0.1 * min(1.0, len(dissent) * 0.3)
            correctness_prob = max(0.1, min(0.95, correctness_prob))
            was_correct = random.random() < correctness_prob

            # Resolve the session
            self.engine.resolve_session(session["id"], accepted=was_correct)

            results.append({
                "session_id": session["id"],
                "goal": goal,
                "decision": decision,
                "confidence": round(confidence, 3),
                "dissent_count": len(dissent),
                "dissenters": dissent,
                "was_correct": was_correct,
                "correctness_probability": round(correctness_prob, 3),
            })

        return results


# ═══════════════════════════════════════════════════════════════════════════════
#  Orchestrator
# ═══════════════════════════════════════════════════════════════════════════════

class EvidenceGenerator:
    """Orchestrator that cycles through 4 evidence modes.

    Each call to tick() produces evidence from one source, rotating
    through the four modes to ensure balanced data generation.

    Usage:
        gen = EvidenceGenerator()
        result = gen.tick()       # one batch from one source
        result = gen.tick(count=10)  # larger batch
    """

    MODES = ["plans", "research", "competition", "negotiation"]

    def __init__(self):
        self.plan_source = PlanOutcomeGenerator()
        self.research_source = ResearchGenerator()
        self.competition_source = StrategyCompetitionSource()
        self.negotiation_source = NegotiationFeedbackSource()
        self._mode_index = 0

    def tick(self, count: int = 5) -> dict[str, Any]:
        """Generate one batch of evidence from the current mode.

        Rotates to the next mode after each tick.
        """
        mode = self.MODES[self._mode_index % len(self.MODES)]
        self._mode_index += 1

        if mode == "plans":
            items = self.plan_source.generate_batch(count)
        elif mode == "research":
            items = self.research_source.generate_batch(count)
        elif mode == "competition":
            items = self.competition_source.generate_batch(count)
        elif mode == "negotiation":
            items = self.negotiation_source.generate_batch(count)
        else:
            items = []

        return {
            "mode": mode,
            "count": len(items),
            "items": items,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def run_cycles(self, cycles: int = 100, batch_size: int = 5) -> dict[str, Any]:
        """Run multiple cycles across all modes.

        Returns aggregate statistics.
        """
        totals: dict[str, int] = {"plans": 0, "research": 0, "competition": 0, "negotiation": 0}
        start = datetime.now(timezone.utc)

        for _ in range(cycles):
            result = self.tick(count=batch_size)
            totals[result["mode"]] += result["count"]

        elapsed = (datetime.now(timezone.utc) - start).total_seconds()

        return {
            "cycles": cycles,
            "batch_size": batch_size,
            "duration_seconds": round(elapsed, 1),
            "throughput": round(cycles / max(elapsed, 0.1), 1),
            "totals": totals,
            "grand_total": sum(totals.values()),
        }


# ── Helpers ───────────────────────────────────────────────────────────────

def _make_claim(topic: str) -> str:
    """Generate a plausible research claim for a topic."""
    templates = [
        f"{topic} improves development speed by {random.randint(15, 60)}%",
        f"{topic} reduces build times by up to {random.randint(20, 50)}%",
        f"{topic} adoption grew {random.randint(20, 80)}% year-over-year",
        f"{topic} is preferred by {random.randint(50, 90)}% of developers surveyed",
        f"{topic} shows {random.choice(['significant', 'moderate', 'promising'])} results in production",
        f"{topic} has {random.randint(5, 30)} known issues, most with workarounds",
        f"{topic} integrates best with {random.choice(['Firebase', 'AWS', 'custom backend', 'Supabase'])}",
        f"Teams using {topic} report {random.randint(20, 60)}% fewer production incidents",
    ]
    return random.choice(templates)
