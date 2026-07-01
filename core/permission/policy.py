from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from core.permission.models import Decision, Permission, RiskLevel


class PolicyProfile(StrEnum):
    STRICT = "strict"
    DEVELOPER = "developer"
    AUTONOMOUS = "autonomous"


@dataclass(frozen=True)
class PolicyRule:
    max_risk: RiskLevel = RiskLevel.MEDIUM
    require_confirmation: bool = True
    allow_critical: bool = False
    audit_all: bool = True
    block_categories: frozenset[str] = field(default_factory=frozenset)
    require_confirmation_for_categories: frozenset[str] = field(default_factory=frozenset)


_PROFILES: dict[PolicyProfile, PolicyRule] = {
    PolicyProfile.STRICT: PolicyRule(
        max_risk=RiskLevel.LOW,
        require_confirmation=True,
        allow_critical=False,
        audit_all=True,
        block_categories=frozenset({"desktop", "browser", "system"}),
        require_confirmation_for_categories=frozenset({"network", "process", "clipboard"}),
    ),
    PolicyProfile.DEVELOPER: PolicyRule(
        max_risk=RiskLevel.HIGH,
        require_confirmation=True,
        allow_critical=False,
        audit_all=True,
        block_categories=frozenset(),
        require_confirmation_for_categories=frozenset({"desktop", "system"}),
    ),
    PolicyProfile.AUTONOMOUS: PolicyRule(
        max_risk=RiskLevel.CRITICAL,
        require_confirmation=False,
        allow_critical=True,
        audit_all=True,
        block_categories=frozenset(),
        require_confirmation_for_categories=frozenset(),
    ),
}


class PolicyEngine:
    def __init__(self) -> None:
        self._profiles: dict[PolicyProfile, PolicyRule] = dict(_PROFILES)
        self._active_profile: PolicyProfile = PolicyProfile.DEVELOPER

    @property
    def active_profile(self) -> PolicyProfile:
        return self._active_profile

    def set_profile(self, profile: PolicyProfile | str) -> None:
        if isinstance(profile, str):
            profile = PolicyProfile(profile)
        self._active_profile = profile

    def get_rule(self, profile: PolicyProfile | None = None) -> PolicyRule:
        return self._profiles.get(profile or self._active_profile, _PROFILES[PolicyProfile.DEVELOPER])

    def evaluate(self, perm: Permission, profile: PolicyProfile | None = None) -> Decision:
        rule = self.get_rule(profile)

        if perm.category.value in rule.block_categories:
            return Decision.DENY

        if perm.risk == RiskLevel.CRITICAL and not rule.allow_critical:
            if rule.require_confirmation:
                return Decision.NEED_CONFIRM
            return Decision.DENY

        risk_order = [RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL]
        perm_risk_idx = risk_order.index(perm.risk)
        max_risk_idx = risk_order.index(rule.max_risk)
        if perm_risk_idx > max_risk_idx:
            if rule.require_confirmation:
                return Decision.NEED_CONFIRM
            return Decision.DENY

        if perm.requires_confirmation and rule.require_confirmation:
            return Decision.NEED_CONFIRM

        if perm.category.value in rule.require_confirmation_for_categories:
            return Decision.NEED_CONFIRM

        return Decision.ALLOW


policy_engine = PolicyEngine()
