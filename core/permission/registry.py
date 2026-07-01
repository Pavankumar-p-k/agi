from __future__ import annotations

import logging
from typing import Any

from core.capability.models import Capability, _BUILTIN_CAPABILITIES
from core.capability.registry import capability_registry
from core.permission.models import Permission, _BUILTIN_PERMISSIONS
from core.providers.base import ExecutionProvider
from core.providers.registry import provider_registry

logger = logging.getLogger(__name__)


class PermissionRegistry:
    def __init__(self) -> None:
        self._permissions: dict[str, Permission] = dict(_BUILTIN_PERMISSIONS)
        self._capability_permissions: dict[str, frozenset[str]] = {}
        self._provider_declared: dict[str, frozenset[str]] = {}

    def register_permission(self, perm: Permission) -> None:
        self._permissions[perm.id] = perm

    def get_permission(self, perm_id: str) -> Permission | None:
        return self._permissions.get(perm_id)

    def all_permission_ids(self) -> frozenset[str]:
        return frozenset(self._permissions.keys())

    def permissions_for_capability(self, capability_id: str) -> frozenset[str]:
        cached = self._capability_permissions.get(capability_id)
        if cached is not None:
            return cached

        cap = capability_registry.get(capability_id)
        if cap and cap.permissions:
            perms = frozenset(cap.permissions)
            self._capability_permissions[capability_id] = perms
            return perms

        if capability_id in _BUILTIN_CAPABILITIES:
            perms = frozenset(_BUILTIN_CAPABILITIES[capability_id].permissions)
            self._capability_permissions[capability_id] = perms
            return perms

        return frozenset()

    def declared_by_provider(self, provider_id: str) -> frozenset[str]:
        cached = self._provider_declared.get(provider_id)
        if cached is not None:
            return cached

        provider = provider_registry.get(provider_id)
        if provider is None:
            return frozenset()

        caps = getattr(provider, "capabilities", None)
        if callable(caps):
            caps_obj = caps()
            cap_names = list(caps_obj.capability_names) if hasattr(caps_obj, "capability_names") else []
        else:
            cap_names = caps or []

        all_perms: set[str] = set()
        for cname in cap_names:
            all_perms.update(self.permissions_for_capability(cname))

        result = frozenset(all_perms)
        self._provider_declared[provider_id] = result
        return result

    def invalidate_provider(self, provider_id: str) -> None:
        self._provider_declared.pop(provider_id, None)

    def invalidate_capability(self, capability_id: str) -> None:
        self._capability_permissions.pop(capability_id, None)


permission_registry = PermissionRegistry()
