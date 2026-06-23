"""OutcomePredictor — predicts outcomes for candidate strategies using historical evidence.

Sources (in priority order):
  1. CalibrationStore — empirical prediction error data (Phase 12.4)
  2. ActivityGraph — similar past goals and their outcomes (Phase 12.5+)
  3. KnowledgeStore — domain patterns and success rates (Phase 12.5+)
  4. ResearchMemory — relevant domain facts (Phase 12.5+)
  5. CollaborationResults — how well collaboration worked (Phase 12.5+)
  6. ExperimentResults — what approaches worked (Phase 12.5+)

The predictor is fully deterministic. All evidence is explicitly queried
and combined via fixed formulas — no hidden LLM reasoning.
"""

from __future__ import annotations

import logging
from typing import Any

from core.belief.integration import BeliefIntegrator
from core.strategy.models import Prediction, Strategy, StrategyTag

logger = logging.getLogger(__name__)

# Keyword-based domain classification for evidence lookup
_DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "android": ["android", "apk", "mobile", "kotlin", "java"],
    "web": ["web", "frontend", "react", "api", "backend", "server"],
    "data": ["data", "analytics", "pipeline", "etl", "database"],
    "ml": ["ml", "model", "training", "inference", "neural"],
    "infra": ["infra", "deploy", "kubernetes", "docker", "cloud"],
}

# Base estimates per goal type (fallback when no historical evidence)
_BASE_ESTIMATES: dict[str, dict[str, float]] = {
    "build": {
        "success_probability": 0.75,
        "duration_days": 14,
        "risk": 0.3,
        "effort": 5,
    },
    "research": {
        "success_probability": 0.85,
        "duration_days": 3,
        "risk": 0.15,
        "effort": 2,
    },
    "refactor": {
        "success_probability": 0.70,
        "duration_days": 7,
        "risk": 0.35,
        "effort": 4,
    },
    "explore": {
        "success_probability": 0.80,
        "duration_days": 2,
        "risk": 0.2,
        "effort": 1,
    },
}

# Strategy tag modifiers (multiplied against base estimates)
_TAG_MODIFIERS: dict[str, dict[str, float]] = {
    "mvp": {
        "success_probability": 1.10,
        "duration_days": 0.6,
        "risk": 0.8,
        "effort": 0.5,
    },
    "feature_complete": {
        "success_probability": 0.90,
        "duration_days": 1.8,
        "risk": 1.2,
        "effort": 1.8,
    },
    "quality_first": {
        "success_probability": 1.05,
        "duration_days": 1.3,
        "risk": 0.7,
        "effort": 1.3,
    },
    "research_driven": {
        "success_probability": 1.15,
        "duration_days": 1.5,
        "risk": 0.6,
        "effort": 1.4,
    },
    "safe": {
        "success_probability": 1.08,
        "duration_days": 1.1,
        "risk": 0.7,
        "effort": 1.1,
    },
    "ambitious": {
        "success_probability": 0.85,
        "duration_days": 1.5,
        "risk": 1.4,
        "effort": 1.5,
    },
    "iterative": {
        "success_probability": 1.05,
        "duration_days": 0.9,
        "risk": 0.85,
        "effort": 1.0,
    },
}


def _detect_domains(goal: str) -> list[str]:
    """Detect domain keywords in the goal."""
    goal_lower = goal.lower()
    found: list[str] = []
    for domain, keywords in _DOMAIN_KEYWORDS.items():
        if any(kw in goal_lower for kw in keywords):
            found.append(domain)
    return found or ["general"]


class OutcomePredictor:
    """Predicts outcomes for strategies using deterministic heuristics.

    Pipeline:
      1. Base estimate × tag modifiers → heuristic
      2. Blend with historical evidence (if MemoryAdapter provided)
      3. Apply calibration (if PredictionCalibrator provided)

    Phase 16.1: Accepts optional BeliefIntegrator. When present, all
    confidence values are computed through the Belief Quality Engine.
    """

    def __init__(self, belief_integrator: BeliefIntegrator | None = None):
        self._evidence_cache: dict[str, list[dict]] = {}
        self._belief = belief_integrator

    def predict(self, strategy: Strategy, goal_type: str | None = None,
                calibrator: Any | None = None,
                memory_adapter: Any | None = None) -> Prediction:
        """Generate a Prediction for a single strategy.

        Pipeline:
          heuristic → [blend with evidence] → [calibrate]
        """
        gtype = goal_type or "build"
        base = _BASE_ESTIMATES.get(gtype, _BASE_ESTIMATES["build"])

        sp_mod = 1.0
        dur_mod = 1.0
        risk_mod = 1.0
        effort_mod = 1.0

        for tag in strategy.tags:
            modifiers = _TAG_MODIFIERS.get(tag.value, {})
            sp_mod *= modifiers.get("success_probability", 1.0)
            dur_mod *= modifiers.get("duration_days", 1.0)
            risk_mod *= modifiers.get("risk", 1.0)
            effort_mod *= modifiers.get("effort", 1.0)

        success_prob = min(base["success_probability"] * sp_mod, 1.0)
        duration = max(base["duration_days"] * dur_mod, 0.5)
        risk = min(base["risk"] * risk_mod, 1.0)
        effort = max(base["effort"] * effort_mod, 0.5)

        domains = _detect_domains(strategy.goal)
        evidence_count = 0
        for domain in domains:
            evidence_count += len(self._evidence_cache.get(domain, []))

        heuristic_conf = min(0.3 + evidence_count * 0.05, 0.95)
        if self._belief is not None:
            confidence = self._belief.adjust_prediction_confidence(
                domain=domains[0] if domains else "general",
                evidence_count=evidence_count,
                current_confidence=heuristic_conf,
            )
        else:
            confidence = heuristic_conf

        prediction = Prediction(
            success_probability=round(success_prob, 3),
            estimated_duration_days=round(duration, 1),
            estimated_risk=round(risk, 3),
            estimated_effort=round(effort, 1),
            confidence=round(confidence, 3),
            evidence_count=evidence_count,
        )

        # Phase 12.5: Blend with historical evidence
        if memory_adapter is not None:
            tags = [t.value for t in strategy.tags]
            evidence = memory_adapter.get_evidence(
                strategy.goal, gtype, tags
            )
            prediction = self._blend(prediction, evidence, strategy.goal)

        # Phase 12.4: Apply calibration
        if calibrator is not None:
            tags = [t.value for t in strategy.tags]
            prediction = calibrator.calibrate(prediction, gtype, tags)

        return prediction

    def predict_all(self, strategies: list[Strategy],
                    goal_type: str | None = None,
                    calibrator: Any | None = None,
                    memory_adapter: Any | None = None) -> list[Strategy]:
        """Predict outcomes for all strategies in-place."""
        for strategy in strategies:
            strategy.prediction = self.predict(
                strategy, goal_type, calibrator, memory_adapter,
            )
        return strategies

    def _blend(self, heuristic: Prediction,
               evidence: Any, goal: str = "") -> Prediction:
        """Blend heuristic prediction with historical evidence.

        The blend weight scales with evidence sample_size:
          weight = min(sample_size / 20, 1.0)

        At 0 samples: pure heuristic.
        At 20+ samples: mostly evidence-driven.
        """
        if evidence.sample_size == 0:
            return heuristic

        weight = min(evidence.sample_size / 20.0, 1.0)

        blended_dur = (
            heuristic.estimated_duration_days * (1.0 - weight)
            + evidence.avg_duration_days * weight
        )
        blended_success = (
            heuristic.success_probability * (1.0 - weight)
            + evidence.success_rate * weight
        )

        total_evidence = heuristic.evidence_count + evidence.sample_size
        if self._belief is not None:
            domains = _detect_domains(goal)
            domain = domains[0] if domains else "general"
            blended_confidence = self._belief.adjust_prediction_confidence(
                domain=domain,
                evidence_count=total_evidence,
                current_confidence=heuristic.confidence + evidence.confidence * weight * 0.5,
            )
        else:
            blended_confidence = min(
                heuristic.confidence + evidence.confidence * weight * 0.5,
                0.95,
            )

        return Prediction(
            success_probability=round(blended_success, 3),
            estimated_duration_days=round(blended_dur, 1),
            estimated_risk=heuristic.estimated_risk,
            estimated_effort=heuristic.estimated_effort,
            confidence=round(blended_confidence, 3),
            evidence_count=total_evidence,
        )
