"""GovernanceValidator verifies decisions and execution against governance rules."""
from __future__ import annotations
from typing import Any, Dict
from jarvis_os.runtime.exceptions import GovernanceViolation

from .IdentityKernel import IdentityKernel
from .BrainPolicyEngine import BrainPolicyEngine
from .execution_context import BrainExecutionContext


class GovernanceValidator:
    """Validates the governance flow and prevents leaks."""

    def __init__(self, identity: IdentityKernel, policy: BrainPolicyEngine):
        self.identity = identity
        self.policy = policy

    def audit_decision(self, decision: Dict[str, Any], context: BrainExecutionContext) -> None:
        if not decision.get("identity_aligned", False):
            raise GovernanceViolation("Governance audit failed: identity alignment missing.")
        if decision.get("trust_risk", 0.0) > 0.75:
            raise GovernanceViolation("Governance audit failed: trust risk too high.")

    def validate_execution(self, result: Dict[str, Any], context: BrainExecutionContext) -> bool:
        if result.get("success") is False and result.get("trust_risk", 0.0) > 0.5:
            raise GovernanceViolation("Execution validation failed: high trust risk on failure.")
        return True

    def inspect_conflict(self, conflict: Dict[str, Any]) -> Dict[str, Any]:
        return self.identity.resolve_conflict(conflict)
