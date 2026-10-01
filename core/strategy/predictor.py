"""Outcome prediction for strategies (Phase 12)."""
from __future__ import annotations

from typing import Dict, List, Optional

from core.strategy.models import EvidenceBundle, Prediction, Strategy, StrategyTag

# Base heuristics keyed by the strategy's dominant tag.
_TAG_PROFILES: Dict[str, Dict[str, float]] = {
    "mvp": {"sp": 0.85, "dur": 8.0, "risk": 0.15, "effort": 5.0, "conf": 0.6},
    "feature_complete": {"sp": 0.7, "dur": 20.0, "risk": 0.4, "effort": 12.0, "conf": 0.55},
    "quality_first": {"sp": 0.82, "dur": 16.0, "risk": 0.25, "effort": 10.0, "conf": 0.6},
    "research_driven": {"sp": 0.7, "dur": 15.0, "risk": 0.35, "effort": 8.0, "conf": 0.5},
    "broad_survey": {"sp": 0.75, "dur": 7.0, "risk": 0.2, "effort": 5.0, "conf": 0.55},
    "deep_dive": {"sp": 0.8, "dur": 12.0, "risk": 0.25, "effort": 8.0, "conf": 0.6},
    "targeted": {"sp": 0.85, "dur": 4.0, "risk": 0.15, "effort": 3.0, "conf": 0.65},
    "safe": {"sp": 0.85, "dur": 4.0, "risk": 0.15, "effort": 3.0, "conf": 0.65},
    "minimal_change": {"sp": 0.85, "dur": 5.0, "risk": 0.15, "effort": 3.0, "conf": 0.65},
    "incremental": {"sp": 0.8, "dur": 10.0, "risk": 0.25, "effort": 6.0, "conf": 0.55},
    "full_refactor": {"sp": 0.7, "dur": 18.0, "risk": 0.45, "effort": 12.0, "conf": 0.5},
    "exploratory": {"sp": 0.6, "dur": 9.0, "risk": 0.35, "effort": 5.0, "conf": 0.45},
    "comparative": {"sp": 0.72, "dur": 8.0, "risk": 0.25, "effort": 5.0, "conf": 0.5},
    "prototype": {"sp": 0.75, "dur": 7.0, "risk": 0.25, "effort": 5.0, "conf": 0.5},
}

_DEFAULT_PROFILE = {"sp": 0.6, "dur": 12.0, "risk": 0.4, "effort": 7.0, "conf": 0.4}

# Priority order when a strategy has several tags.
_TAG_PRIORITY = ["mvp", "minimal_change", "targeted", "quality_first",
                 "feature_complete", "full_refactor", "incremental",
                 "deep_dive", "broad_survey", "research_driven", "safe",
                 "prototype", "comparative", "exploratory"]


def _tag_value(tag) -> str:
    return getattr(tag, "value", tag)


class OutcomePredictor:
    """Deterministic heuristic predictor with optional evidence blending."""

    def __init__(self, belief_integrator=None) -> None:
        self.belief_integrator = belief_integrator

    # ── heuristics ───────────────────────────────────────────────────

    def _profile_for(self, strategy: Strategy) -> Dict[str, float]:
        values = [_tag_value(t) for t in (strategy.tags or [])]
        for tag in _TAG_PRIORITY:
            if tag in values:
                return _TAG_PROFILES[tag]
        for value in values:
            if value in _TAG_PROFILES:
                return _TAG_PROFILES[value]
        return _DEFAULT_PROFILE

    def _heuristic(self, strategy: Strategy) -> Prediction:
        profile = self._profile_for(strategy)
        return Prediction(
            success_probability=profile["sp"],
            estimated_duration_days=profile["dur"],
            estimated_risk=profile["risk"],
            estimated_effort=profile["effort"],
            confidence=profile["conf"],
            evidence_count=0,
        )

    # ── blending ─────────────────────────────────────────────────────

    def _blend(
        self,
        heuristic: Prediction,
        evidence: EvidenceBundle,
        goal: str = "",
    ) -> Prediction:
        if evidence is None or evidence.sample_size <= 0:
            return heuristic.copy()

        weight = min(evidence.sample_size / 20.0, 1.0)
        duration = (
            heuristic.estimated_duration_days * (1 - weight)
            + evidence.avg_duration_days * weight
        )
        success = (
            heuristic.success_probability * (1 - weight)
            + evidence.success_rate * weight
        )
        confidence = (
            heuristic.confidence * (1 - weight)
            + (evidence.confidence or 0.0) * weight
        )

        if self.belief_integrator is not None:
            try:
                confidence = self.belief_integrator.adjust_evidence_bundle_confidence(
                    sample_size=evidence.sample_size + heuristic.evidence_count,
                    domain="",
                )
            except Exception:
                pass

        return Prediction(
            success_probability=success,
            estimated_duration_days=duration,
            estimated_risk=heuristic.estimated_risk,
            estimated_effort=max(
                heuristic.estimated_effort,
                duration * 0.5,
            ),
            confidence=confidence,
            evidence_count=heuristic.evidence_count + evidence.sample_size,
        )

    # ── public API ───────────────────────────────────────────────────

    def predict(
        self,
        strategy: Strategy,
        goal_type: str = "build",
        memory_adapter=None,
        calibrator=None,
    ) -> Prediction:
        prediction = self._heuristic(strategy)

        if memory_adapter is not None:
            try:
                tags = [_tag_value(t) for t in (strategy.tags or [])]
                evidence = memory_adapter.get_evidence(strategy.goal, goal_type, tags)
                prediction = self._blend(prediction, evidence, strategy.goal)
            except Exception:
                pass

        if calibrator is not None:
            try:
                tags = [_tag_value(t) for t in (strategy.tags or [])]
                prediction = calibrator.calibrate(prediction, goal_type, tags)
            except Exception:
                pass

        strategy.prediction = prediction
        return prediction

    def predict_all(
        self,
        strategies: List[Strategy],
        goal_type: str = "build",
        memory_adapter=None,
        calibrator=None,
    ) -> List[Strategy]:
        for strategy in strategies or []:
            self.predict(
                strategy,
                goal_type,
                memory_adapter=memory_adapter,
                calibrator=calibrator,
            )
        return strategies
