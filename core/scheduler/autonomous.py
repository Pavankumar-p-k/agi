"""AutonomousScheduler — thin bridge from opportunity discovery to activity execution.

Phase 8.4: connects the existing OpportunityDiscoveryEngine + DecisionEngine
to the scheduler queue, so that detected improvement opportunities are
automatically submitted as executable activities.

Architecture:
    OpportunityDiscoveryEngine (core/opportunity/engine.py)
        │
        ▼
    AutonomousScheduler (this file)
        │
        ├── DecisionEngine (gate: EV, risk, confidence thresholds)
        │
        ▼
    SchedulerQueue.submit()
        │
        ▼
    Worker Pool (via registered executor)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from core.scheduler.models import ScheduledActivity

if TYPE_CHECKING:
    from core.opportunity.engine import OpportunityDiscoveryEngine
    from core.opportunity.models import Opportunity
    from core.scheduler.decision import DecisionEngine
    from core.scheduler.queue import SchedulerQueue

logger = logging.getLogger(__name__)

# ── Default thresholds for auto-submission ───────────────────────────────────

DEFAULT_MIN_EV = 0.15       # minimum expected_value to auto-submit
DEFAULT_MIN_CONFIDENCE = 0.20  # minimum confidence in prediction
DEFAULT_MAX_RISK = 0.80     # maximum acceptable risk
DEFAULT_MAX_PER_CYCLE = 5   # max new activities per run_cycle


@dataclass
class OpportunityActivity:
    """Bridge record: a discovered opportunity converted to a scheduler activity.

    Keeps the lineage from discovery through execution.
    """
    opportunity_id: str
    target_system: str
    description: str
    source: str
    source_score: float
    decision_ev: float
    decision_confidence: float
    decision_risk: float
    activity_id: str = ""
    submitted: bool = False


class AutonomousScheduler:
    """Periodic bridge from opportunity discovery to scheduler queue.

    Usage:
        bridge = AutonomousScheduler(
            engine=OpportunityDiscoveryEngine(),
            decision=DecisionEngine(intelligence=...),
            queue=scheduler.queue,
        )
        result = bridge.run_cycle()  # discover, evaluate, submit
    """

    def __init__(
        self,
        engine: OpportunityDiscoveryEngine | None = None,
        decision: DecisionEngine | None = None,
        queue: SchedulerQueue | None = None,
        min_ev: float = DEFAULT_MIN_EV,
        min_confidence: float = DEFAULT_MIN_CONFIDENCE,
        max_risk: float = DEFAULT_MAX_RISK,
        max_per_cycle: int = DEFAULT_MAX_PER_CYCLE,
    ):
        self._engine = engine
        self._decision = decision
        self._queue = queue
        self._min_ev = min_ev
        self._min_confidence = min_confidence
        self._max_risk = max_risk
        self._max_per_cycle = max_per_cycle

        # Track submitted opportunities to avoid duplicates
        self._submitted_ids: set[str] = set()

    def run_cycle(self, **discovery_kwargs: Any) -> dict[str, Any]:
        """Full pipeline: discover → evaluate → filter → submit.

        Args:
            **discovery_kwargs: Passed through to
                OpportunityDiscoveryEngine.discover_all().

        Returns:
            Dict with cycle_id, discovered_count, submitted_count,
            rejected_count, and list of submitted activities.
        """
        results: dict[str, Any] = {
            "discovered": 0,
            "evaluated": 0,
            "submitted": 0,
            "rejected": 0,
            "submitted_activities": [],
            "rejected_reasons": [],
        }

        # 1. Discover opportunities
        opportunities = self._discover_opportunities(**discovery_kwargs)
        results["discovered"] = len(opportunities)

        # 2. Evaluate and submit
        for opp in opportunities:
            if results["submitted"] >= self._max_per_cycle:
                break

            bridge = self._evaluate_opportunity(opp)
            results["evaluated"] += 1

            if bridge is None:
                continue

            if self._should_submit(bridge):
                act = self._submit_activity(opp)
                if act:
                    bridge.submitted = True
                    bridge.activity_id = act.activity_id
                    self._submitted_ids.add(opp.id)
                    results["submitted"] += 1
                    results["submitted_activities"].append({
                        "activity_id": act.activity_id,
                        "opportunity_id": opp.id,
                        "goal": act.goal,
                        "node_type": act.node_type,
                    })
                    logger.info("AutonomousScheduler: submitted %s as %s (%s)",
                                opp.id, act.activity_id, act.goal[:60])
            else:
                results["rejected"] += 1
                results["rejected_reasons"].append({
                    "opportunity_id": opp.id,
                    "target_system": opp.target_system,
                    "reason": self._rejection_reason(bridge),
                })

        return results

    # ── Internal pipeline ───────────────────────────────────────────────

    def _discover_opportunities(self, **kwargs: Any) -> list[Opportunity]:
        """Run discovery, returning OPEN opportunities not yet submitted."""
        if not self._engine:
            logger.debug("AutonomousScheduler: no engine, skipping discovery")
            return []
        try:
            all_opps = self._engine.discover_all(**kwargs)
        except Exception as e:
            logger.warning("AutonomousScheduler: discovery failed: %s", e)
            return []

        # Only OPEN opportunities that haven't been submitted yet
        return [o for o in all_opps
                if o.status.value == "open" and o.id not in self._submitted_ids]

    def _evaluate_opportunity(
        self, opp: Opportunity,
    ) -> OpportunityActivity | None:
        """Run a discovered opportunity through the DecisionEngine.

        Returns an OpportunityActivity with decision metrics, or None if
        the decision engine is unavailable.
        """
        from core.scheduler.decision import DecisionEngine as _DE

        # Build a synthetic ScheduledActivity to run through DecisionEngine
        synth = ScheduledActivity(
            activity_id=f"_eval_{opp.id}",
            node_type="opportunity",
            goal=f"Research: {opp.improvement_description[:100]} for {opp.target_system}",
            priority=self._score_to_priority(opp.opportunity_score),
        )

        ev = opp.opportunity_score
        confidence = opp.confidence
        risk = 1.0 - opp.success_probability

        if self._decision:
            try:
                est = self._decision.estimate(synth)
                # Use decision engine if it has signal; fall back to
                # opportunity's own scoring when the engine has no data
                if est.confidence >= opp.confidence:
                    ev = est.expected_value
                    confidence = est.confidence
                    risk = est.risk
            except Exception as e:
                logger.debug("AutonomousScheduler: decision failed: %s", e)

        return OpportunityActivity(
            opportunity_id=opp.id,
            target_system=opp.target_system,
            description=opp.improvement_description,
            source=opp.source.value if hasattr(opp.source, "value") else str(opp.source),
            source_score=opp.opportunity_score,
            decision_ev=ev,
            decision_confidence=confidence,
            decision_risk=risk,
        )

    def _should_submit(self, bridge: OpportunityActivity) -> bool:
        """Apply threshold gates before auto-submission."""
        if bridge.decision_ev < self._min_ev:
            return False
        if bridge.decision_confidence < self._min_confidence:
            return False
        if bridge.decision_risk > self._max_risk:
            return False
        return True

    def _rejection_reason(self, bridge: OpportunityActivity) -> str:
        """Explain why an opportunity was rejected."""
        reasons = []
        if bridge.decision_ev < self._min_ev:
            reasons.append(f"EV={bridge.decision_ev:.3f} < {self._min_ev}")
        if bridge.decision_confidence < self._min_confidence:
            reasons.append(f"confidence={bridge.decision_confidence:.3f} < {self._min_confidence}")
        if bridge.decision_risk > self._max_risk:
            reasons.append(f"risk={bridge.decision_risk:.3f} > {self._max_risk}")
        return "; ".join(reasons) if reasons else "unknown"

    def _submit_activity(self, opp: Opportunity) -> ScheduledActivity | None:
        """Convert an Opportunity to a ScheduledActivity and submit to queue."""
        if not self._queue:
            logger.debug("AutonomousScheduler: no queue, cannot submit")
            return None

        goal = f"Research: {opp.improvement_description[:200]} for {opp.target_system}"
        priority = self._score_to_priority(opp.opportunity_score)

        try:
            act = self._queue.submit(
                activity_id=f"opp_{opp.id}",
                goal=goal,
                priority=priority,
                node_type="opportunity",
                metadata={
                    "source": "autonomous",
                    "opportunity_id": opp.id,
                    "target_system": opp.target_system,
                    "opportunity_score": opp.opportunity_score,
                    "source_type": opp.source.value if hasattr(opp.source, "value") else str(opp.source),
                },
            )
            # Mark the opportunity as in_progress
            try:
                from core.opportunity.store import OpportunityStore
                store = OpportunityStore()
                store.update_opportunity_status(opp.id, "in_progress")
            except Exception:
                pass
            return act
        except Exception as e:
            logger.warning("AutonomousScheduler: submit failed for %s: %s", opp.id, e)
            return None

    @staticmethod
    def _score_to_priority(score: float) -> int:
        """Map a 0.0–1.0 opportunity score to a 0–5 priority level."""
        if score >= 0.8:
            return 5
        if score >= 0.6:
            return 4
        if score >= 0.4:
            return 3
        if score >= 0.2:
            return 2
        return 1
