from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from core.plugins.state_store import PluginStateStore
from core.plugins.settings_store import get_settings_store, PluginSettingsStore
from core.plugins.ssrf import SsrfProtection, assert_safe_url

logger = logging.getLogger("jarvis.plugins.runtime")


class AuthGuard:
    """Simple auth guard for plugin operations.

    Tracks which operations require approval and validates against
    the current user's permissions.
    """

    def __init__(self):
        self._guarded: Dict[str, str] = {}  # operation -> permission

    def guard(self, operation: str, permission: str = "admin"):
        self._guarded[operation] = permission

    def check(self, operation: str, user_permissions: List[str]) -> bool:
        required = self._guarded.get(operation)
        if required is None:
            return True
        return required in user_permissions


class PluginRuntime:
    """Runtime context for an active plugin.

    Provides access to:
    - In-memory runtime store (scoped per plugin ID)
    - Persistent state store (SQLite-backed)
    - Settings store (JSON-backed)
    - SSRF-protected HTTP client
    - Auth guards for sensitive operations
    """

    def __init__(self, plugin_id: str, config: Optional[dict] = None):
        self.plugin_id = plugin_id
        self.config = config or {}
        self._store: Dict[str, Any] = {}
        self._state: PluginStateStore = PluginStateStore()
        self._settings: PluginSettingsStore = get_settings_store()
        self._ssrf: SsrfProtection = SsrfProtection()
        self._auth: AuthGuard = AuthGuard()

    # ── In-memory store ──

    def store_get(self, key: str, default: Any = None) -> Any:
        return self._store.get(key, default)

    def store_set(self, key: str, value: Any):
        self._store[key] = value

    def store_delete(self, key: str):
        self._store.pop(key, None)

    def store_keys(self) -> List[str]:
        return list(self._store.keys())

    # ── Persistent state (SQLite) ──

    def state_get(self, key: str, default: Any = None) -> Any:
        return self._state.get(self.plugin_id, key, default)

    def state_set(self, key: str, value: Any):
        self._state.set(self.plugin_id, key, value)

    def state_delete(self, key: str) -> bool:
        return self._state.delete(self.plugin_id, key)

    def state_all(self) -> Dict[str, Any]:
        return self._state.get_all(self.plugin_id)

    def state_keys(self) -> List[dict]:
        return self._state.list_keys(self.plugin_id)

    def state_clear(self):
        self._state.clear(self.plugin_id)

    # ── Settings ──

    def settings_get(self, key: str, default: Any = None) -> Any:
        return self._settings.get(self.plugin_id, key, default)

    def settings_set(self, key: str, value: Any):
        self._settings.set(self.plugin_id, key, value)

    def settings_all(self) -> Dict[str, Any]:
        return self._settings.get_all(self.plugin_id)

    # ── SSRF-safe HTTP ──

    def http_client(self, **kwargs) -> Any:
        return self._ssrf.wrap_client(**kwargs)

    def check_url(self, url: str):
        assert_safe_url(url)

    # ── Auth ──

    def guard(self, operation: str, permission: str = "admin"):
        self._auth.guard(operation, permission)

    def check_access(self, operation: str, user_permissions: List[str]) -> bool:
        return self._auth.check(operation, user_permissions)


class RuntimeRegistry:
    """Global registry of active plugin runtimes."""

    def __init__(self):
        self._runtimes: Dict[str, PluginRuntime] = {}

    def register(self, runtime: PluginRuntime):
        self._runtimes[runtime.plugin_id] = runtime
        logger.info("Registered plugin runtime: %s", runtime.plugin_id)

    def get(self, plugin_id: str) -> Optional[PluginRuntime]:
        return self._runtimes.get(plugin_id)

    def unregister(self, plugin_id: str):
        self._runtimes.pop(plugin_id, None)
        logger.info("Unregistered plugin runtime: %s", plugin_id)

    def list(self) -> List[str]:
        return list(self._runtimes.keys())

    def get_all(self) -> Dict[str, PluginRuntime]:
        return dict(self._runtimes)


plugin_runtime_registry = RuntimeRegistry()

__all__ = [
    "plugin_runtime_registry",
    "RuntimeRegistry",
    "PluginRuntime",
    "AuthGuard",
]
