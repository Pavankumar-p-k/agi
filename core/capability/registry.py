"""Authoritative Capability Registry module for JARVIS.

This module re-exports the unified registry from tools.registry and
tools.base_tool per ADR-013 (single source of truth), and additionally
provides the capability-level *view* over the provider registry pinned by
tests/unit/test_provider_ecosystem.py and tests/architecture/test_capability_gates.py:

- ``CapabilityRegistry(registry=<ProviderRegistry>)`` owns no provider
  storage — capabilities are derived live from the providers it wraps, plus a
  small local registry of extra capability descriptions (``register_capability``).
- ``capability_registry`` is the module singleton used by the provider
  bootstrap to mirror provider capabilities into the capability layer.
"""
from __future__ import annotations

from typing import Any, Optional

from tools.base_tool import (
    CapabilityDefinition,
    CapabilityHealth,
    CapabilityStatus,
    CapabilityType,
    ReliabilityMetrics,
    RiskTier,
    ToolDefinition,
    ToolResult,
    VerificationSpec,
)
from tools.registry import (
    CapabilityRegistry as _ToolCapabilityRegistry,
    ToolRegistry,
    get_capability,
    get_tool,
    new_capability_registry,
    new_registry,
    _ensure_registry,
)

__all__ = [
    "CapabilityDefinition",
    "CapabilityHealth",
    "CapabilityStatus",
    "CapabilityType",
    "ReliabilityMetrics",
    "RiskTier",
    "ToolDefinition",
    "ToolResult",
    "VerificationSpec",
    "CapabilityRegistry",
    "ToolRegistry",
    "get_capability",
    "get_tool",
    "new_capability_registry",
    "new_registry",
    "capability_registry",
    "async_capability_registry",
    "ProviderCapabilityRegistry",
]

# Historical alias kept for import compatibility with the ADR-013 re-export.
ProviderCapabilityRegistry = _ToolCapabilityRegistry


class CapabilityRegistry:
    """Capability-level view over the provider registry.

    Wraps a ``core.providers.registry.ProviderRegistry`` (or anything with
    ``get_providers_for_capability`` / ``has_capability`` /
    ``all_capabilities``) and answers capability questions from it.  Extra
    capability descriptions can be registered locally without touching
    provider state.
    """

    # Keyword fragments used by get_providers_for_task (task text → capability).
    _TASK_KEYWORDS: dict[str, tuple[str, ...]] = {
        "coding": ("code", "coding", "program", "function", "implement", "debug", "refactor", "script"),
        "testing": ("test", "testing", "unit test", "qa", "verify code"),
        "review": ("review", "audit", "inspect code"),
        "github": ("github", "pull request", "commit", "repository"),
        "git": ("git", "version control"),
        "email": ("email", "mail", "smtp"),
        "browser": ("browser", "web page", "navigate", "click"),
        "desktop": ("desktop", "window", "screenshot", "mouse", "keyboard"),
        "research": ("research", "search", "investigate", "documentation"),
        "scaffold": ("scaffold", "bootstrap project", "new project"),
    }

    _DEFAULT_DESCRIPTIONS: dict[str, str] = {
        "coding": "Code editing, generation and execution",
        "python": "Python code generation and execution",
        "testing": "Test generation and execution",
        "review": "Code review and audit",
        "refactoring": "Code refactoring",
        "documentation": "Documentation generation",
        "research": "Information research and synthesis",
        "scaffold": "Project scaffolding",
        "github": "GitHub repository operations",
        "git": "Version control operations",
        "version_control": "Version control operations",
        "email": "Email composition and sending",
        "send_email": "Send email messages",
        "compose_email": "Compose email drafts",
        "browser": "Browser automation",
        "desktop": "Desktop automation",
        "messaging": "Instant messaging integrations",
        "workspace": "Workspace/desktop state inspection",
        "desktop_state": "Desktop state inspection",
    }

    def __init__(self, registry: Any = None) -> None:
        self._provider_registry = registry
        self._descriptions: dict[str, str] = dict(self._DEFAULT_DESCRIPTIONS)
        self._capability_objects: dict[str, Any] = {}

    # ------------------------------------------------------------------ #
    # Provider-backed queries                                            #
    # ------------------------------------------------------------------ #

    def get_providers(self, capability: str) -> list[Any]:
        if self._provider_registry is None:
            return []
        try:
            return list(self._provider_registry.get_providers_for_capability(capability))
        except Exception:
            return []

    def has_capability(self, capability: str) -> bool:
        if self._provider_registry is None:
            return False
        try:
            return bool(self._provider_registry.has_capability(capability))
        except Exception:
            return False

    def all_capabilities(self) -> list[str]:
        caps: set[str] = set(self._descriptions)
        if self._provider_registry is not None:
            try:
                caps.update(self._provider_registry.all_capabilities())
            except Exception:
                pass
        return sorted(caps)

    def get_description(self, capability: str) -> str:
        if capability in self._descriptions:
            return self._descriptions[capability]
        if self._provider_registry is not None:
            try:
                for provider in self._provider_registry.get_providers_for_capability(capability):
                    caps = provider.capabilities()
                    # No per-capability descriptions on providers; a capability
                    # that exists is described generically when unknown.
                    if capability in (caps.capability_names or []):
                        return capability.replace("_", " ")
            except Exception:
                pass
        return ""

    def register_capability(self, capability: str, description: str = "") -> None:
        """Register/override a capability description in this view."""
        self._descriptions[capability] = description

    def register(self, capability: Any) -> None:
        """Register a ``core.capability.models.Capability`` object (versioned).

        Re-registering the same id keeps only the latest version (Gate 4:
        multiple versions coexist temporally, ``get`` returns the newest).
        """
        self._capability_objects[capability.id] = capability
        if capability.description:
            self._descriptions.setdefault(capability.id, capability.description)

    def get(self, capability_id: str) -> Optional[Any]:
        return self._capability_objects.get(capability_id)

    def get_providers_for_task(self, task: str) -> dict[str, list[Any]]:
        """Map task text → {capability: providers} via keyword matching."""
        text = (task or "").lower()
        if not text.strip():
            return {}
        matches: dict[str, list[Any]] = {}
        for capability, keywords in self._TASK_KEYWORDS.items():
            if any(kw in text for kw in keywords):
                providers = self.get_providers(capability)
                if providers:
                    matches[capability] = providers
        return matches


# Module singleton used by the provider bootstrap to mirror capabilities.
capability_registry = CapabilityRegistry()


# ---------------------------------------------------------------------- #
# Backward-compatible function shims (legacy callers)                     #
# ---------------------------------------------------------------------- #

def async_capability_registry(*args: Any, **kwargs: Any) -> CapabilityRegistry:
    return capability_registry
