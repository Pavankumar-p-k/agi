"""BrainPolicyEngine evaluates policy, safety and trust constraints."""
from __future__ import annotations
from typing import Any, Dict


class BrainPolicyEngine:
    """Policy engine for governing legal, ethical, and safety bounds."""

    def __init__(self):
        pass

    def evaluate(self, intent: Dict[str, Any]) -> Dict[str, Any]:
        if intent.get("risk", 0.0) > 0.8 and intent.get("requires_context", True):
            return {"allowed": False, "reason": "High risk operation without explicit user confirmation.", "severity": 0.9}
        if intent.get("task_type") == "destructive":
            return {"allowed": False, "reason": "Destructive actions are prohibited.", "severity": 1.0}
        if intent.get("emotional_state") == "distressed" and intent.get("urgency", 0.5) < 0.4:
            return {"allowed": True, "reason": "Defer action and prioritize user support.", "severity": 0.4}
        return {"allowed": True, "reason": "Policy cleared.", "severity": 0.1}

    def requires_governance_review(self, intent: Dict[str, Any]) -> bool:
        return intent.get("risk", 0.0) > 0.5 or intent.get("long_term_value", 0.0) > 0.7
