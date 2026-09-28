"""CapabilityRegistry — versioned capability store over the provider registry.

Also accepts plain capability-name strings via register_capability()
(provider_sdk registration passes names from provider manifests;
missing descriptors are synthesized from the builtin capabilities).
"""
from __future__ import annotations

from typing import Optional

from core.capability.models import Capability, _BUILTIN_CAPABILITIES


class CapabilityRegistry:
    """Stores capabilities; latest version wins on duplicate id."""

    def __init__(self, registry: Optional[object] = None) -> None:
        # `registry` is the ProviderRegistry to index capabilities against.
        self._provider_registry = registry
        self._capabilities: dict[str, Capability] = {}

    def register(self, capability: Capability) -> Capability:
        existing = self._capabilities.get(capability.id)
        if existing is None or capability.version >= existing.version:
            self._capabilities[capability.id] = capability
        return capability

    def register_capability(self, capability) -> Optional[Capability]:
        """Register a capability by name (string) or Capability instance."""
        if isinstance(capability, str):
            existing = self._capabilities.get(capability)
            if existing is not None:
                return existing
            builtin = _BUILTIN_CAPABILITIES.get(capability)
            cap = Capability(
                id=capability,
                description=getattr(builtin, "description", ""),
                permissions=getattr(builtin, "permissions", ()),
                tags=getattr(builtin, "tags", ()),
            )
            self._capabilities[capability] = cap
            return cap
        if isinstance(capability, Capability):
            return self.register(capability)
        # Best-effort: unknown descriptor types are ignored, never crash.
        return None

    def get(self, capability_id: str) -> Optional[Capability]:
        return self._capabilities.get(capability_id)

    def has(self, capability_id: str) -> bool:
        return capability_id in self._capabilities

    def all(self) -> list:
        return list(self._capabilities.values())


# Module-level default registry.
capability_registry = CapabilityRegistry()


__all__ = ["CapabilityRegistry", "capability_registry"]
