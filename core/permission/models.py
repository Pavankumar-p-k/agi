from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class PermissionCategory(StrEnum):
    FILESYSTEM = "filesystem"
    NETWORK = "network"
    DESKTOP = "desktop"
    BROWSER = "browser"
    PROCESS = "process"
    CLIPBOARD = "clipboard"
    SYSTEM = "system"
    GIT = "git"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Decision(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    NEED_CONFIRM = "need_confirm"


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
    "browser.tabs.read",
    "browser.tabs.control",
    "process.list",
    "process.control",
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


class Permission:
    def __init__(
        self,
        id: str,
        category: PermissionCategory | str = "",
        risk: RiskLevel | str = RiskLevel.LOW,
        requires_confirmation: bool = False,
        audit: bool = True,
        description: str = "",
    ) -> None:
        self.id = id
        self.category = PermissionCategory(category) if isinstance(category, str) and category else self._infer_category(id)
        self.risk = RiskLevel(risk) if isinstance(risk, str) else risk
        self.requires_confirmation = requires_confirmation
        self.audit = audit
        self.description = description or id

    def _infer_category(self, perm_id: str) -> PermissionCategory:
        prefix = perm_id.split(".")[0] if "." in perm_id else perm_id
        for cat in PermissionCategory:
            if cat.value == prefix:
                return cat
        return PermissionCategory.SYSTEM

    def is_high_risk(self) -> bool:
        return self.id in HIGH_RISK or self.risk in (RiskLevel.HIGH, RiskLevel.CRITICAL)

    def __repr__(self) -> str:
        return f"Permission({self.id}, risk={self.risk})"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Permission):
            return self.id == other.id
        if isinstance(other, str):
            return self.id == other
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.id)


_BUILTIN_PERMISSIONS: dict[str, Permission] = {
    "filesystem.read": Permission("filesystem.read", risk=RiskLevel.LOW),
    "filesystem.write": Permission("filesystem.write", risk=RiskLevel.HIGH, requires_confirmation=True),
    "network.http": Permission("network.http", risk=RiskLevel.LOW),
    "network.smtp": Permission("network.smtp", risk=RiskLevel.MEDIUM, requires_confirmation=True),
    "network.websocket": Permission("network.websocket", risk=RiskLevel.MEDIUM),
    "clipboard.read": Permission("clipboard.read", risk=RiskLevel.MEDIUM, requires_confirmation=True),
    "clipboard.write": Permission("clipboard.write", risk=RiskLevel.LOW),
    "desktop.window.read": Permission("desktop.window.read", risk=RiskLevel.MEDIUM),
    "desktop.window.move": Permission("desktop.window.move", risk=RiskLevel.HIGH, requires_confirmation=True),
    "desktop.mouse.move": Permission("desktop.mouse.move", risk=RiskLevel.HIGH, requires_confirmation=True),
    "desktop.mouse.click": Permission("desktop.mouse.click", risk=RiskLevel.CRITICAL, requires_confirmation=True),
    "desktop.keyboard.type": Permission("desktop.keyboard.type", risk=RiskLevel.CRITICAL, requires_confirmation=True),
    "desktop.screen.capture": Permission("desktop.screen.capture", risk=RiskLevel.CRITICAL, requires_confirmation=True),
    "browser.tabs.read": Permission("browser.tabs.read", risk=RiskLevel.MEDIUM),
    "browser.tabs.control": Permission("browser.tabs.control", risk=RiskLevel.HIGH, requires_confirmation=True),
    "process.list": Permission("process.list", risk=RiskLevel.MEDIUM),
    "process.control": Permission("process.control", risk=RiskLevel.CRITICAL, requires_confirmation=True),
    "system.environment": Permission("system.environment", risk=RiskLevel.LOW),
    "system.shell": Permission("system.shell", risk=RiskLevel.CRITICAL, requires_confirmation=True),
}


@dataclass(frozen=True)
class AuditEntry:
    timestamp: float
    capability_id: str
    permission_id: str
    decision: Decision
    policy: str
    reason: str
    details: dict[str, Any] = field(default_factory=dict)
