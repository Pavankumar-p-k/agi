"""PolicyEngine — profile-based permission decisions (Gate 7)."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable

from core.permission.models import Decision, PermissionCategory, RiskLevel


class PolicyProfile(str, Enum):
    STRICT = "strict"
    DEVELOPER = "developer"
    AUTONOMOUS = "autonomous"


@dataclass
class PolicyRule:
    max_risk: RiskLevel = RiskLevel.CRITICAL
    require_confirmation: bool = True
    allow_critical: bool = False
    audit_all: bool = True
    block_categories: tuple = ()
    require_confirmation_for_categories: tuple = ()


# profile -> (max allowed risk without confirmation, blocked categories,
#             critical allowed)
_PROFILE_RULES: dict[PolicyProfile, PolicyRule] = {
    PolicyProfile.STRICT: PolicyRule(
        max_risk=RiskLevel.LOW,
        block_categories=(PermissionCategory.DESKTOP,
                          PermissionCategory.SHELL),
        require_confirmation_for_categories=(PermissionCategory.NETWORK,),
        allow_critical=False,
    ),
    PolicyProfile.DEVELOPER: PolicyRule(
        max_risk=RiskLevel.HIGH,
        allow_critical=False,
        require_confirmation_for_categories=(PermissionCategory.DESKTOP,),
    ),
    PolicyProfile.AUTONOMOUS: PolicyRule(
        max_risk=RiskLevel.CRITICAL,
        allow_critical=True,
        require_confirmation=False,
        audit_all=True,
    ),
}


class PolicyEngine:
    def __init__(self, profile: PolicyProfile = PolicyProfile.DEVELOPER) -> None:
        self.active_profile = profile
        self.rule = _PROFILE_RULES[profile]

    def set_profile(self, profile: PolicyProfile | str) -> None:
        if isinstance(profile, str):
            profile = PolicyProfile(profile.lower())
        self.active_profile = profile
        self.rule = _PROFILE_RULES[profile]

    def evaluate(self, permission, profile: PolicyProfile | str = None) -> Decision:
        if profile is not None:
            if isinstance(profile, str):
                profile = PolicyProfile(profile.lower())
        else:
            profile = self.active_profile
        rule = _PROFILE_RULES.get(profile, self.rule)

        category = getattr(permission, "category", PermissionCategory.SYSTEM)
        risk = getattr(permission, "risk", RiskLevel.LOW)

        if category in rule.block_categories:
            return Decision.DENY

        risk_order = [RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH,
                      RiskLevel.CRITICAL]
        if risk == RiskLevel.CRITICAL:
            if not rule.allow_critical:
                return Decision.NEED_CONFIRM
            return Decision.ALLOW

        if rule.require_confirmation and \
                category in rule.require_confirmation_for_categories:
            return Decision.NEED_CONFIRM

        if risk_order.index(risk) > risk_order.index(rule.max_risk):
            return Decision.NEED_CONFIRM
        return Decision.ALLOW


__all__ = ["PolicyEngine", "PolicyProfile", "PolicyRule"]
