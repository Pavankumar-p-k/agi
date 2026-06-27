from __future__ import annotations

import logging
import os
from pathlib import Path

from core.providers.registry import provider_registry
from core.capability.registry import capability_registry

logger = logging.getLogger(__name__)


def register_internal_providers() -> None:
    from core.providers.adapters.forge import ForgeProvider
    from core.providers.adapters.browser_provider import BrowserProvider
    from core.providers.adapters.research_provider import ResearchProvider
    from core.providers.adapters.automation_provider import AutomationProvider
    from core.providers.adapters.messaging_provider import MessagingProvider
    from core.providers.adapters.deployment_provider import DeploymentProvider
    provider_registry.register(ForgeProvider(), priority=10)
    provider_registry.register(BrowserProvider(), priority=10)
    provider_registry.register(ResearchProvider(), priority=10)
    provider_registry.register(AutomationProvider(), priority=10)
    provider_registry.register(MessagingProvider(), priority=10)
    provider_registry.register(DeploymentProvider(), priority=10)
    logger.info("[ProviderBootstrap] Registered internal providers: forge, browser, research, automation, messaging, deployment")


def register_external_providers() -> None:
    from core.providers.adapters.claude_code import ClaudeCodeProvider
    from core.providers.adapters.codex import CodexProvider

    claude = ClaudeCodeProvider()
    if claude.installed:
        provider_registry.register(claude, priority=50)
        logger.info("[ProviderBootstrap] Registered external provider: claude_code")
    else:
        logger.info("[ProviderBootstrap] claude_code not installed, skipping")

    codex = CodexProvider()
    if codex.installed:
        provider_registry.register(codex, priority=60)
        logger.info("[ProviderBootstrap] Registered external provider: codex")
    else:
        logger.info("[ProviderBootstrap] codex not installed, skipping")


def scan_provider_plugins() -> None:
    plugins_dir = Path.home() / ".jarvis" / "providers"
    if not plugins_dir.is_dir():
        return

    for manifest_path in sorted(plugins_dir.glob("*.json")):
        try:
            import json
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            provider_id = data.get("provider_id") or data.get("name", manifest_path.stem)
            if provider_registry.get(provider_id):
                logger.debug("[ProviderBootstrap] Provider %s already registered", provider_id)
                continue

            adapter_path = data.get("adapter", "")
            if not adapter_path or not os.path.isabs(adapter_path):
                adapter_path = str(plugins_dir / adapter_path)
            if not os.path.exists(adapter_path):
                logger.warning("[ProviderBootstrap] Adapter %s not found for %s", adapter_path, provider_id)
                continue

            import importlib.util
            import sys
            spec = importlib.util.spec_from_file_location(f"provider_{provider_id}", adapter_path)
            if not spec or not spec.loader:
                continue
            mod = importlib.util.module_from_spec(spec)
            sys.modules[f"provider_{provider_id}"] = mod
            spec.loader.exec_module(mod)

            provider_class = getattr(mod, "Provider", None)
            if not provider_class:
                logger.warning("[ProviderBootstrap] No Provider class in %s", adapter_path)
                continue

            provider_instance = provider_class()
            priority = data.get("priority", 100)
            provider_registry.register(provider_instance, priority=priority)
            for cap in provider_instance.capabilities().capability_names:
                capability_registry.register_capability(cap)

            logger.info("[ProviderBootstrap] Loaded external provider: %s from %s", provider_id, adapter_path)

        except Exception as e:
            logger.exception("[ProviderBootstrap] Failed to load provider manifest %s: %s", manifest_path, e)


def bootstrap_providers() -> None:
    register_internal_providers()
    register_external_providers()
    scan_provider_plugins()
    logger.info(
        "[ProviderBootstrap] %d providers registered, %d capabilities",
        len(provider_registry.list_providers()),
        len(capability_registry.all_capabilities()),
    )
