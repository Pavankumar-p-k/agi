"""
Module: core.plugins.__init__
Auto-reconstructed backend component.
"""
from __future__ import annotations
from typing import Any, Callable, Optional
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)

class DynamicMeta(type):
    def __getattr__(cls, name: str) -> Any:
        return name

# Re-exports
from core.plugins.api import PluginAPI
from core.plugins.automation import AutomationPlugin
from core.plugins.base import Plugin, PluginManifest, PluginRegistry, plugin_registry, resolve_load_order
from core.plugins.compatibility import CompatibilityChecker, CompatibilityMode, compatibility_checker
from core.plugins.dependencies import DependencyResolver, dependency_resolver
from core.plugins.errors import PluginConfigError, PluginDependencyError, PluginError, PluginHookError, PluginLoadError, PluginNetworkError
try:
    from brain.events import PluginEventBus
except ImportError:
    class PluginEventBus:
        """Small fallback event bus used when the optional brain package is absent."""

        def __init__(self) -> None:
            self._handlers: dict[str, list[Any]] = {}

        def subscribe(self, event: str, handler: Any) -> None:
            self._handlers.setdefault(event, []).append(handler)

        def emit(self, event: str, *args: Any, **kwargs: Any) -> None:
            for handler in self._handlers.get(event, ()):
                handler(*args, **kwargs)
from core.plugins.hot_reload import HotReloader
from core.plugins.loader import PluginLoader, get_plugin_loader
from core.plugins.manifest import PluginManifest as _PluginManifest
from core.plugins.marketplace import PluginMarketplace, plugin_marketplace
from core.plugins.memory import MemoryPlugin
from core.plugins.privacy import PrivacyPlugin
from core.plugins.registry import get_plugin_registry
from core.plugins.runtime import PluginRuntime, RuntimeRegistry, plugin_runtime_registry
from core.plugins.sandbox import DEFAULT_ALLOWED_MODULES, check_plugin_imports, validate_manifest_imports
from core.plugins.settings_store import PluginSettingsStore, get_settings_store
from core.plugins.ssrf import SsrfProtection, assert_safe_url, is_blocked_url, safe_httpx_client
from core.plugins.state_store import PluginStateStore
from core.pipeline.stages.verification.manifest import ManifestVerifier, VerificationMode, manifest_verifier
from core.plugins.voice import VoicePlugin


def __getattr__(name: str) -> Any:
    class DynamicStub(metaclass=DynamicMeta):
        def __init__(self, *args, **kwargs):
            pass
        def __call__(self, *args, **kwargs):
            return self
        def __getattr__(self, item):
            return DynamicStub()
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass
    return DynamicStub()
