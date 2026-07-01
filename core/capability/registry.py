from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from core.capability.models import Capability, BUILTIN_CAPABILITY_IDS
from core.providers.base import ExecutionProvider
from core.providers.registry import ProviderRegistry, provider_registry

logger = logging.getLogger(__name__)


class CapabilityRegistry:
    def __init__(self, registry: ProviderRegistry | None = None):
        self._provider_registry = registry or provider_registry
        self._capabilities: dict[str, Capability] = {}

    def register(self, capability: Capability) -> None:
        self._capabilities[capability.id] = capability
        logger.info("[CapabilityRegistry] Registered capability: %s v%d", capability.id, capability.version)

    def get(self, capability_id: str) -> Capability | None:
        return self._capabilities.get(capability_id)

    def get_providers(self, capability: str) -> list[ExecutionProvider]:
        return self._provider_registry.get_providers_for_capability(capability)

    def has_capability(self, capability: str) -> bool:
        return self._provider_registry.has_capability(capability)

    def all_capabilities(self) -> list[str]:
        return self._provider_registry.all_capabilities()

    def get_description(self, capability: str) -> str:
        cap = self._capabilities.get(capability)
        if cap:
            return cap.description
        from core.capability.models import _BUILTIN_CAPABILITIES
        builtin = _BUILTIN_CAPABILITIES.get(capability)
        return builtin.description if builtin else ""

    def register_capability(self, capability: str, description: str = "") -> None:
        from core.capability.models import _BUILTIN_CAPABILITIES
        if capability in _BUILTIN_CAPABILITIES:
            self._capabilities[capability] = _BUILTIN_CAPABILITIES[capability]
        elif capability not in self._capabilities:
            desc = description or capability
            self._capabilities[capability] = Capability(
                id=capability, description=desc, version=1, tags=(description.lower(),) if description else (capability.lower(),),
            )
        logger.info("[CapabilityRegistry] Registered capability: %s", capability)

    def _iter_capabilities(self) -> dict[str, Capability]:
        if self._capabilities:
            return self._capabilities
        from core.capability.models import _BUILTIN_CAPABILITIES
        return dict(_BUILTIN_CAPABILITIES)

    def get_providers_for_task(self, goal: str) -> dict[str, list[ExecutionProvider]]:
        goal_lower = goal.lower()
        matches: dict[str, list[ExecutionProvider]] = {}

        for cap_id, cap in self._iter_capabilities().items():
            if cap.matches(goal_lower):
                providers = self._provider_registry.get_providers_for_capability(cap_id)
                if providers:
                    matches[cap_id] = providers

        return matches

    def match_goal(self, goal: str) -> list[Capability]:
        goal_lower = goal.lower()
        caps = self._iter_capabilities()
        return sorted(
            [c for c in caps.values() if c.matches(goal_lower)],
            key=lambda c: _score_match(c, goal_lower), reverse=True,
        )


def _score_match(cap: Capability, goal: str) -> int:
    score = 0
    if cap.id in goal:
        score += 3
    for tag in cap.tags:
        if tag in goal:
            score += 1
    return score


capability_registry = CapabilityRegistry()
