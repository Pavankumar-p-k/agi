"""StrategicDelegator chooses the best subsystem based on governance evaluation."""
from __future__ import annotations
from typing import Any, Dict, List

from .CapabilityMatrix import CapabilityMatrix
from .BrainPolicyEngine import BrainPolicyEngine
from .IdentityKernel import IdentityKernel


class StrategicDelegator:
    """Delegates tasks strategically using capability and policy signals."""

    def __init__(self, capability: CapabilityMatrix, policy: BrainPolicyEngine):
        self.capability = capability
        self.policy = policy
        self.identity: IdentityKernel | None = None

    def attach_identity(self, identity: IdentityKernel) -> None:
        self.identity = identity

    def evaluate(self, task: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        task_features = self._extract_task_features(task, context)
        subsystem = self.capability.best_fit(task_features)
        confidence = self._confidence(task_features, subsystem)
        return {
            "subsystem": subsystem,
            "confidence": confidence,
            "task_features": task_features,
            "reason": f"Strategic fit for {subsystem}",
        }

    def _extract_task_features(self, task: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "reasoning_weight": 1.0 if task.get("type") in {"analysis", "planning", "strategy"} else 0.7,
            "execution_weight": 1.0 if task.get("type") in {"action", "automation"} else 0.4,
            "automation_weight": 1.0 if task.get("type") == "automation" else 0.3,
            "context_weight": 1.0 if task.get("requires_context") else 0.5,
            "emotion_weight": 1.0 if task.get("requires_empathy") else 0.2,
            "cost_weight": task.get("cost", 0.5),
            "risk_weight": task.get("risk", 0.3),
        }

    def _confidence(self, task_features: Dict[str, Any], subsystem: str) -> float:
        score = self.capability.score(subsystem, task_features)
        return min(1.0, max(0.0, score))
