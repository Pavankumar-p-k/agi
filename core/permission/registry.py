"""
Module: core.permission.registry
Registry of all known permissions in the system.
"""
from __future__ import annotations
from typing import Any, Optional
from dataclasses import dataclass, field
import logging

from core.permission.models import Permission, PermissionCategory, RiskLevel, ALL_PERMISSIONS

logger = logging.getLogger(__name__)

_CAPABILITY_PERMISSION_MAP: dict[str, list[str]] = {
    "coding": ["filesystem.read", "filesystem.write"],
    "desktop": [
        "desktop.mouse.move", "desktop.mouse.click",
        "desktop.keyboard.type", "desktop.screen.capture",
        "desktop.window.read", "desktop.window.move",
    ],
    "browser": ["browser.tabs.read", "browser.tabs.control"],
    "filesystem": ["filesystem.read", "filesystem.write", "filesystem.delete"],
    "network": ["network.http", "network.smtp", "network.websocket"],
    "system": ["system.environment", "system.shell"],
    "process": ["process.list", "process.control"],
    "clipboard": ["clipboard.read", "clipboard.write"],
}


@dataclass
class PermissionRegistry:
    _permissions: dict[str, Permission] = field(default_factory=dict)

    def register(self, permission: Permission) -> Permission:
        self._permissions[permission.name] = permission
        return permission

    def unregister(self, name: str) -> bool:
        if name in self._permissions:
            del self._permissions[name]
            return True
        return False

    def get(self, name: str) -> Permission | None:
        return self._permissions.get(name)

    def has(self, name: str) -> bool:
        return name in self._permissions

    def list_all(self) -> list[Permission]:
        return list(self._permissions.values())

    def list_by_category(self, category: PermissionCategory) -> list[Permission]:
        return [p for p in self._permissions.values() if p.category == category]

    def permissions_for_capability(self, capability_id: str) -> list[str]:
        return list(_CAPABILITY_PERMISSION_MAP.get(capability_id, []))

    def count(self) -> int:
        return len(self._permissions)

    def clear(self) -> int:
        count = len(self._permissions)
        self._permissions.clear()
        return count

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": len(self._permissions),
            "permissions": {k: v.to_dict() for k, v in self._permissions.items()},
        }

    def register_defaults(self) -> int:
        defaults = [
            Permission(name="desktop.mouse.move", category=PermissionCategory.MOUSE_INPUT, risk_level=RiskLevel.LOW),
            Permission(name="desktop.mouse.click", category=PermissionCategory.MOUSE_INPUT, risk_level=RiskLevel.MEDIUM),
            Permission(name="desktop.mouse.double_click", category=PermissionCategory.MOUSE_INPUT, risk_level=RiskLevel.MEDIUM),
            Permission(name="desktop.mouse.drag", category=PermissionCategory.MOUSE_INPUT, risk_level=RiskLevel.HIGH),
            Permission(name="desktop.keyboard.type", category=PermissionCategory.KEYBOARD_INPUT, risk_level=RiskLevel.MEDIUM),
            Permission(name="desktop.keyboard.hotkey", category=PermissionCategory.KEYBOARD_INPUT, risk_level=RiskLevel.HIGH),
            Permission(name="desktop.screen.capture", category=PermissionCategory.SCREEN_CAPTURE, risk_level=RiskLevel.LOW),
            Permission(name="desktop.screen.record", category=PermissionCategory.SCREEN_CAPTURE, risk_level=RiskLevel.MEDIUM),
            Permission(name="desktop.window.read", category=PermissionCategory.DESKTOP_CONTROL, risk_level=RiskLevel.LOW),
            Permission(name="desktop.window.move", category=PermissionCategory.DESKTOP_CONTROL, risk_level=RiskLevel.MEDIUM),
            Permission(name="desktop.replay.record", category=PermissionCategory.REPLAY, risk_level=RiskLevel.HIGH),
            Permission(name="desktop.replay.execute", category=PermissionCategory.REPLAY, risk_level=RiskLevel.CRITICAL),
            Permission(name="filesystem.read", category=PermissionCategory.FILESYSTEM, risk_level=RiskLevel.LOW),
            Permission(name="filesystem.write", category=PermissionCategory.FILESYSTEM, risk_level=RiskLevel.HIGH),
            Permission(name="filesystem.delete", category=PermissionCategory.FILESYSTEM, risk_level=RiskLevel.CRITICAL),
            Permission(name="network.http", category=PermissionCategory.NETWORK, risk_level=RiskLevel.LOW),
            Permission(name="network.smtp", category=PermissionCategory.NETWORK, risk_level=RiskLevel.MEDIUM),
            Permission(name="network.websocket", category=PermissionCategory.NETWORK, risk_level=RiskLevel.MEDIUM),
            Permission(name="system.environment", category=PermissionCategory.SYSTEM, risk_level=RiskLevel.LOW),
            Permission(name="system.shell", category=PermissionCategory.SYSTEM, risk_level=RiskLevel.CRITICAL),
            Permission(name="process.list", category=PermissionCategory.SYSTEM, risk_level=RiskLevel.LOW),
            Permission(name="process.control", category=PermissionCategory.SYSTEM, risk_level=RiskLevel.HIGH),
            Permission(name="clipboard.read", category=PermissionCategory.SYSTEM, risk_level=RiskLevel.LOW),
            Permission(name="clipboard.write", category=PermissionCategory.SYSTEM, risk_level=RiskLevel.LOW),
            Permission(name="browser.tabs.read", category=PermissionCategory.BROWSER, risk_level=RiskLevel.LOW),
            Permission(name="browser.tabs.control", category=PermissionCategory.BROWSER, risk_level=RiskLevel.MEDIUM),
        ]
        count = 0
        for p in defaults:
            if not self.has(p.name):
                self.register(p)
                count += 1
        return count


permission_registry = PermissionRegistry()
