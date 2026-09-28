"""PermissionRegistry — maps capabilities to required permissions."""
from __future__ import annotations

# Capability id -> required permission ids.
_CAPABILITY_PERMISSIONS: dict[str, tuple[str, ...]] = {
    "chat": (),
    "coding": ("filesystem.read", "filesystem.write"),
    "research": ("network.http",),
    "testing": ("filesystem.read",),
    "deployment": ("system.shell",),
    "documentation": ("filesystem.read",),
    "review": ("filesystem.read",),
    "security": ("filesystem.read",),
    "desktop": ("desktop.mouse.click", "desktop.keyboard.type",
                "desktop.screen.capture", "desktop.window.focus"),
    "browser": ("network.http",),
}


class PermissionRegistry:
    def permissions_for_capability(self, capability_id: str) -> tuple:
        return _CAPABILITY_PERMISSIONS.get(capability_id, ())

    def register(self, capability_id: str, permissions: tuple) -> None:
        _CAPABILITY_PERMISSIONS[capability_id] = tuple(permissions)

    def all_capabilities(self) -> list:
        return sorted(_CAPABILITY_PERMISSIONS.keys())


permission_registry = PermissionRegistry()


__all__ = ["PermissionRegistry", "permission_registry"]
