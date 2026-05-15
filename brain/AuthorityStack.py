"""AuthorityStack defines the layered governance pipeline for every request."""
from __future__ import annotations
from typing import Any, Dict
from jarvis_os.runtime.exceptions import GovernanceViolation

from .execution_context import BrainExecutionContext
from .IdentityKernel import IdentityKernel
from .ExecutiveGovernor import ExecutiveGovernor
from .CapabilityMatrix import CapabilityMatrix
from .StrategicDelegator import StrategicDelegator
from .BrainPolicyEngine import BrainPolicyEngine
from .GovernanceValidator import GovernanceValidator
from .WorldStateEngine import WorldStateEngine


class AuthorityStack:
    """Composes the required governance layers into a single authority pipeline."""

    def __init__(self, world_state: WorldStateEngine):
        self.world_state = world_state
        self.identity = IdentityKernel()
        self.capability = CapabilityMatrix()
        self.policy = BrainPolicyEngine()
        self.validator = GovernanceValidator(self.identity, self.policy)
        self.delegator = StrategicDelegator(self.capability, self.policy)
        self.executive = ExecutiveGovernor(
            identity=self.identity,
            capability=self.capability,
            delegator=self.delegator,
            policy=self.policy,
            validator=self.validator,
        )

    async def evaluate(self, context: BrainExecutionContext) -> Dict[str, Any]:
        """Evaluate the request through the full authority stack."""
        intent = await self.executive.interpret_intent(context, self.world_state)
        decision = await self.executive.decide(intent, context)
        self.validator.audit_decision(decision, context)
        return decision

    def validate(self, result: Dict[str, Any], context: BrainExecutionContext) -> bool:
        valid = self.validator.validate_execution(result, context)
        if not valid:
            raise GovernanceViolation("AuthorityStack validation failed.")
        return True
