"""PermissionManager — the single authorization point (Gate 4)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from core.permission.audit import PermissionAudit
from core.permission.models import Decision, Permission, PermissionCategory, RiskLevel
from core.permission.policy import PolicyEngine, PolicyProfile
from core.permission.registry import permission_registry


@dataclass
class PermissionResult:
    permission_id: str
    decision: Decision
    policy: str
    reason: str

    def to_dict(self) -> dict:
        return {
            "permission_id": self.permission_id,
            "decision": self.decision.value,
            "policy": self.policy,
            "reason": self.reason,
        }


@dataclass
class PermissionResolution:
    capability_id: str
    overall: Decision
    required_permissions: tuple
    policy: str
    results: tuple
    reason: str

    @property
    def allowed(self) -> bool:
        return self.overall == Decision.ALLOW

    @property
    def denied(self) -> bool:
        return self.overall == Decision.DENY

    @property
    def needs_confirmation(self) -> bool:
        return self.overall == Decision.NEED_CONFIRM

    def to_dict(self) -> dict:
        return {
            "capability_id": self.capability_id,
            "required_permissions": list(self.required_permissions),
            "policy": self.policy,
            "results": [r.to_dict() for r in self.results],
            "overall": self.overall.value,
            "reason": self.reason,
        }


class PermissionManager:
    def __init__(self, audit: Optional[PermissionAudit] = None,
                 policy: Optional[PolicyEngine] = None) -> None:
        self.audit = audit if audit is not None else PermissionAudit()
        self.policy = policy if policy is not None else PolicyEngine()

    def resolve(self, capability_id: str) -> PermissionResolution:
        perm_ids = permission_registry.permissions_for_capability(capability_id)
        results = []
        decisions: list = []
        profile = self.policy.active_profile

        if not perm_ids:
            resolution = PermissionResolution(
                capability_id=capability_id,
                overall=Decision.ALLOW,
                required_permissions=(),
                policy=str(getattr(profile, "value", profile)),
                results=(),
                reason="capability declares no permissions",
            )
            self.audit.record(capability_id, capability_id, Decision.ALLOW,
                              policy=str(getattr(profile, "value", profile)),
                              reason="no permissions declared")
            return resolution

        for pid in perm_ids:
            # Infer risk/category from the permission id prefix.
            if pid.startswith("desktop."):
                category, risk = PermissionCategory.DESKTOP, RiskLevel.CRITICAL
            elif pid.startswith("system."):
                category, risk = PermissionCategory.SHELL, RiskLevel.CRITICAL
            elif pid.startswith("network."):
                category, risk = PermissionCategory.NETWORK, RiskLevel.LOW
            else:
                category, risk = PermissionCategory.FILESYSTEM, RiskLevel.LOW
            perm = Permission(pid, category=category, risk=risk)
            decision = self.policy.evaluate(perm)
            decisions.append(decision)
            results.append(PermissionResult(
                permission_id=pid, decision=decision,
                policy=str(getattr(profile, "value", profile)),
                reason=f"policy {getattr(profile, 'value', profile)}",
            ))
            self.audit.record(capability_id, pid, decision,
                              policy=str(getattr(profile, "value", profile)),
                              reason="policy evaluation")

        if Decision.DENY in decisions:
            overall = Decision.DENY
        elif Decision.NEED_CONFIRM in decisions:
            overall = Decision.NEED_CONFIRM
        else:
            overall = Decision.ALLOW

        return PermissionResolution(
            capability_id=capability_id,
            overall=overall,
            required_permissions=tuple(perm_ids),
            policy=str(getattr(profile, "value", profile)),
            results=tuple(results),
            reason=f"overall={overall.value} from {len(results)} permissions",
        )


permission_manager = PermissionManager()


__all__ = ["PermissionManager", "PermissionResolution", "PermissionResult",
           "permission_manager"]
