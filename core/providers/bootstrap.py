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
    from core.providers.adapters.workspace_provider import WorkspaceProvider
    from core.providers.adapters.github_provider import GitHubProvider
    from core.providers.adapters.email_provider import EmailProvider
    provider_registry.register(ForgeProvider(), priority=10)
    provider_registry.register(BrowserProvider(), priority=10)
    provider_registry.register(ResearchProvider(), priority=10)
    provider_registry.register(AutomationProvider(), priority=10)
    provider_registry.register(MessagingProvider(), priority=10)
    provider_registry.register(DeploymentProvider(), priority=10)
    provider_registry.register(WorkspaceProvider(), priority=10)
    provider_registry.register(GitHubProvider(), priority=10)
    provider_registry.register(EmailProvider(), priority=10)
    logger.info("[ProviderBootstrap] Registered internal providers: forge, browser, research, automation, messaging, deployment, workspace, github, email")


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


def register_sdk_providers() -> None:
    try:
        from provider_sdk.registration import ProviderRegistrationPipeline
        pipeline = ProviderRegistrationPipeline()
        count = pipeline.discover_and_register()
        if count:
            logger.info("[ProviderBootstrap] Registered %d SDK providers", count)
    except Exception as e:
        logger.debug("[ProviderBootstrap] SDK provider registration skipped: %s", e)


def bootstrap_v2_providers(manifest_dirs: list[Path] | None = None) -> int:
    from provider_sdk.lifecycle import lifecycle_manager

    if manifest_dirs is None:
        manifest_dirs = [Path.home() / ".jarvis" / "providers"]

    count = 0
    for search_dir in manifest_dirs:
        if not search_dir.is_dir():
            continue
        for manifest_path in sorted(search_dir.glob("*.json")) + sorted(search_dir.glob("*.yaml")) + sorted(search_dir.glob("*.yml")):
            try:
                record = lifecycle_manager.run_pipeline(str(manifest_path))
                if record.state == "ACTIVE":
                    count += 1
                elif record.state == "REJECTED":
                    logger.warning(
                        "[Bootstrap] %s rejected: %s",
                        manifest_path.name, record.diagnostics[0],
                    )
            except Exception as e:
                logger.exception("[Bootstrap] Pipeline failed for %s: %s", manifest_path.name, e)
    return count


def bootstrap_providers() -> None:
    register_internal_providers()
    register_external_providers()

    # Phase A: pipeline for external plugin manifests (v1 and v2)
    try:
        v2_count = bootstrap_v2_providers()
        if v2_count:
            logger.info("[ProviderBootstrap] Registered %d v2 providers", v2_count)
    except Exception as e:
        logger.warning("[ProviderBootstrap] v2 pipeline failed: %s", e)

    # Fallback: legacy scan for v1 manifests not covered by pipeline
    try:
        scan_provider_plugins()
    except Exception as e:
        logger.warning("[ProviderBootstrap] Legacy plugin scan failed: %s", e)

    register_sdk_providers()

    # Print startup metrics
    try:
        from provider_sdk.lifecycle import lifecycle_manager
        counts = lifecycle_manager.get_state_counts()
        active = counts.get("ACTIVE", 0)
        quarantined = counts.get("QUARANTINED", 0)
        rejected = counts.get("REJECTED", 0)
        discovered = counts.get("DISCOVERED", 0)
        validated = counts.get("VALIDATED", 0)
        total = sum(counts.values())
        caps = len(capability_registry.all_capabilities())
        from provider_sdk.manifest_v2 import PIPELINE_VERSION
        logger.info(
            "[ProviderBootstrap] Providers: %d discovered | %d active | %d quarantined | %d rejected | Capabilities: %d | Pipeline v%d",
            total, active, quarantined, rejected, caps, PIPELINE_VERSION,
        )
        if rejected:
            logger.info(
                "[ProviderBootstrap] Rejected: %s",
                ", ".join(r.provider_id for r in lifecycle_manager.get_state_list("REJECTED")),
            )
        if quarantined:
            logger.info(
                "[ProviderBootstrap] Quarantined: %s",
                ", ".join(r.provider_id for r in lifecycle_manager.get_state_list("QUARANTINED")),
            )
    except Exception as e:
        logger.debug("[ProviderBootstrap] Metrics unavailable: %s", e)

    logger.info(
        "[ProviderBootstrap] %d providers registered, %d capabilities",
        len(provider_registry.list_providers()),
        len(capability_registry.all_capabilities()),
    )
