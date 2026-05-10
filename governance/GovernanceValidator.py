from __future__ import annotations

from typing import Any, Dict, Optional

from brain.execution_context import BrainExecutionContext
from jarvis_os.runtime.exceptions import GovernanceViolation
from .strict_verification import StrictVerificationEngine, VerificationReport, VerificationVerdict


class GovernanceValidator:
    """
    Canonical governance gate for execution requests.
    Raises `GovernanceViolation` on any policy breach.
    """

    _INJECTION_TOKENS = (
        "ignore previous instructions",
        "bypass governance",
        "disable safety",
        "emulate this",
        "jailbreak",
    )

    def __init__(self) -> None:
        self.last_decision: Optional[Dict[str, Any]] = None

    def validate_execution(
        self,
        result: Dict[str, Any],
        context: Optional[BrainExecutionContext] = None,
    ) -> bool:
        task = str(result.get("task", "")).lower()
        if any(token in task for token in self._INJECTION_TOKENS):
            raise GovernanceViolation("Execution blocked: prompt injection or policy bypass intent detected.")

        if result.get("success") is False and float(result.get("trust_risk", 0.0)) > 0.5:
            raise GovernanceViolation("Execution blocked: trust risk exceeded allowed threshold.")

        self.last_decision = {
            "allowed": True,
            "task": result.get("task", ""),
            "context": context.to_dict() if context else {},
        }
        return True


__all__ = [
    "GovernanceValidator",
    "StrictVerificationEngine",
    "VerificationReport",
    "VerificationVerdict",
]
