from core.providers.feedback.models import (
    CalibrationEntry, RoutingDecision, RoutingOutcome, ScoreBreakdown,
)
from core.providers.feedback.recorder import DecisionRecorder
from core.providers.feedback.calibrator import CalibrationEngine
from core.providers.feedback.store import FeedbackStore

feedback_store: FeedbackStore | None = None


def get_feedback_store() -> FeedbackStore:
    global feedback_store
    if feedback_store is None:
        feedback_store = FeedbackStore()
    return feedback_store


def get_decision_recorder() -> DecisionRecorder:
    return DecisionRecorder(store=get_feedback_store())


def get_calibration_engine() -> CalibrationEngine:
    return CalibrationEngine(store=get_feedback_store())
