"""ExecutiveGovernor provides final decision authority and governance oversight."""
from __future__ import annotations
from typing import Any, Dict

from .IdentityKernel import IdentityKernel
from .CapabilityMatrix import CapabilityMatrix
from .StrategicDelegator import StrategicDelegator
from .BrainPolicyEngine import BrainPolicyEngine
from .GovernanceValidator import GovernanceValidator
from .execution_context import BrainExecutionContext
from .WorldStateEngine import WorldStateEngine


class ExecutiveGovernor:
    """Executive governance layer for final authority and strategic arbitration."""

    def __init__(
        self,
        identity: IdentityKernel,
        capability: CapabilityMatrix,
        delegator: StrategicDelegator,
        policy: BrainPolicyEngine,
        validator: GovernanceValidator,
    ):
        self.identity = identity
        self.capability = capability
        self.delegator = delegator
        self.policy = policy
        self.validator = validator
        self.delegator.attach_identity(identity)

    async def interpret_intent(self, context: BrainExecutionContext, world_state: WorldStateEngine) -> Dict[str, Any]:
        world_snapshot = await world_state.snapshot()
        intent = {
            "goal": context.goal,
            "user_id": context.user_id,
            "urgency": context.metadata.get("urgency", 0.5),
            "risk_tolerance": context.metadata.get("risk_tolerance", 0.3),
            "emotional_state": context.metadata.get("emotional_state", "neutral"),
            "type": context.metadata.get("task_type", "general"),
            "requires_context": context.metadata.get("requires_context", True),
            "requires_empathy": context.metadata.get("requires_empathy", False),
            "cost": context.metadata.get("cost", 0.5),
            "risk": context.metadata.get("risk", 0.3),
            "long_term_value": context.metadata.get("long_term_value", 0.5),
            "world_risk": world_snapshot["strategic"]["risk_level"],
            "trust_score": world_snapshot["user"]["trust_score"],
            "active_task_count": len(world_snapshot["tasks"]),
        }
        return intent

    async def decide(self, intent: Dict[str, Any], context: BrainExecutionContext) -> Dict[str, Any]:
        policy_result = self.policy.evaluate(intent)
        if not policy_result["allowed"]:
            return self._deny(intent, policy_result)

        candidate = self.delegator.evaluate(intent, context.to_dict())
        identity_ok = self.identity.check_alignment(context, candidate)
        if not identity_ok:
            return self._override_intent(intent)

        execution_plan = {
            "intent": intent,
            "delegate_to": candidate["subsystem"],
            "confidence": candidate["confidence"],
            "identity_aligned": True,
            "trust_risk": 0.0,
            "user_first": True,
            "strategy": {
                "horizon": context.metadata.get("horizon", "short"),
                "long_term_value": intent["long_term_value"],
                "urgency": intent["urgency"],
            },
        }
        self.validator.audit_decision(execution_plan, context)
        return execution_plan

    def _deny(self, intent: Dict[str, Any], policy: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "intent": intent,
            "allowed": False,
            "reason": policy["reason"],
            "delegate_to": None,
            "identity_aligned": False,
            "trust_risk": 1.0,
        }

    def _override_intent(self, intent: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "intent": intent,
            "allowed": False,
            "reason": "Identity Kernel override — decision conflicts with mission.",
            "delegate_to": None,
            "identity_aligned": False,
            "trust_risk": 1.0,
        }
