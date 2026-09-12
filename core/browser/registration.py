"""Registration of Browser AI capabilities into the authoritative registry.

Usage (startup / discovery pass):
    from core.browser.registration import register_browser_ai
    register_browser_ai()   # idempotent: registry keys by capability name

This reuses tools.registry (ADR-013 single source of truth) and the existing
CapabilityDiscoveryService — no parallel registry is created.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_registered = False


def register_browser_ai() -> list[Any]:
    """Register Browser AI capabilities with the authoritative ToolRegistry."""
    global _registered
    from core.browser.browser_ai import get_browser_ai
    from core.capability.discovery import CapabilityDiscoveryService
    from tools.registry import _ensure_registry

    specialist = get_browser_ai()
    service = CapabilityDiscoveryService(_ensure_registry())
    caps = service.discover_specialist(specialist)
    _registered = True
    logger.info("[BrowserAI] registered %d capabilities", len(caps))
    return caps


def browser_ai_capabilities() -> list[dict[str, Any]]:
    """Return the registered Browser AI capabilities as dicts (for catalog/report)."""
    from tools.registry import _ensure_registry

    registry = _ensure_registry()
    return [
        cap.to_dict()
        for cap in registry.list_capabilities(owner_module="Browser AI")
    ]
