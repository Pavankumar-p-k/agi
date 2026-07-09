# Copyright (c) 2024-2026 JARVIS Project
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from core.plugins.api import PluginAPI
from core.plugins.automation import AutomationPlugin
from core.plugins.base import Plugin, PluginManifest, PluginRegistry, plugin_registry, resolve_load_order
from core.plugins.compatibility import CompatibilityChecker, CompatibilityMode, compatibility_checker
from core.plugins.dependencies import DependencyResolver, dependency_resolver
from core.plugins.errors import (
    PluginConfigError,
    PluginDependencyError,
    PluginError,
    PluginHookError,
    PluginLoadError,
    PluginNetworkError,
)
from core.event_bus import PluginEventBus
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

__all__ = [
    "Plugin", "PluginManifest", "PluginRegistry", "plugin_registry", "resolve_load_order",
    "VoicePlugin", "AutomationPlugin", "PrivacyPlugin", "MemoryPlugin",
    "PluginAPI",
    "check_plugin_imports", "validate_manifest_imports", "DEFAULT_ALLOWED_MODULES",
    "PluginEventBus",
    "HotReloader",
    "PluginStateStore",
    "is_blocked_url", "assert_safe_url", "safe_httpx_client", "SsrfProtection",
    "PluginError", "PluginLoadError", "PluginConfigError", "PluginHookError",
    "PluginNetworkError", "PluginDependencyError",
    "PluginLoader", "get_plugin_loader",
    "PluginSettingsStore", "get_settings_store",
    "get_plugin_registry",
    "PluginRuntime",
    "plugin_runtime_registry",
    "RuntimeRegistry",
    "DependencyResolver", "dependency_resolver",
    "CompatibilityChecker", "CompatibilityMode", "compatibility_checker",
    "ManifestVerifier", "VerificationMode", "manifest_verifier",
    "PluginMarketplace", "plugin_marketplace",
]
