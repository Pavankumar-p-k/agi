"""Provider bootstrap: registers built-in and external providers at startup.

Completed from the committed contract in tests/unit/test_provider_ecosystem.py
(TestProviderBootstrap).  Idempotent — repeated calls never duplicate
registrations.  External CLI providers are registered only when their binary
is detected on PATH.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from core.providers.registry import provider_registry
from core.capability.registry import capability_registry

logger = logging.getLogger(__name__)

_BOOTSTRAPPED = False
_BOOTSTRAPPED_REGISTRY_ID: int | None = None


def register_internal_providers() -> None:
    """Register the internal forge provider (highest priority)."""
    if provider_registry.get("forge") is None:
        from core.providers.adapters.forge import ForgeProvider
        provider_registry.register(ForgeProvider(), priority=10)
        logger.info("[provider_bootstrap] registered internal provider: forge")


def register_external_providers() -> None:
    """Register external CLI providers when their binaries are installed."""
    from core.providers.adapters.claude_code import ClaudeCodeProvider
    from core.providers.adapters.codex import CodexProvider
    for cls in (ClaudeCodeProvider, CodexProvider):
        try:
            provider = cls()
        except Exception as exc:
            logger.debug("[provider_bootstrap] %s construction failed: %s",
                         getattr(cls, "provider_id", cls), exc)
            continue
        if not provider.installed:
            continue
        if provider_registry.get(provider.provider_id) is None:
            provider_registry.register(provider, priority=cls.priority)
            logger.info("[provider_bootstrap] registered external provider: %s",
                        provider.provider_id)


def scan_provider_plugins() -> int:
    """Best-effort scan of ~/.jarvis/providers for plugin manifests.

    Never raises; returns the number of manifests discovered (not registered —
    actual plugin loading stays with the existing plugin system).
    """
    count = 0
    try:
        root = Path.home() / ".jarvis" / "providers"
        if root.is_dir():
            for manifest_file in root.glob("*.json"):
                try:
                    json.loads(manifest_file.read_text(encoding="utf-8"))
                    count += 1
                except Exception:
                    continue
    except Exception as exc:
        logger.debug("[provider_bootstrap] plugin scan failed: %s", exc)
    return count


def _sync_capabilities() -> None:
    """Mirror registered provider capabilities into the capability registry."""
    try:
        for provider in provider_registry.list_providers():
            try:
                caps = provider.capabilities().capability_names
            except Exception:
                continue
            for cap in caps:
                try:
                    capability_registry.register_capability(cap)
                except Exception:
                    continue
    except Exception as exc:
        logger.debug("[provider_bootstrap] capability sync failed: %s", exc)


def bootstrap_providers(force: bool = False) -> None:
    """Full bootstrap.  Idempotent unless ``force=True``.

    Idempotence is keyed to the *active* registry: a clean (or patched)
    registry is always populated, while repeated calls against the same
    registry are no-ops (registration itself also guards duplicates).
    """
    global _BOOTSTRAPPED, _BOOTSTRAPPED_REGISTRY_ID
    registry_token = id(provider_registry)
    if not force and _BOOTSTRAPPED and _BOOTSTRAPPED_REGISTRY_ID == registry_token:
        return
    register_internal_providers()
    register_external_providers()
    scan_provider_plugins()
    _sync_capabilities()
    _BOOTSTRAPPED = True
    _BOOTSTRAPPED_REGISTRY_ID = registry_token
    logger.info(
        "[provider_bootstrap] bootstrap complete (%d providers)",
        len(provider_registry.list_providers()),
    )
