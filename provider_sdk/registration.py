from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from provider_sdk.manifest import ProviderManifest
from provider_sdk.manifest_v2 import ProviderDescriptor
from provider_sdk.loader import ProviderLoader
from provider_sdk.discovery import discovery_service
from core.providers.registry import provider_registry
from core.capability.registry import capability_registry

logger = logging.getLogger(__name__)


class TemporaryRegistry:
    _staged: dict[str, ProviderDescriptor] = {}

    @classmethod
    def stage(cls, descriptor: ProviderDescriptor) -> None:
        cls._staged[descriptor.id] = descriptor

    @classmethod
    def unstage(cls, provider_id: str) -> None:
        cls._staged.pop(provider_id, None)

    @classmethod
    def commit(cls, descriptor: ProviderDescriptor) -> bool:
        if descriptor.id not in cls._staged:
            logger.warning("[TemporaryRegistry] %s not staged, cannot commit", descriptor.id)
            return False
        if provider_registry.get(descriptor.id):
            logger.debug("[TemporaryRegistry] %s already registered, skipping", descriptor.id)
            cls._staged.pop(descriptor.id, None)
            return True
        instance = descriptor.instance
        if instance is None:
            logger.warning("[TemporaryRegistry] %s has no instance, cannot commit", descriptor.id)
            return False
        provider_registry.register(instance, priority=descriptor.metadata.get("priority", 100))
        caps = instance.capabilities().capability_names
        for cap in caps:
            capability_registry.register_capability(cap)
        logger.info(
            "[TemporaryRegistry] Committed %s/%s v%s (%d capabilities)",
            descriptor.publisher, descriptor.id, descriptor.version,
            len(caps),
        )
        return True

    @classmethod
    def clear(cls) -> None:
        cls._staged.clear()


class ProviderRegistrationPipeline:
    def __init__(self) -> None:
        self.loader = ProviderLoader()

    def register_from_manifest(self, manifest: ProviderManifest, base_dir: Path | None = None) -> bool:
        if provider_registry.get(manifest.provider_id):
            logger.debug("[RegistrationPipeline] %s already registered, skipping", manifest.provider_id)
            return False

        instance = self.loader.load_adapter(manifest, base_dir)
        if instance is None:
            logger.warning("[RegistrationPipeline] Failed to load adapter for %s", manifest.provider_id)
            return False

        provider_registry.register(instance, priority=manifest.priority)
        for cap in instance.capabilities().capability_names:
            capability_registry.register_capability(cap)

        logger.info(
            "[RegistrationPipeline] Registered %s v%s (%s adapter, priority=%d, %d capabilities)",
            manifest.provider_id, manifest.version, manifest.adapter_type,
            manifest.priority, len(manifest.capabilities),
        )
        return True

    def discover_and_register(self, search_dirs: list[str | Path] | None = None) -> int:
        if search_dirs:
            for d in search_dirs:
                discovery_service.add_search_dir(d)

        manifests = discovery_service.discover_manifests()
        count = 0
        for manifest in manifests:
            base_dir = None
            if manifest.adapter and not Path(manifest.adapter).is_absolute():
                base_dir = Path.home() / ".jarvis" / "providers"
            if self.register_from_manifest(manifest, base_dir):
                count += 1
        return count


registration_pipeline = ProviderRegistrationPipeline()
