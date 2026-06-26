from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from core.plugins.base import PluginRegistry
from core.providers.base import ExecutionProvider, ProviderHealth, ProviderHealthStatus

logger = logging.getLogger(__name__)

_PROVIDER_SETTINGS_DIR = Path.home() / ".jarvis" / "provider_settings"
_PROVIDER_SETTINGS_FILE = _PROVIDER_SETTINGS_DIR / "registry.json"


class ProviderRegistry:
    def __init__(self):
        self._providers: dict[str, ExecutionProvider] = {}
        self._priorities: dict[str, int] = {}
        self._capability_index: dict[str, list[str]] = {}
        self._plugin_registry: PluginRegistry | None = None
        self._pending_settings: dict[str, dict] = {}
        self._load_persisted()

    @property
    def plugin_registry(self) -> PluginRegistry | None:
        return self._plugin_registry

    def link_plugin_registry(self, registry: PluginRegistry) -> None:
        self._plugin_registry = registry

    # -- Registration -------------------------------------------------------

    def register(self, provider: ExecutionProvider, priority: int | None = None) -> None:
        pid = provider.provider_id
        self._providers[pid] = provider

        # Apply any pending persisted settings before setting priority
        if pid in self._pending_settings:
            settings = self._pending_settings.pop(pid)
            if not settings.get("enabled", True):
                provider.disable()
            if "priority" in settings:
                self._priorities[pid] = settings["priority"]
            else:
                self._priorities[pid] = priority if priority is not None else provider.priority
        else:
            self._priorities[pid] = priority if priority is not None else provider.priority

        caps = provider.capabilities().capability_names
        for cap in caps:
            if cap not in self._capability_index:
                self._capability_index[cap] = []
            if pid not in self._capability_index[cap]:
                self._capability_index[cap].append(pid)

        logger.info("[ProviderRegistry] Registered %s v%s (priority=%d, capabilities=%s)",
                     pid, provider.version, self._priorities[pid], caps)
        self._save_persisted()

    def unregister(self, provider_id: str) -> bool:
        provider = self._providers.pop(provider_id, None)
        if not provider:
            return False
        self._priorities.pop(provider_id, None)
        for cap in list(self._capability_index.keys()):
            if provider_id in self._capability_index[cap]:
                self._capability_index[cap].remove(provider_id)
            if not self._capability_index[cap]:
                del self._capability_index[cap]
        logger.info("[ProviderRegistry] Unregistered %s", provider_id)
        self._save_persisted()
        return True

    def get(self, provider_id: str) -> ExecutionProvider | None:
        return self._providers.get(provider_id)

    def list_providers(self) -> list[ExecutionProvider]:
        return list(self._providers.values())

    def list_enabled(self) -> list[ExecutionProvider]:
        return [p for p in self._providers.values() if p.enabled]

    # -- Priority -----------------------------------------------------------

    def set_priority(self, provider_id: str, priority: int) -> bool:
        if provider_id not in self._providers:
            return False
        self._priorities[provider_id] = priority
        self._save_persisted()
        return True

    def get_priority(self, provider_id: str) -> int:
        return self._priorities.get(provider_id, 100)

    def _sorted_providers(self) -> list[ExecutionProvider]:
        return sorted(
            self._providers.values(),
            key=lambda p: self._priorities.get(p.provider_id, p.priority),
        )

    # -- Enable / Disable ---------------------------------------------------

    def enable(self, provider_id: str) -> bool:
        provider = self._providers.get(provider_id)
        if not provider:
            return False
        provider.enable()
        self._save_persisted()
        return True

    def disable(self, provider_id: str) -> bool:
        provider = self._providers.get(provider_id)
        if not provider:
            return False
        provider.disable()
        self._save_persisted()
        return True

    def is_enabled(self, provider_id: str) -> bool:
        provider = self._providers.get(provider_id)
        return provider.enabled if provider else False

    # -- Capability Routing -------------------------------------------------

    def get_providers_for_capability(self, capability: str) -> list[ExecutionProvider]:
        provider_ids = self._capability_index.get(capability, [])
        return [self._providers[pid] for pid in provider_ids if pid in self._providers]

    def has_capability(self, capability: str) -> bool:
        return capability in self._capability_index

    def all_capabilities(self) -> list[str]:
        return list(self._capability_index.keys())

    # -- Persistence --------------------------------------------------------

    def _save_persisted(self) -> None:
        try:
            _PROVIDER_SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
            data = {
                pid: {
                    "enabled": p.enabled,
                    "priority": self._priorities.get(pid, p.priority),
                }
                for pid, p in self._providers.items()
            }
            _PROVIDER_SETTINGS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning("[ProviderRegistry] Failed to persist settings: %s", e)

    def _load_persisted(self) -> None:
        try:
            if _PROVIDER_SETTINGS_FILE.exists():
                data = json.loads(_PROVIDER_SETTINGS_FILE.read_text(encoding="utf-8"))
                for pid, settings in data.items():
                    if pid in self._providers:
                        if not settings.get("enabled", True):
                            self._providers[pid].disable()
                        if "priority" in settings:
                            self._priorities[pid] = settings["priority"]
                    else:
                        self._pending_settings[pid] = settings
        except Exception as e:
            logger.warning("[ProviderRegistry] Failed to load persisted settings: %s", e)


provider_registry = ProviderRegistry()
