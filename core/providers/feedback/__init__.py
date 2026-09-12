"""Provider decision-feedback engine (X.6).

Components:
- ``models``      — ProviderResult, ScoreBreakdown, RoutingDecision,
                    RoutingOutcome, CalibrationEntry, CalibrationConfig.
- ``store``       — FeedbackStore (SQLite persistence for decisions,
                    outcomes, calibrations).
- ``recorder``    — DecisionRecorder (records decisions + outcomes).
- ``calibrator``  — CalibrationEngine (context-aware adjustments).
"""
from __future__ import annotations

from core.providers.feedback.models import (
    CalibrationConfig,
    CalibrationEntry,
    ProviderResult,
    RoutingDecision,
    RoutingOutcome,
    ScoreBreakdown,
)
from core.providers.feedback.recorder import DecisionRecorder
from core.providers.feedback.calibrator import CalibrationEngine
from core.providers.feedback.store import FeedbackStore

__all__ = [
    "CalibrationConfig",
    "CalibrationEntry",
    "CalibrationEngine",
    "DecisionRecorder",
    "FeedbackStore",
    "ProviderResult",
    "RoutingDecision",
    "RoutingOutcome",
    "ScoreBreakdown",
]
