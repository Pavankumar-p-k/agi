"""PlanHealthEngine — evaluates plan health from 7 data sources.

Health levels:
  healthy          → everything nominal
  watch            → minor degradation, monitor
  replan_recommended → replan would likely help
  replan_required  → replan necessary before execution

Inputs evaluated:
  1. Confidence score (current vs baseline)
  2. Risk trend (current vs baseline)
  3. Outcome accuracy (if executed)
  4. Workflow failures (scheduled activities that failed)
  5. Schedule delays (activities past due)
  6. Knowledge updates (new knowledge since plan creation)
  7. Research contradictions (new findings that affect plan assumptions)
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from core.planner.outcomes import PlanOutcomeStore
from core.planner.store import PlanStore

logger = logging.getLogger(__name__)


class PlanHealthEngine:
    """Deterministic health evaluation for a single plan."""

    def __init__(self) -> None:
        self._plan_store = PlanStore()
        self._outcome_store = PlanOutcomeStore()

    # ── Public API ──────────────────────────────────────────────────────────

    def evaluate(self, plan_id: str) -> dict[str, Any]:
        """Return full health assessment for a plan."""
        plan = self._plan_store.get(plan_id)
        if plan is None:
            return {"plan_id": plan_id, "status": "unknown", "error": "Plan not found"}

        signals: list[dict] = []
        weights: dict[str, float] = {}
        health_score = 1.0  # start perfect, deduct

        # 1. Confidence assessment
        conf = self._assess_confidence(plan)
        signals.append(conf)
        health_score *= conf["weight_multiplier"]
        weights["confidence"] = conf["weight_multiplier"]

        # 2. Risk trend
        risk = self._assess_risk(plan)
        signals.append(risk)
        health_score *= risk["weight_multiplier"]
        weights["risk"] = risk["weight_multiplier"]

        # 3. Outcome accuracy (if plan has been executed)
        accuracy = self._assess_accuracy(plan_id)
        signals.append(accuracy)
        health_score *= accuracy["weight_multiplier"]
        weights["accuracy"] = accuracy["weight_multiplier"]

        # 4. Workflow failures
        wf_failures = self._assess_workflow_failures(plan_id)
        signals.append(wf_failures)
        health_score *= wf_failures["weight_multiplier"]
        weights["workflow"] = wf_failures["weight_multiplier"]

        # 5. Schedule delays
        delays = self._assess_schedule_delays(plan_id)
        signals.append(delays)
        health_score *= delays["weight_multiplier"]
        weights["delays"] = delays["weight_multiplier"]

        # 6. Knowledge updates
        knowledge = self._assess_knowledge_updates(plan)
        signals.append(knowledge)
        health_score *= knowledge["weight_multiplier"]
        weights["knowledge"] = knowledge["weight_multiplier"]

        # 7. Research contradictions
        research = self._assess_research_contradictions(plan)
        signals.append(research)
        health_score *= research["weight_multiplier"]
        weights["research"] = research["weight_multiplier"]

        health_score = max(0.0, min(1.0, health_score))

        # Determine status
        status = self._classify_health(health_score, signals)

        return {
            "plan_id": plan_id,
            "health_score": round(health_score, 3),
            "status": status,
            "signals": signals,
            "weights": weights,
            "evaluated_at": datetime.utcnow().isoformat(),
        }

    # ── Signal assessors ───────────────────────────────────────────────────

    def _assess_confidence(self, plan: dict) -> dict:
        """Compare current confidence against plan baseline."""
        baseline = plan.get("metadata", {}).get("confidence_at_creation", 0.5)

        from core.planner.evidence import PlanEvidenceEngine
        eng = PlanEvidenceEngine()
        conf_result = eng.get_confidence(plan["id"])
        current_conf = conf_result.get("overall_confidence", baseline) if conf_result else baseline

        drop = baseline - current_conf
        multiplier = 1.0
        if drop >= 0.30:
            multiplier = 0.45
        elif drop >= 0.15:
            multiplier = 0.65
        elif drop >= 0.05:
            multiplier = 0.85

        return {
            "name": "confidence_collapse",
            "label": "Confidence",
            "value": round(current_conf, 3),
            "baseline": round(baseline, 3),
            "delta": round(-drop, 3),
            "weight_multiplier": multiplier,
            "detail": f"{current_conf*100:.0f}% (was {baseline*100:.0f}%)" if drop > 0.01 else f"{current_conf*100:.0f}% (stable)",
        }

    def _assess_risk(self, plan: dict) -> dict:
        """Evaluate risk trend."""
        from core.planner.evidence import PlanEvidenceEngine
        eng = PlanEvidenceEngine()
        try:
            risks_result = eng.get_risks(plan["id"])
        except Exception as e:
            logger.debug("Risk assessment unavailable for %s: %s", plan["id"], e)
            risks_result = None

        if risks_result and risks_result.get("risks"):
            risks = risks_result["risks"]
            critical = sum(1 for r in risks if r.get("severity") == "critical")
            warnings = sum(1 for r in risks if r.get("severity") == "warning")
            multiplier = 1.0
            if critical >= 3:
                multiplier = 0.4
            elif critical >= 1:
                multiplier = 0.6
            elif warnings >= 5:
                multiplier = 0.7
            elif warnings >= 3:
                multiplier = 0.85
            return {
                "name": "risk_trend",
                "label": "Risk Trend",
                "value": critical + warnings,
                "baseline": 0,
                "delta": 0,
                "weight_multiplier": multiplier,
                "detail": f"{len(risks)} risks ({critical} critical, {warnings} warnings)",
            }
        return {
            "name": "risk_trend",
            "label": "Risk Trend",
            "value": 0,
            "baseline": 0,
            "delta": 0,
            "weight_multiplier": 1.0,
            "detail": "No risks identified",
        }

    def _assess_accuracy(self, plan_id: str) -> dict:
        """Check outcome accuracy if plan has been executed."""
        from core.planner.outcomes import get_prediction_accuracy
        try:
            accuracy = get_prediction_accuracy(plan_id)
        except Exception:
            accuracy = None

        if accuracy and accuracy.get("has_actuals"):
            overall = accuracy["overall_accuracy"]
            multiplier = 1.0
            if overall < 0.3:
                multiplier = 0.4
            elif overall < 0.5:
                multiplier = 0.6
            elif overall < 0.7:
                multiplier = 0.8
            return {
                "name": "outcome_accuracy",
                "label": "Outcome Accuracy",
                "value": round(overall, 3),
                "baseline": 1.0,
                "delta": round(overall - 1.0, 3),
                "weight_multiplier": multiplier,
                "detail": f"{overall*100:.0f}% accurate",
            }
        return {
            "name": "outcome_accuracy",
            "label": "Outcome Accuracy",
            "value": None,
            "baseline": 1.0,
            "delta": 0,
            "weight_multiplier": 1.0,
            "detail": "No execution data yet",
        }

    def _assess_workflow_failures(self, plan_id: str) -> dict:
        """Count failed scheduled activities tied to this plan."""
        try:
            from core.scheduler.store import SchedulerStore
            sched = SchedulerStore()
            activities = sched.list_by_metadata("plan_id", plan_id)
            if not activities:
                return {
                    "name": "workflow_failures",
                    "label": "Workflow Failures",
                    "value": 0,
                    "baseline": 0,
                    "delta": 0,
                    "weight_multiplier": 1.0,
                    "detail": "No activities scheduled",
                }
            failed = sum(1 for a in activities if a.status == "failed")
            multiplier = 1.0
            if failed >= 3:
                multiplier = 0.35
            elif failed >= 1:
                multiplier = 0.55
            return {
                "name": "workflow_failures",
                "label": "Workflow Failures",
                "value": failed,
                "baseline": 0,
                "delta": 0,
                "weight_multiplier": multiplier,
                "detail": f"{failed}/{len(activities)} activities failed",
            }
        except Exception:
            return {
                "name": "workflow_failures",
                "label": "Workflow Failures",
                "value": 0,
                "baseline": 0,
                "delta": 0,
                "weight_multiplier": 1.0,
                "detail": "Could not load activities",
            }

    def _assess_schedule_delays(self, plan_id: str) -> dict:
        """Check if scheduled activities are overdue."""
        try:
            from core.scheduler.store import SchedulerStore
            sched = SchedulerStore()
            activities = sched.list_by_metadata("plan_id", plan_id)
            if not activities:
                return {
                    "name": "schedule_delays",
                    "label": "Schedule Delays",
                    "value": 0,
                    "baseline": 0,
                    "delta": 0,
                    "weight_multiplier": 1.0,
                    "detail": "No activities scheduled",
                }
            now = datetime.utcnow()
            pending = [a for a in activities if a.status in ("pending", "running")]
            delayed = 0
            for a in pending:
                if a.created_at:
                    created = datetime.fromisoformat(a.created_at)
                    if (now - created).total_seconds() > 86400:  # >24h
                        delayed += 1
            multiplier = 1.0
            if delayed >= 3:
                multiplier = 0.4
            elif delayed >= 1:
                multiplier = 0.6
            return {
                "name": "schedule_delays",
                "label": "Schedule Delays",
                "value": delayed,
                "baseline": 0,
                "delta": 0,
                "weight_multiplier": multiplier,
                "detail": f"{delayed}/{len(pending)} activities delayed >24h",
            }
        except Exception:
            return {
                "name": "schedule_delays",
                "label": "Schedule Delays",
                "value": 0,
                "baseline": 0,
                "delta": 0,
                "weight_multiplier": 1.0,
                "detail": "Could not check delays",
            }

    def _assess_knowledge_updates(self, plan: dict) -> dict:
        """Detect new knowledge items added since plan creation."""
        try:
            from core.long_term_memory.store import KnowledgeStore
            ks = KnowledgeStore()
            all_knowledge = ks.get_all_knowledge(limit=500)
            plan_created = plan.get("created_at")
            if not plan_created or not all_knowledge:
                return {
                    "name": "knowledge_updates",
                    "label": "Knowledge Updates",
                    "value": 0,
                    "baseline": 0,
                    "delta": 0,
                    "weight_multiplier": 1.0,
                    "detail": "No new knowledge since creation",
                }
            created = datetime.fromisoformat(plan_created.replace("Z", "+00:00"))
            new_items = 0
            for k in all_knowledge:
                if k.last_validated:
                    try:
                        kv = datetime.fromisoformat(k.last_validated.replace("Z", "+00:00"))
                        if kv > created:
                            new_items += 1
                    except Exception:
                        pass
            multiplier = 1.0
            if new_items >= 10:
                multiplier = 0.75
            elif new_items >= 5:
                multiplier = 0.85
            elif new_items >= 2:
                multiplier = 0.95
            return {
                "name": "knowledge_updates",
                "label": "Knowledge Updates",
                "value": new_items,
                "baseline": 0,
                "delta": 0,
                "weight_multiplier": multiplier,
                "detail": f"{new_items} new knowledge items since plan created",
            }
        except Exception:
            return {
                "name": "knowledge_updates",
                "label": "Knowledge Updates",
                "value": 0,
                "baseline": 0,
                "delta": 0,
                "weight_multiplier": 1.0,
                "detail": "Could not check knowledge store",
            }

    def _assess_research_contradictions(self, plan: dict) -> dict:
        """Check for research contradictions that affect this plan."""
        try:
            from core.routes.research import _get_research_store
            store = _get_research_store()
            contradictions = store.fetch_contradictions()
            if not contradictions:
                return {
                    "name": "research_contradictions",
                    "label": "Research Contradictions",
                    "value": 0,
                    "baseline": 0,
                    "delta": 0,
                    "weight_multiplier": 1.0,
                    "detail": "No contradictions found",
                }
            multiplier = 0.8 if len(contradictions) >= 1 else 1.0
            return {
                "name": "research_contradictions",
                "label": "Research Contradictions",
                "value": len(contradictions),
                "baseline": 0,
                "delta": 0,
                "weight_multiplier": multiplier,
                "detail": f"{len(contradictions)} contradictions detected",
            }
        except Exception:
            return {
                "name": "research_contradictions",
                "label": "Research Contradictions",
                "value": 0,
                "baseline": 0,
                "delta": 0,
                "weight_multiplier": 1.0,
                "detail": "Could not check research store",
            }

    # ── Classification ─────────────────────────────────────────────────────

    @staticmethod
    def _classify_health(score: float, signals: list[dict]) -> str:
        """Map health score + signals to a status level."""
        if score >= 0.80:
            return "healthy"
        if score >= 0.55:
            return "watch"
        # Check if any signal forces replan_required
        for s in signals:
            if s["weight_multiplier"] <= 0.45:
                return "replan_required"
        if score >= 0.30:
            return "replan_recommended"
        return "replan_required"
