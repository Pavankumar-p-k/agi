from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from core.providers.base import ExecutionProvider
from core.providers.registry import ProviderRegistry, provider_registry

logger = logging.getLogger(__name__)

_KNOWN_CAPABILITIES: dict[str, str] = {
    "coding": "Software development and code generation",
    "browser": "Web browsing and page interaction",
    "vision": "Image understanding and analysis",
    "deployment": "Application deployment and hosting",
    "testing": "Automated test execution and generation",
    "documentation": "Documentation generation and management",
    "security": "Security analysis and auditing",
    "research": "Information gathering and analysis",
    "database": "Database operations and management",
    "notifications": "Push notifications and alerts",
    "filesystem": "File system operations",
    "desktop": "Desktop automation",
    "email": "Email sending and management",
    "messaging": "Messaging platform integration",
    "terminal": "Terminal and shell operations",
    "voice": "Voice processing and synthesis",
    "speech": "Speech-to-text and text-to-speech",
    "translation": "Language translation",
    "OCR": "Optical character recognition",
    "image_generation": "AI image generation",
    "automation": "General workflow automation",
}


class CapabilityRegistry:
    def __init__(self, registry: ProviderRegistry | None = None):
        self._provider_registry = registry or provider_registry
        self._capability_descriptions: dict[str, str] = dict(_KNOWN_CAPABILITIES)

    def get_providers(self, capability: str) -> list[ExecutionProvider]:
        return self._provider_registry.get_providers_for_capability(capability)

    def has_capability(self, capability: str) -> bool:
        return self._provider_registry.has_capability(capability)

    def all_capabilities(self) -> list[str]:
        return self._provider_registry.all_capabilities()

    def get_description(self, capability: str) -> str:
        return self._capability_descriptions.get(capability, "")

    def register_capability(self, capability: str, description: str = "") -> None:
        self._capability_descriptions[capability] = description or capability
        logger.info("[CapabilityRegistry] Registered capability: %s", capability)

    def get_providers_for_task(self, goal: str) -> dict[str, list[ExecutionProvider]]:
        goal_lower = goal.lower()
        matches: dict[str, list[ExecutionProvider]] = {}

        for capability in self._capability_descriptions:
            if capability in goal_lower:
                providers = self._provider_registry.get_providers_for_capability(capability)
                if providers:
                    matches[capability] = providers

        return matches


capability_registry = CapabilityRegistry()
