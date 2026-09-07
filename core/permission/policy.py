"""
Module: core.permission.policy
Policy engine for evaluating permission rules against profiles.
"""
from __future__ import annotations
from typing import Any, Callable, Optional
from dataclasses import dataclass, field
from enum import Enum
import logging

from core.permission.models import Decision, RiskLevel, PermissionCategory

logger = logging.getLogger(__name__)


class PolicyMatchMode(Enum):
    EXACT = "exact"
    PREFIX = "prefix"
    WILDCARD = "wildcard"


@dataclass
class PolicyRule:
    permission_pattern: str = "*"
    decision: Decision = Decision.DENY
    risk_ceiling: RiskLevel = RiskLevel.HIGH
    max_risk: RiskLevel = RiskLevel.HIGH
    require_confirmation: bool = False
    allow_critical: bool = False
    audit_all: bool = False
    block_categories: list[str] = field(default_factory=list)
    require_confirmation_for_categories: list[str] = field(default_factory=list)
    conditions: dict[str, Any] = field(default_factory=dict)
    match_mode: PolicyMatchMode = PolicyMatchMode.WILDCARD
    description: str = ""

    def matches(self, permission_name: str) -> bool:
        if self.match_mode == PolicyMatchMode.EXACT:
            return self.permission_pattern == permission_name
        if self.match_mode == PolicyMatchMode.PREFIX:
            return permission_name.startswith(self.permission_pattern)
        if self.permission_pattern == "*":
            return True
        return permission_name == self.permission_pattern

    def evaluate(self, permission_name: str, risk_level: RiskLevel, context: dict[str, Any] | None = None) -> Decision:
        if not self.matches(permission_name):
            return Decision.ALLOW
        risk_order = [RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL]
        if risk_order.index(risk_level) > risk_order.index(self.risk_ceiling):
            return Decision.DENY
        if self.require_confirmation:
            return Decision.NEED_CONFIRM
        if self.conditions:
            ctx = context or {}
            for key, expected in self.conditions.items():
                if ctx.get(key) != expected:
                    return Decision.CONDITIONAL
        return self.decision

    def to_dict(self) -> dict[str, Any]:
        return {
            "permission_pattern": self.permission_pattern,
            "decision": self.decision.value,
            "risk_ceiling": self.risk_ceiling.value,
            "max_risk": self.max_risk.value,
            "require_confirmation": self.require_confirmation,
            "allow_critical": self.allow_critical,
            "audit_all": self.audit_all,
            "block_categories": self.block_categories,
            "require_confirmation_for_categories": self.require_confirmation_for_categories,
            "conditions": self.conditions,
            "match_mode": self.match_mode.value,
            "description": self.description,
        }


class PolicyProfile:
    STRICT: str = "strict"
    DEVELOPER: str = "developer"
    AUTONOMOUS: str = "autonomous"
    DEFAULT: str = "default"

    def __init__(self, name: str = "default", rules: list[PolicyRule] | None = None, default_decision: Decision = Decision.DENY, description: str = ""):
        self.name = name
        self.rules = rules or []
        self.default_decision = default_decision
        self.description = description

    def evaluate(self, permission_name: str, risk_level: RiskLevel, context: dict[str, Any] | None = None) -> Decision:
        for rule in self.rules:
            result = rule.evaluate(permission_name, risk_level, context)
            if result != Decision.ALLOW:
                return result
        return self.default_decision

    def add_rule(self, rule: PolicyRule) -> None:
        self.rules.append(rule)

    def remove_rule(self, permission_pattern: str) -> bool:
        before = len(self.rules)
        self.rules = [r for r in self.rules if r.permission_pattern != permission_pattern]
        return len(self.rules) < before

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "rules": [r.to_dict() for r in self.rules],
            "default_decision": self.default_decision.value,
            "description": self.description,
        }


def _build_strict_profile() -> PolicyProfile:
    return PolicyProfile(
        name=PolicyProfile.STRICT,
        default_decision=Decision.DENY,
        description="Strict profile: denies most actions, requires confirmation for network",
        rules=[
            PolicyRule(
                permission_pattern="desktop.",
                decision=Decision.DENY,
                risk_ceiling=RiskLevel.CRITICAL,
                match_mode=PolicyMatchMode.PREFIX,
                description="Block all desktop actions",
            ),
            PolicyRule(
                permission_pattern="network.",
                decision=Decision.NEED_CONFIRM,
                risk_ceiling=RiskLevel.CRITICAL,
                match_mode=PolicyMatchMode.PREFIX,
                require_confirmation=True,
                description="Require confirmation for network",
            ),
        ],
    )


def _build_developer_profile() -> PolicyProfile:
    return PolicyProfile(
        name=PolicyProfile.DEVELOPER,
        default_decision=Decision.ALLOW,
        description="Developer profile: allows low-risk, needs confirm for critical",
        rules=[
            PolicyRule(
                permission_pattern="desktop.",
                decision=Decision.NEED_CONFIRM,
                risk_ceiling=RiskLevel.CRITICAL,
                match_mode=PolicyMatchMode.PREFIX,
                require_confirmation=True,
                description="Desktop needs confirmation",
            ),
            PolicyRule(
                permission_pattern="filesystem.read",
                decision=Decision.ALLOW,
                risk_ceiling=RiskLevel.CRITICAL,
                match_mode=PolicyMatchMode.EXACT,
                description="Allow filesystem read",
            ),
        ],
    )


def _build_autonomous_profile() -> PolicyProfile:
    return PolicyProfile(
        name=PolicyProfile.AUTONOMOUS,
        default_decision=Decision.ALLOW,
        description="Autonomous profile: allows everything",
        rules=[],
    )


class PolicyEngine:
    def __init__(self):
        self.profiles: dict[str, PolicyProfile] = {
            PolicyProfile.STRICT: _build_strict_profile(),
            PolicyProfile.DEVELOPER: _build_developer_profile(),
            PolicyProfile.AUTONOMOUS: _build_autonomous_profile(),
            PolicyProfile.DEFAULT: PolicyProfile(name=PolicyProfile.DEFAULT),
        }
        self.active_profile: str = PolicyProfile.DEFAULT

    def evaluate(self, permission: Any, profile_name: str | None = None) -> Decision:
        pname = profile_name or self.active_profile
        profile = self.profiles.get(pname)
        if profile is None:
            logger.warning("Profile '%s' not found, using default deny", pname)
            return Decision.DENY

        perm_name = ""
        risk_level = RiskLevel.MEDIUM
        if hasattr(permission, "name"):
            perm_name = permission.name
        elif hasattr(permission, "name_or_id"):
            perm_name = permission.name_or_id
        elif isinstance(permission, str):
            perm_name = permission
        if hasattr(permission, "risk"):
            risk_level = permission.risk
        elif hasattr(permission, "risk_level"):
            risk_level = permission.risk_level

        return profile.evaluate(perm_name, risk_level)

    def get_profile(self, name: str) -> PolicyProfile | None:
        return self.profiles.get(name)

    def create_profile(self, name: str, default_decision: Decision = Decision.DENY, description: str = "") -> PolicyProfile:
        profile = PolicyProfile(name=name, default_decision=default_decision, description=description)
        self.profiles[name] = profile
        return profile

    def set_profile(self, profile_name: str | PolicyProfile) -> None:
        if isinstance(profile_name, PolicyProfile):
            self.active_profile = profile_name.name
        else:
            if profile_name in self.profiles:
                self.active_profile = profile_name
            else:
                lower = profile_name.lower()
                for key in self.profiles:
                    if key.lower() == lower:
                        self.active_profile = key
                        return

    def set_active_profile(self, name: str) -> bool:
        if name in self.profiles:
            self.active_profile = name
            return True
        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "profiles": {k: v.to_dict() for k, v in self.profiles.items()},
            "active_profile": self.active_profile,
        }


def policy_engine(**kwargs: Any) -> PolicyEngine:
    return PolicyEngine(**kwargs)
