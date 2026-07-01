from __future__ import annotations

from dataclasses import dataclass, field

ALL_PERMISSIONS: frozenset[str] = frozenset({
    "filesystem.read",
    "filesystem.write",
    "network.http",
    "network.smtp",
    "network.websocket",
    "clipboard.read",
    "clipboard.write",
    "desktop.window.read",
    "desktop.window.move",
    "desktop.mouse.move",
    "desktop.mouse.click",
    "desktop.keyboard.type",
    "desktop.screen.capture",
    "process.list",
    "process.control",
    "browser.tabs.read",
    "browser.tabs.control",
    "system.environment",
    "system.shell",
})

HIGH_RISK: frozenset[str] = frozenset({
    "system.shell",
    "desktop.mouse.click",
    "desktop.keyboard.type",
    "desktop.screen.capture",
    "process.control",
    "filesystem.write",
})


def validate_permissions(declared: list[str]) -> list[str]:
    errors: list[str] = []
    for p in declared:
        if p in ("all", "*", "everything", "any"):
            errors.append(f"Wildcard permission '{p}' is not allowed")
        elif p not in ALL_PERMISSIONS:
            errors.append(f"Unknown permission '{p}'")
    return errors


@dataclass
class PermissionGrant:
    permissions: frozenset[str] = field(default_factory=frozenset)
    high_risk_warning: bool = False

    def allows(self, permission: str) -> bool:
        return permission in self.permissions


class PermissionManager:
    def __init__(self) -> None:
        self._grants: dict[str, PermissionGrant] = {}
        self._audit_log: list[dict] = []

    def grant(self, provider_id: str, permissions: frozenset[str]) -> PermissionGrant:
        grant = PermissionGrant(
            permissions=permissions,
            high_risk_warning=bool(permissions & HIGH_RISK),
        )
        self._grants[provider_id] = grant
        return grant

    def check(self, provider_id: str, permission: str) -> bool:
        grant = self._grants.get(provider_id)
        if grant is None:
            self._audit(f"DENY", provider_id, permission, "No grant exists")
            return False
        if not grant.allows(permission):
            self._audit(f"DENY", provider_id, permission, "Not in granted set")
            return False
        self._audit(f"ALLOW", provider_id, permission, "")
        return True

    def _audit(self, result: str, provider_id: str, permission: str, reason: str) -> None:
        import time
        self._audit_log.append({
            "result": result,
            "provider_id": provider_id,
            "permission": permission,
            "reason": reason,
            "timestamp": time.time(),
        })

    def get_audit_log(self) -> list[dict]:
        return list(self._audit_log)

    def violations(self, provider_id: str) -> list[dict]:
        return [
            e for e in self._audit_log
            if e.get("result") == "DENY" and e.get("provider_id") == provider_id
        ]

    def clear(self) -> None:
        self._grants.clear()
        self._audit_log.clear()


permission_manager = PermissionManager()
