"""ProviderRouter — selects a provider for a capability with fallback.

Contract (tests/architecture/test_capability_gates.py + trace/metrics tests):
- module-level ``provider_router`` instance is monkeypatched by tests;
- ``select`` / ``select_with_fallback`` return a single provider object;
- ``_registry`` attribute holds the ProviderRegistry (tests inject fakes).
"""
from __future__ import annotations

from typing import Any, List, Optional, Tuple

from core.providers.base import ExecutionProvider
from core.providers.registry import ProviderRegistry


class ProviderRouter:
    """Capability-addressed provider selection over a ProviderRegistry."""

    def __init__(self, registry: Optional[ProviderRegistry] = None) -> None:
        self._registry = registry if registry is not None else ProviderRegistry()

    # ── selection ────────────────────────────────────────────────────
    def select(self, capability: str) -> Optional[ExecutionProvider]:
        """Best enabled provider for a capability, or None."""
        chain = self._select_chain(capability)
        return chain[0] if chain else None

    def select_with_fallback(
        self, capability: str,
    ) -> Tuple[Optional[ExecutionProvider], List[ExecutionProvider]]:
        """Best provider plus its fallback chain."""
        chain = self._select_chain(capability)
        return (chain[0], chain[1:]) if chain else (None, [])

    def _select_chain(self, capability: str) -> List[ExecutionProvider]:
        candidates = self._registry.providers_for_capability(capability)
        return [p for p in candidates if getattr(p, "installed", True)
                and p.is_enabled()]

    def resolve(self, capability: str) -> Optional[ExecutionProvider]:
        return self.select(capability)

    # ── introspection ────────────────────────────────────────────────
    @property
    def registry(self) -> ProviderRegistry:
        return self._registry

    def fallback_chain(self, capability: str) -> List[ExecutionProvider]:
        return self._select_chain(capability)


# Module-level default router (tests monkeypatch this attribute).
provider_router = ProviderRouter()


__all__ = ["ProviderRouter", "provider_router"]
