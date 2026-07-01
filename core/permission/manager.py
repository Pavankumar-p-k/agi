from __future__ import annotations

import logging
from typing import Any

from core.permission.audit import PermissionAudit, permission_audit
from core.permission.models import Decision, Permission
from core.permission.policy import PolicyEngine, PolicyProfile, policy_engine
from core.permission.registry import PermissionRegistry, permission_registry

logger = logging.getLogger(__name__)


class PermissionResolution:
    def __init__(
        self,
        capability_id: str,
        required_permissions: frozenset[str],
        policy: str,
        results: dict[str, Decision],
        overall: Decision,
        reason: str,
    ) -> None:
        self.capability_id = capability_id
        self.required_permissions = required_permissions
        self.policy = policy
        self.results = results
        self.overall = overall
        self.reason = reason

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "required_permissions": list(self.required_permissions),
            "policy": self.policy,
            "results": {k: v.value for k, v in self.results.items()},
            "overall": self.overall.value,
            "reason": self.reason,
        }

    @property
    def allowed(self) -> bool:
        return self.overall == Decision.ALLOW

    @property
    def needs_confirmation(self) -> bool:
        return self.overall == Decision.NEED_CONFIRM

    @property
    def denied(self) -> bool:
        return self.overall == Decision.DENY


class PermissionManager:
    def __init__(
        self,
        registry: PermissionRegistry | None = None,
        engine: PolicyEngine | None = None,
        audit: PermissionAudit | None = None,
    ) -> None:
        self._registry = registry or permission_registry
        self._engine = engine or policy_engine
        self._audit = audit or permission_audit

    def resolve(self, capability_id: str, task: dict[str, Any] | None = None) -> PermissionResolution:
        required_perms = self._registry.permissions_for_capability(capability_id)
        profile = self._engine.active_profile

        if not required_perms:
            res = PermissionResolution(
                capability_id=capability_id,
                required_permissions=frozenset(),
                policy=profile.value,
                results={},
                overall=Decision.ALLOW,
                reason=f"No permissions required for capability '{capability_id}'",
            )
            self._audit.record(
                capability_id=capability_id,
                permission_id="(none)",
                decision=Decision.ALLOW,
                policy=profile.value,
                reason=res.reason,
            )
            return res

        results: dict[str, Decision] = {}
        details: dict[str, Any] = {}

        for perm_id in required_perms:
            perm = self._registry.get_permission(perm_id)
            if perm is None:
                results[perm_id] = Decision.DENY
                details[perm_id] = f"Unknown permission '{perm_id}'"
                continue

            decision = self._engine.evaluate(perm)
            results[perm_id] = decision

            self._audit.record(
                capability_id=capability_id,
                permission_id=perm_id,
                decision=decision,
                policy=profile.value,
                reason=f"Permission '{perm_id}' → {decision.value} under {profile.value}",
            )

        denied_or_confirm = [p for p, d in results.items() if d in (Decision.DENY, Decision.NEED_CONFIRM)]
        has_deny = any(d == Decision.DENY for d in results.values())
        has_confirm = any(d == Decision.NEED_CONFIRM for d in results.values())

        if has_deny:
            overall = Decision.DENY
            reason = f"Denied by policy '{profile.value}': {', '.join(denied_or_confirm)}"
        elif has_confirm:
            overall = Decision.NEED_CONFIRM
            if len(denied_or_confirm) == 1:
                reason = f"Permission '{denied_or_confirm[0]}' requires confirmation under '{profile.value}'"
            else:
                reason = f"Multiple permissions require confirmation under '{profile.value}': {', '.join(denied_or_confirm)}"
        else:
            overall = Decision.ALLOW
            reason = f"All permissions allowed under policy '{profile.value}'"

        return PermissionResolution(
            capability_id=capability_id,
            required_permissions=required_perms,
            policy=profile.value,
            results=results,
            overall=overall,
            reason=reason,
        )

    def confirm(self, capability_id: str, task: dict[str, Any] | None = None) -> PermissionResolution:
        resolution = self.resolve(capability_id, task)
        if resolution.overall != Decision.NEED_CONFIRM:
            return resolution

        confirm_perms = [p for p, d in resolution.results.items() if d == Decision.NEED_CONFIRM]
        results = dict(resolution.results)
        for p in confirm_perms:
            results[p] = Decision.ALLOW
            self._audit.record(
                capability_id=capability_id,
                permission_id=p,
                decision=Decision.ALLOW,
                policy=resolution.policy,
                reason=f"Confirmed by user",
            )

        return PermissionResolution(
            capability_id=capability_id,
            required_permissions=resolution.required_permissions,
            policy=resolution.policy,
            results=results,
            overall=Decision.ALLOW,
            reason=f"User confirmed permissions: {', '.join(confirm_perms)}",
        )


permission_manager = PermissionManager()
