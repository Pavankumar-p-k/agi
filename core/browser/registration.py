"""BrowserAI registration into the authoritative tool registry."""
from __future__ import annotations

from tools.registry import ToolRegistry, new_registry, _ensure_registry


def register_browser_ai() -> list:
    """Register all BrowserAI capabilities; returns the definitions."""
    from core.browser.browser_ai import BrowserAI
    registry = _ensure_registry()
    capabilities = BrowserAI().get_capabilities()
    for definition in capabilities:
        registry.register_capability(definition)
    return capabilities


def browser_ai_capabilities() -> list:
    """Registered BrowserAI capabilities as dicts."""
    registry = _ensure_registry()
    return [d for d in registry.capabilities_as_dicts()
            if str(d.get("name", "")).startswith("browser.")
            and d.get("owner_module") == "Browser AI"]


__all__ = ["register_browser_ai", "browser_ai_capabilities"]
