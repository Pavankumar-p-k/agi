"""DecisionEvidence — collects evidence from all learning systems.

Pulls data from:
  - WorkflowCalibrationEngine (workflow success/duration/quality)
  - Provider CalibrationEngine (provider quality per capability)
  - Strategy OutcomePredictor (strategy-level prediction)
  - HealthMonitor (system health)
  - ProviderBudgetManager (budget remaining)
  - WorkflowFingerprint (context match)

This is pure data collection. No scoring happens here.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from core.decision.models import CandidateEvidence, EvidenceDimension
from core.workflow.calibration import WorkflowCalibrationEngine, WorkflowPrediction
from core.workflow.learning_models import _FINGERPRINT_FALLBACK_CHAIN

logger = logging.getLogger(__name__)

_DEFAULT_DIMENSION_WEIGHTS: dict[str, float] = {
    "workflow_success": 0.25,
    "provider_quality": 0.20,
    "strategy_alignment": 0.15,
    "system_health": 0.10,
    "budget_viability": 0.10,
    "context_fit": 0.10,
    "confidence": 0.10,
}


class DecisionEvidence:
    """Collects evidence from all learning systems for scoring.

    Each call to ``collect()`` returns one ``CandidateEvidence`` per
    candidate template, populated with all available signals.

    The collector is stateless and thread-safe.
    """

    def __init__(
        self,
        workflow_calibration: WorkflowCalibrationEngine | None = None,
        provider_calibration: Any | None = None,
        strategy_predictor: Any | None = None,
        health_monitor: Any | None = None,
        budget_manager: Any | None = None,
        dimension_weights: dict[str, float] | None = None,
    ):
        self._wf_cal = workflow_calibration
        self._prov_cal = provider_calibration
        self._strat_pred = strategy_predictor
        self._health = health_monitor
        self._budget = budget_manager
        self._weights = dimension_weights or dict(_DEFAULT_DIMENSION_WEIGHTS)

    def collect(
        self,
        template_ids: list[tuple[str, int]],
        task_type: str = "",
        languages: str = "",
        frameworks: str = "",
        project_size: str = "",
        capabilities: list[str] | None = None,
    ) -> list[CandidateEvidence]:
        """Collect evidence for each candidate template.

        Args:
            template_ids: List of (template_id, template_version) pairs.
            task_type, languages, frameworks, project_size: Context for
                calibration fallback chains.
            capabilities: Required capabilities for provider scoring.

        Returns:
            One CandidateEvidence per template, ordered by input order.
        """
        results: list[CandidateEvidence] = []
        now = time.time()

        for tid, tver in template_ids:
            evidence = CandidateEvidence(
                template_id=tid,
                template_version=tver,
                collected_at=now,
            )

            # 1. Workflow calibration
            wf_dim = self._collect_workflow(tid, tver, task_type, languages, frameworks, project_size)
            evidence.dimensions.append(wf_dim)

            # 2. Provider calibration
            prov_dim = self._collect_providers(capabilities, languages, frameworks, project_size)
            evidence.dimensions.append(prov_dim)

            # 3. Strategy alignment
            strat_dim = self._collect_strategy(tid, task_type)
            evidence.dimensions.append(strat_dim)

            # 4. System health
            health_dim = self._collect_health()
            evidence.dimensions.append(health_dim)

            # 5. Budget viability
            budget_dim = self._collect_budget()
            evidence.dimensions.append(budget_dim)

            # 6. Context fit — how well the fingerprint matches available data
            ctx_dim = self._collect_context_fit(tid, tver, task_type, languages, frameworks, project_size)
            evidence.dimensions.append(ctx_dim)

            # 7. Aggregated confidence
            conf_dim = self._collect_confidence(evidence.dimensions)
            evidence.dimensions.append(conf_dim)

            results.append(evidence)

        return results

    # ── Per-dimension collectors ────────────────────────────────────

    def _collect_workflow(
        self,
        template_id: str,
        template_version: int,
        task_type: str,
        languages: str,
        frameworks: str,
        project_size: str,
    ) -> EvidenceDimension:
        """Collect workflow calibration prediction."""
        if self._wf_cal is None:
            return EvidenceDimension(
                name="workflow_success",
                score=0.0, weight=self._weights.get("workflow_success", 0.25),
                reason="Workflow calibration not available",
                confidence=0.0, source="workflow_calibration",
            )

        try:
            pred = self._wf_cal.predict(
                template_id=template_id,
                template_version=template_version,
                task_type=task_type,
                languages=languages,
                frameworks=frameworks,
                project_size=project_size,
            )
            score = pred.expected_success * max(0.1, pred.confidence)
            reason = (
                f"Workflow success: {pred.expected_success:.0%} "
                f"(evidence: {pred.evidence_count})"
            )
            return EvidenceDimension(
                name="workflow_success",
                score=score,
                weight=self._weights.get("workflow_success", 0.25),
                reason=reason,
                confidence=pred.confidence,
                source="workflow_calibration",
            )
        except Exception as e:
            logger.debug("Workflow calibration failed for %s: %s", template_id, e)
            return EvidenceDimension(
                name="workflow_success",
                score=0.0, weight=self._weights.get("workflow_success", 0.25),
                reason=f"Workflow calibration error: {e}",
                confidence=0.0, source="workflow_calibration",
            )

    def _collect_providers(
        self,
        capabilities: list[str] | None,
        language: str,
        framework: str,
        project_size: str,
    ) -> EvidenceDimension:
        """Collect average provider calibration for required capabilities."""
        if self._prov_cal is None or not capabilities:
            return EvidenceDimension(
                name="provider_quality",
                score=0.5, weight=self._weights.get("provider_quality", 0.20),
                reason="Provider calibration not available",
                confidence=0.0, source="provider_calibration",
            )

        try:
            scores: list[float] = []
            confs: list[float] = []
            for cap in capabilities:
                adj, conf = self._prov_cal.get_adjustment_with_confidence(
                    provider_id="", capability=cap,
                    language=language, framework=framework,
                    project_size=project_size,
                )
                # Normalize adjustment [-0.5, +0.5] to score [0.0, 1.0]
                scores.append(0.5 + adj)
                confs.append(conf)

            avg_score = sum(scores) / len(scores) if scores else 0.5
            avg_conf = sum(confs) / len(confs) if confs else 0.0
            avg_score = max(0.0, min(1.0, avg_score))

            return EvidenceDimension(
                name="provider_quality",
                score=avg_score,
                weight=self._weights.get("provider_quality", 0.20),
                reason=f"Provider quality: {avg_score:.0%} across {len(capabilities)} capabilities",
                confidence=avg_conf,
                source="provider_calibration",
            )
        except Exception as e:
            logger.debug("Provider calibration failed: %s", e)
            return EvidenceDimension(
                name="provider_quality",
                score=0.5, weight=self._weights.get("provider_quality", 0.20),
                reason=f"Provider calibration error: {e}",
                confidence=0.0, source="provider_calibration",
            )

    def _collect_strategy(self, template_id: str, goal_type: str) -> EvidenceDimension:
        """Collect strategy-level prediction via StrategyBridge if available.

        Falls back to a neutral default when no strategy predictor is wired.
        """
        if self._strat_pred is None:
            return EvidenceDimension(
                name="strategy_alignment",
                score=0.5, weight=self._weights.get("strategy_alignment", 0.15),
                reason="Strategy predictor not available",
                confidence=0.0, source="strategy",
            )

        try:
            from core.strategy_v2.models import StrategyCandidate

            candidate = StrategyCandidate(
                strategy_id=f"template_{template_id}",
                name=f"Execute {template_id}",
                description=f"Execute template {template_id}",
                proposal_ids=[],
                impact_by_dimension={goal_type or "build": 0.5},
                overall_improvement=0.5,
                risk=0.3,
                implementation_cost=0.3,
                confidence=0.5,
            )

            if hasattr(self._strat_pred, "predict"):
                pred = self._strat_pred.predict(candidate)
                if hasattr(pred, "overall_improvement"):
                    candidate = pred

            score = candidate.overall_improvement * max(0.1, candidate.confidence)

            return EvidenceDimension(
                name="strategy_alignment",
                score=score,
                weight=self._weights.get("strategy_alignment", 0.15),
                reason=(
                    f"Strategy improvement: {candidate.overall_improvement:.0%} "
                    f"risk: {candidate.risk:.0%}"
                ),
                confidence=candidate.confidence,
                source="strategy_v2",
            )
        except Exception as e:
            logger.debug("Strategy prediction failed for %s: %s", template_id, e)
            return EvidenceDimension(
                name="strategy_alignment",
                score=0.5, weight=self._weights.get("strategy_alignment", 0.15),
                reason=f"Strategy prediction error: {e}",
                confidence=0.0, source="strategy_v2",
            )

    def _collect_health(self) -> EvidenceDimension:
        """Collect system health score."""
        if self._health is None:
            return EvidenceDimension(
                name="system_health",
                score=1.0, weight=self._weights.get("system_health", 0.10),
                reason="Health monitor not available",
                confidence=0.0, source="health",
            )

        try:
            if callable(getattr(self._health, "all_ok", None)):
                healthy = self._health.all_ok()
            elif callable(getattr(self._health, "module_status", None)):
                statuses = [
                    getattr(self._health, "module_status")(m)
                    for m in getattr(self._health, "MODULES", [])
                ]
                healthy = all(s == "ok" for s in statuses)
            else:
                healthy = True

            score = 1.0 if healthy else 0.5
            reason = "All systems healthy" if healthy else "Some systems degraded"
            return EvidenceDimension(
                name="system_health",
                score=score,
                weight=self._weights.get("system_health", 0.10),
                reason=reason,
                confidence=1.0 if healthy else 0.5,
                source="health",
            )
        except Exception as e:
            logger.debug("Health check failed: %s", e)
            return EvidenceDimension(
                name="system_health",
                score=1.0, weight=self._weights.get("system_health", 0.10),
                reason=f"Health check error: {e}",
                confidence=0.0, source="health",
            )

    def _collect_budget(self) -> EvidenceDimension:
        """Collect budget viability."""
        if self._budget is None:
            return EvidenceDimension(
                name="budget_viability",
                score=1.0, weight=self._weights.get("budget_viability", 0.10),
                reason="Budget manager not available",
                confidence=0.0, source="budget",
            )

        try:
            if callable(getattr(self._budget, "all_ok", None)):
                ok, msg = self._budget.all_ok()
                score = 1.0 if ok else 0.3
                reason = "Within budget" if ok else f"Budget warning: {msg}"
            else:
                score = 1.0
                reason = "Budget OK"

            return EvidenceDimension(
                name="budget_viability",
                score=score,
                weight=self._weights.get("budget_viability", 0.10),
                reason=reason,
                confidence=score,
                source="budget",
            )
        except Exception as e:
            logger.debug("Budget check failed: %s", e)
            return EvidenceDimension(
                name="budget_viability",
                score=1.0, weight=self._weights.get("budget_viability", 0.10),
                reason=f"Budget check error: {e}",
                confidence=0.0, source="budget",
            )

    def _collect_context_fit(
        self,
        template_id: str,
        template_version: int,
        task_type: str,
        languages: str,
        frameworks: str,
        project_size: str,
    ) -> EvidenceDimension:
        """Measure how well the context fingerprint matches stored data.

        A full match (all 4 fields) → 1.0
        Each fallback level reduces the score.
        """
        if self._wf_cal is None:
            return EvidenceDimension(
                name="context_fit",
                score=0.5, weight=self._weights.get("context_fit", 0.10),
                reason="Workflow calibration not available",
                confidence=0.0, source="context",
            )

        try:
            cal = self._wf_cal._calibration
            from core.workflow.learning_models import _fingerprint_fallback_key as _ffk

            for level_idx, (inc_t, inc_l, inc_f, inc_s) in enumerate(_FINGERPRINT_FALLBACK_CHAIN):
                partial_key = _ffk(
                    task_type=task_type if inc_t else "",
                    languages=languages if inc_l else "",
                    frameworks=frameworks if inc_f else "",
                    project_size=project_size if inc_s else "",
                )
                entry = cal.get_calibration(
                    template_id=template_id,
                    template_version=template_version,
                    fingerprint_key=partial_key,
                )
                if entry is not None:
                    # More specific fallback levels get higher scores
                    fallback_levels = len(_FINGERPRINT_FALLBACK_CHAIN)
                    fit = 1.0 - (level_idx / fallback_levels)
                    level_names = [
                        "exact", "no-size", "task+lang", "task-only", "generic",
                    ]
                    return EvidenceDimension(
                        name="context_fit",
                        score=fit,
                        weight=self._weights.get("context_fit", 0.10),
                        reason=f"Context match at '{level_names[level_idx]}' level",
                        confidence=fit,
                        source="context",
                    )

            return EvidenceDimension(
                name="context_fit",
                score=0.1, weight=self._weights.get("context_fit", 0.10),
                reason="No context calibration data",
                confidence=0.0, source="context",
            )
        except Exception as e:
            return EvidenceDimension(
                name="context_fit",
                score=0.5, weight=self._weights.get("context_fit", 0.10),
                reason=f"Context fit error: {e}",
                confidence=0.0, source="context",
            )

    def _collect_confidence(self, dimensions: list[EvidenceDimension]) -> EvidenceDimension:
        """Aggregated confidence across all dimensions."""
        confs = [d.confidence for d in dimensions if d.confidence > 0]
        avg_conf = sum(confs) / len(confs) if confs else 0.0

        # Penalize if any critical dimension has zero confidence
        critical = {"workflow_success", "provider_quality"}
        zeros = sum(
            1 for d in dimensions
            if d.name in critical and d.confidence <= 0
        )
        penalty = 0.2 * zeros

        score = max(0.0, min(1.0, avg_conf - penalty))
        reason = (
            f"Aggregated confidence: {score:.0%}"
            if zeros == 0
            else f"Aggregated confidence: {score:.0%} ({zeros} critical dimensions missing)"
        )
        return EvidenceDimension(
            name="confidence",
            score=score,
            weight=self._weights.get("confidence", 0.10),
            reason=reason,
            confidence=score,
            source="aggregated",
        )
