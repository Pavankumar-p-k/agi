"""SelfGovernanceMonitor observes governance integrity and triggers self-repair."""
from __future__ import annotations
from typing import Any, Dict

from .IdentityKernel import IdentityKernel
from .GovernanceValidator import GovernanceValidator
from .execution_context import BrainExecutionContext


class SelfGovernanceMonitor:
    """Monitors governance health and enforces self-repair."""

    def __init__(self, identity: IdentityKernel, validator: GovernanceValidator):
        self.identity = identity
        self.validator = validator
        self.issue_log: list[Dict[str, Any]] = []

    def observe(self, decision: Dict[str, Any], execution_result: Dict[str, Any], context: BrainExecutionContext) -> None:
        if not decision.get("identity_aligned", True):
            self.issue_log.append({"type": "identity_drift", "detail": decision})
        if execution_result.get("success") is False:
            self.issue_log.append({"type": "execution_failure", "detail": execution_result})
        if execution_result.get("trust_risk", 0.0) > 0.5:
            self.issue_log.append({"type": "trust_risk", "detail": execution_result})

    def repair(self) -> Dict[str, Any]:
        import os
        import json
        issues = self.issue_log.copy()
        if issues:
            os.makedirs("reports", exist_ok=True)
            with open("reports/governance_repair.json", "a", encoding="utf-8") as f:
                f.write(json.dumps(issues) + "\n")
        self.issue_log.clear()
        return {"repaired": len(issues), "issues": issues}

    def has_critical_issues(self) -> bool:
        return any(issue["type"] in {"identity_drift", "trust_risk"} for issue in self.issue_log)
