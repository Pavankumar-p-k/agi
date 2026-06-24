"""Autonomous Improvement Loop — closes the opportunity→experiment→outcome→calibration cycle.

Lifecycle per opportunity:
  1. Accept → create PlannerExperiment from Opportunity
  2. Start → apply config change to KnobStore
  3. Complete → measure, roll back
  4. Promote/Rollback → keep or discard config
  5. Calibrate → feed outcome to OpportunityCalibrator

The loop is synchronous per opportunity — each step completes before the next.
Run via tick() which picks the next viable opportunity and advances it.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from core.improvement.knob_store import KnobStore
from core.improvement.planner_experiment import PlannerExperimentManager
from core.opportunity.calibration import OpportunityCalibrator
from core.opportunity.models import Opportunity
from core.opportunity.store import OpportunityStore

logger = logging.getLogger(__name__)


class AutonomousLoop:
    """Closes the opportunity-to-outcome lifecycle.

    Ticks are idempotent — each tick picks the highest-scored in_progress
    opportunity that has no running experiment, and advances it one step.
    """

    def __init__(
        self,
        opp_store: OpportunityStore | None = None,
        exp_manager: PlannerExperimentManager | None = None,
        knob_store: KnobStore | None = None,
        calibrator: OpportunityCalibrator | None = None,
    ):
        self.opp_store = opp_store or OpportunityStore()
        self.exp_manager = exp_manager or PlannerExperimentManager()
        self.knob_store = knob_store or KnobStore()
        self.calibrator = calibrator or OpportunityCalibrator(store=self.opp_store)

    # ── Public API ─────────────────────────────────────────────────────

    def tick(self) -> dict[str, Any]:
        """Advance one opportunity one step. Returns result payload."""
        # Find the best candidate: in_progress with no running experiment
        opp = self._next_candidate()
        if opp is None:
            return {"action": "idle", "reason": "no candidate"}

        existing_exp = self._find_experiment(opp.id)
        if existing_exp is None:
            return self._step_create_experiment(opp)
        elif existing_exp.get("status") == "created":
            return self._step_start_experiment(existing_exp, opp)
        elif existing_exp.get("status") == "running":
            return self._step_complete_experiment(existing_exp, opp)
        elif existing_exp.get("status") == "completed":
            return self._step_promote_or_rollback(existing_exp, opp)
        elif existing_exp.get("status") in ("promoted", "rolled_back"):
            return {"action": "idle", "reason": "opportunity_complete", "opp_id": opp.id}

        return {"action": "stuck", "opp_id": opp.id, "exp_status": existing_exp.get("status")}

    def advance_opportunity(self, opp_id: str) -> dict[str, Any]:
        """Advance a specific opportunity one step (for manual trigger)."""
        opp = self.opp_store.get_opportunity(opp_id)
        if opp is None:
            return {"action": "not_found", "opp_id": opp_id}

        existing_exp = self._find_experiment(opp_id)
        if existing_exp is None:
            return self._step_create_experiment(opp)
        elif existing_exp.get("status") == "created":
            return self._step_start_experiment(existing_exp, opp)
        elif existing_exp.get("status") == "running":
            return self._step_complete_experiment(existing_exp, opp)
        elif existing_exp.get("status") == "completed":
            return self._step_promote_or_rollback(existing_exp, opp)
        elif existing_exp.get("status") in ("promoted", "rolled_back"):
            return {"action": "idle", "reason": "opportunity_complete", "opp_id": opp_id}

        return {"action": "stuck", "opp_id": opp_id, "exp_status": existing_exp.get("status")}

    def run_full_cycle(self, opp_id: str) -> list[dict[str, Any]]:
        """Run all lifecycle steps for an opportunity (synchronous)."""
        steps = []
        while True:
            result = self.advance_opportunity(opp_id)
            steps.append(result)
            if result.get("action") in ("idle", "calibrated", "error", "not_found"):
                break
        return steps

    # ── Lifecycle Steps ────────────────────────────────────────────────

    def _step_create_experiment(self, opp: Opportunity) -> dict[str, Any]:
        """Create a PlannerExperiment from an Opportunity."""
        try:
            opportunity_dict = self._opp_to_dict(opp)
            exp = self.exp_manager.create(opportunity_dict, knob_store=self.knob_store)
            logger.info("Created experiment %s for opportunity %s", exp["id"], opp.id)
            return {"action": "created", "opp_id": opp.id, "experiment_id": exp["id"]}
        except Exception as e:
            logger.warning("Failed to create experiment for %s: %s", opp.id, e)
            return {"action": "error", "opp_id": opp.id, "error": str(e)}

    def _step_start_experiment(self, exp: dict, opp: Opportunity) -> dict[str, Any]:
        """Start the experiment by applying config change."""
        try:
            updated = self.exp_manager.start(exp["id"], knob_store=self.knob_store)
            logger.info("Started experiment %s for opportunity %s", exp["id"], opp.id)
            return {"action": "started", "opp_id": opp.id, "experiment_id": exp["id"]}
        except Exception as e:
            logger.warning("Failed to start experiment %s: %s", exp["id"], e)
            return {"action": "error", "opp_id": opp.id, "error": str(e)}

    def _step_complete_experiment(self, exp: dict, opp: Opportunity) -> dict[str, Any]:
        """Complete the experiment: measure, roll back, and calibrate."""
        try:
            result = self.exp_manager.complete(exp["id"], knob_store=self.knob_store)
            logger.info("Completed experiment %s for opportunity %s", exp["id"], opp.id)

            # Immediately calibrate the outcome
            cal = self._calibrate(exp, opp)
            logger.info("Calibrated opportunity %s: improved=%s", opp.id, cal.get("improved"))

            return {
                "action": "completed",
                "opp_id": opp.id,
                "experiment_id": exp["id"],
                "result": result,
                "calibrated": cal,
            }
        except Exception as e:
            logger.warning("Failed to complete experiment %s: %s", exp["id"], e)
            return {"action": "error", "opp_id": opp.id, "error": str(e)}

    def _step_promote_or_rollback(self, exp: dict, opp: Opportunity) -> dict[str, Any]:
        """Promote if experiment improved metrics, otherwise roll back."""
        try:
            result = exp.get("result", {})
            overall = result.get("overall", "") if isinstance(result, dict) else ""
            improved = "improved" in str(overall).lower()

            if improved:
                self.exp_manager.promote(exp["id"], knob_store=self.knob_store)
                action = "promoted"
                self.opp_store.update_opportunity_status(opp.id, "completed")
            else:
                self.exp_manager.rollback(exp["id"], knob_store=self.knob_store)
                action = "rolled_back"
                self.opp_store.update_opportunity_status(opp.id, "rejected")

            logger.info(
                "Opportunity %s: %s (improved=%s)", opp.id, action, improved
            )
            return {"action": action, "opp_id": opp.id, "experiment_id": exp["id"], "improved": improved}
        except Exception as e:
            logger.warning("Failed to promote/rollback %s: %s", exp["id"], e)
            return {"action": "error", "opp_id": opp.id, "error": str(e)}

    # ── Helpers ────────────────────────────────────────────────────────

    def _calibrate(self, exp: dict, opp: Opportunity) -> dict[str, Any]:
        """Record the outcome to the OpportunityCalibrator."""
        try:
            result = exp.get("result", {}) or {}
            overall_improvement = 0.0
            improved = False

            if isinstance(result, dict):
                changes = result.get("changes", {})
                if isinstance(changes, dict):
                    values = [v for v in changes.values() if isinstance(v, (int, float))]
                    if values:
                        overall_improvement = sum(values) / len(values)
                improved = result.get("improved", False) or "improved" in str(result.get("overall", "")).lower()

            self.calibrator.record_outcome(
                opportunity_id=opp.id,
                source=opp.source.value,
                target_system=opp.target_system,
                predicted_score=opp.opportunity_score,
                actual_improvement=overall_improvement,
                actual_success=improved,
            )

            logger.info("Calibrated opportunity %s: improved=%s, delta=%+.3f", opp.id, improved, overall_improvement)
            return {"action": "calibrated", "opp_id": opp.id, "improved": improved, "delta": round(overall_improvement, 3)}
        except Exception as e:
            logger.warning("Failed to calibrate %s: %s", opp.id, e)
            return {"action": "error", "opp_id": opp.id, "error": str(e)}

    # ── Helpers ────────────────────────────────────────────────────────

    def _next_candidate(self) -> Opportunity | None:
        """Find the highest-scored in_progress opportunity without experiment."""
        opportunities = self.opp_store.list_opportunities(status="in_progress")
        if not opportunities:
            return None

        for opp in sorted(opportunities, key=lambda o: o.opportunity_score, reverse=True):
            exp = self._find_experiment(opp.id)
            if exp is None:
                return opp
            if exp.get("status") in ("created", "running", "completed"):
                return opp

        return None

    def _find_experiment(self, opp_id: str) -> dict[str, Any] | None:
        """Find an experiment for this opportunity."""
        experiments = self.exp_manager.list_all()
        for exp in experiments:
            if exp.get("opportunity_id") == opp_id:
                return exp
        return None

    def _opp_to_dict(self, opp: Opportunity) -> dict[str, Any]:
        """Map an Opportunity to the dict format expected by PlannerExperimentManager.create()."""
        return {
            "id": opp.id,
            "description": opp.improvement_description[:200],
            "impact": "high" if opp.opportunity_score > 0.5 else "medium",
            "recommended_change": f"Improve {opp.target_system}: {opp.improvement_description[:80]}",
            "evidence": opp.rationale[:200],
            "expected_gain": opp.opportunity_score,
            "strategy": opp.target_system,
            "type": "strategy_tuning",
        }
