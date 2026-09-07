"""
Module: core.permission.manager
Central permission manager: resolve, audit, policy profiles, runtime violation.
"""
from __future__ import annotations
from typing import Any, Callable, Optional
from dataclasses import dataclass, field
import logging

from core.permission.models import Decision, Permission, PermissionCategory, RiskLevel, AuditEntry
from core.permission.policy import PolicyEngine, PolicyProfile
from core.permission.audit import PermissionAudit
from core.permission.registry import PermissionRegistry
from core.permission.observer import RuntimeObserver

logger = logging.getLogger(__name__)


@dataclass
class PermissionResult:
    capability_id: str = ""
    required_permissions: list[str] = field(default_factory=list)
    policy: str = ""
    results: dict[str, str] = field(default_factory=dict)
    overall: Decision = Decision.ALLOW
    reason: str = ""

    @property
    def allowed(self) -> bool:
        return self.overall == Decision.ALLOW

    @property
    def denied(self) -> bool:
        return self.overall == Decision.DENY

    @property
    def needs_confirmation(self) -> bool:
        return self.overall == Decision.NEED_CONFIRM

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "required_permissions": self.required_permissions,
            "policy": self.policy,
            "results": self.results,
            "overall": self.overall.value,
            "reason": self.reason,
        }


class PermissionManager:
    def __init__(self, registry: PermissionRegistry | None = None, policy_engine: PolicyEngine | None = None, audit: PermissionAudit | None = None, observer: RuntimeObserver | None = None):
        self.registry = registry or PermissionRegistry()
        self.policy_engine = policy_engine or PolicyEngine()
        self.audit = audit or PermissionAudit()
        self.observer = observer or RuntimeObserver()
        self.registry.register_defaults()

    def resolve(self, capability_id: str) -> PermissionResult:
        required = self.registry.permissions_for_capability(capability_id)
        profile_name = self.policy_engine.active_profile
        results: dict[str, str] = {}
        all_allowed = True
        any_denied = False
        any_need_confirm = False
        deny_reason = ""

        for perm_name in required:
            perm = self.registry.get(perm_name)
            if perm is None:
                decision = Decision.DENY
            else:
                decision = self.policy_engine.evaluate(perm)
            results[perm_name] = decision.value
            if decision == Decision.DENY:
                all_allowed = False
                any_denied = True
                deny_reason = f"Permission '{perm_name}' denied by policy '{profile_name}'"
            elif decision == Decision.NEED_CONFIRM:
                all_allowed = False
                any_need_confirm = True
            self.audit.record(
                permission_name=perm_name,
                decision=decision,
                capability_id=capability_id,
                policy=profile_name,
                reason=f"Policy evaluation: {decision.value}",
            )

        if any_denied:
            overall = Decision.DENY
            reason = deny_reason
        elif any_need_confirm:
            overall = Decision.NEED_CONFIRM
            reason = f"Capability '{capability_id}' requires confirmation under profile '{profile_name}'"
        else:
            overall = Decision.ALLOW
            reason = f"All permissions allowed under profile '{profile_name}'"

        return PermissionResult(
            capability_id=capability_id,
            required_permissions=required,
            policy=profile_name,
            results=results,
            overall=overall,
            reason=reason,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "registry": self.registry.to_dict(),
            "policy_engine": self.policy_engine.to_dict(),
            "audit": self.audit.to_dict(),
        }


permission_manager = PermissionManager()
