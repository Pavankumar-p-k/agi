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
from __future__ import annotations

import asyncio
import importlib.util
import inspect
import json
import logging
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.plugins.types import ChannelPlugin

    from core.plugins.api import PluginAPI

_VALID_HTTP_METHODS = {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"}


class _HookFailed:
    def __init__(self, exception: Exception):
        self.exception = exception

    def __repr__(self) -> str:
        return f"_HookFailed({self.exception!r})"


logger = logging.getLogger(__name__)


class _PluginRecord:
    __slots__ = ("manifest", "module")
    def __init__(self, manifest, module):
        self.manifest = manifest
        self.module = module


@dataclass
class PluginManifest:
    name: str
    version: str
    description: str
    author: str = ""
    entry_point: str = ""
    enabled: bool = True
    config_schema: dict | None = None
    dependencies: list[str] = field(default_factory=list)
    hooks: list[str] = field(default_factory=lambda: [
        "on_load", "on_unload",
        "before_model_resolve", "model_call_started", "model_call_ended",
        "llm_input", "llm_output",
        "agent_turn_prepare", "before_agent_start", "before_agent_reply",
        "before_agent_finalize", "agent_end", "before_agent_run",
        "message_received", "message_sending", "message_sent",
        "before_dispatch", "reply_dispatch", "reply_payload_sending",
        "session_start", "session_end",
        "before_compaction", "after_compaction", "before_reset",
        "after_tool_call", "tool_result_persist",
        "before_message_write",
        "on_request", "on_response",
    ])

    def __hash__(self) -> int:
        return hash(self.name)


_DEPENDENCY_GRAPH_CACHE: dict[tuple, list[str]] = {}


def resolve_load_order(plugins: dict) -> list[str]:
    cache_key = tuple(sorted(plugins.keys()))
    if cache_key in _DEPENDENCY_GRAPH_CACHE:
        return _DEPENDENCY_GRAPH_CACHE[cache_key]

    graph: dict[str, list[str]] = {}
    for name, p in plugins.items():
        manifest = p.manifest if isinstance(p, _PluginRecord) else p.manifest
        deps = getattr(manifest, 'dependencies', None) or getattr(manifest, 'requires', None) or []
        graph[name] = list(deps)

    sorted_names: list[str] = []
    visited: set[str] = set()
    in_progress: set[str] = set()

    def _visit(node: str) -> None:
        if node in in_progress:
            logger.warning("[Dependency] Circular dependency detected: %s", node)
            return
        if node in visited:
            return
        in_progress.add(node)
        for dep in graph.get(node, []):
            if dep in graph:
                _visit(dep)
            elif dep not in plugins:
                logger.warning("[Dependency] Plugin %s depends on %s which is not registered", node, dep)
        in_progress.discard(node)
        visited.add(node)
        sorted_names.append(node)

    for name in plugins:
        _visit(name)

    _DEPENDENCY_GRAPH_CACHE[cache_key] = sorted_names
    return sorted_names


class Plugin:
    manifest: PluginManifest

    def __init__(self, manifest: PluginManifest):
        self.manifest = manifest
        self._loaded = False
        self._config: dict = {}
        self._tools: dict[str, dict] = {}
        self._http_routes: list[tuple[str, str, Callable]] = []
        self._providers: list[dict] = []
        self._services: dict[str, Any] = {}
        self._channels: list[ChannelPlugin] = []
        self._api: PluginAPI | None = None
        self._enabled: bool = manifest.enabled
        self._load_attempts: int = 0
        self._last_error: str | None = None

    @property
    def enabled(self) -> bool:
        return self._enabled

    def enable(self) -> None:
        self._enabled = True

    def disable(self) -> None:
        self._enabled = False

    async def on_load(self, app_state: dict | None = None) -> None:
        self._loaded = True
        self._load_attempts += 1
        self._last_error = None
        logger.info("[Plugin] %s v%s loaded", self.manifest.name, self.manifest.version)

    async def on_unload(self) -> None:
        self._loaded = False
        logger.info("[Plugin] %s unloaded", self.manifest.name)

    async def on_request(self, request_data: dict) -> dict:
        return request_data

    async def on_response(self, response_data: dict) -> dict:
        return response_data

    async def before_model_resolve(self, model_role: str, task: str) -> str:
        return model_role

    async def model_call_started(self, model: str, messages: list, **kwargs) -> None:
        pass

    async def model_call_ended(self, model: str, response: str, duration: float) -> None:
        pass

    async def llm_input(self, messages: list) -> list:
        return messages

    async def llm_output(self, response: str) -> str:
        return response

    async def agent_turn_prepare(self, context: dict) -> dict:
        return context

    async def before_agent_start(self, task: str) -> bool:
        return True

    async def before_agent_reply(self, reply: str) -> str:
        return reply

    async def before_agent_finalize(self, context: dict) -> None:
        pass

    async def agent_end(self, result: dict) -> None:
        pass

    async def before_agent_run(self, task: str) -> bool:
        return True

    async def message_received(self, message: dict) -> dict:
        return message

    async def message_sending(self, message: dict) -> dict:
        return message

    async def message_sent(self, message: dict) -> None:
        pass

    async def before_dispatch(self, message: dict) -> dict | None:
        return message

    async def reply_dispatch(self, reply: dict, channel: str) -> dict:
        return reply

    async def reply_payload_sending(self, payload: dict) -> dict:
        return payload

    async def session_start(self, session_id: str, metadata: dict) -> None:
        pass

    async def session_end(self, session_id: str, summary: dict) -> None:
        pass

    async def before_compaction(self, context: dict) -> dict:
        return context

    async def after_compaction(self, context: dict) -> None:
        pass

    async def before_reset(self) -> bool:
        return True

    async def after_tool_call(self, action: str, result: dict) -> None:
        pass

    async def tool_result_persist(self, result: dict) -> dict:
        return result

    async def before_message_write(self, message: dict) -> dict:
        return message

    async def health_check(self) -> dict:
        return {
            "name": self.manifest.name,
            "healthy": self._loaded and self._enabled,
            "load_attempts": self._load_attempts,
            "last_error": self._last_error,
        }

    def register_tool(self, name: str, description: str, handler: Callable,
                      input_schema: dict | None = None, category: str = "general") -> None:
        self._tools[name] = {
            "name": name,
            "description": description,
            "handler": handler,
            "input_schema": input_schema or {},
            "category": category,
        }
        logger.debug("[Plugin] %s registered tool: %s", self.manifest.name, name)

    def register_http_route(self, method: str, path: str, handler: Callable) -> None:
        if method.upper() not in _VALID_HTTP_METHODS:
            logger.warning("[Plugin] %s invalid HTTP method %r for route %s", self.manifest.name, method, path)
            return
        self._http_routes.append((method.upper(), path, handler))
        logger.debug("[Plugin] %s registered route: %s %s", self.manifest.name, method.upper(), path)

    def register_provider(self, provider_type: str, name: str,
                          models: list[str], handler: Callable | None = None) -> None:
        self._providers.append({
            "type": provider_type,
            "name": name,
            "models": models,
            "handler": handler,
        })
        logger.debug("[Plugin] %s registered provider: %s/%s", self.manifest.name, provider_type, name)

    def register_service(self, service_id: str, instance: Any) -> None:
        self._services[service_id] = instance
        logger.debug("[Plugin] %s registered service: %s", self.manifest.name, service_id)

    def register_channel(self, channel) -> None:
        try:
            from channels.base import ChannelPlugin
        except ImportError:
            logger.warning("[Plugin] %s cannot register channel: channels package unavailable", self.manifest.name)
            return
        if not isinstance(channel, ChannelPlugin):
            logger.warning("[Plugin] %s invalid channel: expected ChannelPlugin", self.manifest.name)
            return
        self._channels.append(channel)
        logger.debug("[Plugin] %s registered channel: %s", self.manifest.name, channel.id)

    @property
    def api(self) -> PluginAPI:
        if self._api is None:
            from core.plugins.api import PluginAPI
            self._api = PluginAPI(plugin=self)
        return self._api

    @property
    def tools(self) -> dict[str, dict]:
        return dict(self._tools)

    @property
    def http_routes(self) -> list[tuple[str, str, Callable]]:
        return list(self._http_routes)

    @property
    def providers(self) -> list[dict]:
        return list(self._providers)

    @property
    def channels_registered(self) -> list:
        return list(self._channels)


class PluginRegistry:
    def __init__(self, strict_sandbox: bool = False):
        self._plugins: dict[str, Plugin] = {}
        self._loaded: bool = False
        self.strict_sandbox = strict_sandbox
        self._app_state: dict | None = None
        self._route_routers: dict[str, Any] = {}

    @property
    def plugins(self) -> dict[str, Plugin]:
        return dict(self._plugins)

    @property
    def count(self) -> int:
        return len(self._plugins)

    def register(self, *args) -> None:
        if len(args) == 2:
            manifest, module = args
            key = getattr(manifest, 'id', manifest.name)
            self._plugins[key] = _PluginRecord(manifest, module)
            logger.info("[PluginRegistry] Registered: %s v%s", key, manifest.version)
        elif len(args) == 1 and isinstance(args[0], Plugin):
            plugin = args[0]
            key = plugin.manifest.name
            self._plugins[key] = _PluginRecord(plugin.manifest, plugin)
            logger.info("[PluginRegistry] Registered: %s v%s", key, plugin.manifest.version)
        else:
            raise TypeError("register() takes a Plugin, or (PluginManifest, module)")

    def unregister(self, name: str) -> Any:
        record = self._plugins.pop(name, None)
        return record.module if record else None

    def get(self, name: str) -> Any | None:
        record = self._plugins.get(name)
        return record.module if record else None

    def get_manifest(self, plugin_id: str) -> Any | None:
        record = self._plugins.get(plugin_id)
        return record.manifest if record else None

    def list_by_hook(self, hook: str) -> list[Any]:
        return [
            record.module for record in self._plugins.values()
            if record.manifest.enabled and hook in record.manifest.hooks
        ]

    def list_enabled(self) -> list[Any]:
        return [record.module for record in self._plugins.values() if record.manifest.enabled]

    def list_disabled(self) -> list[Any]:
        return [record.module for record in self._plugins.values() if not record.manifest.enabled]

    def list(self) -> list[Any]:
        return [record.module for record in self._plugins.values()]

    def values(self):
        return self._plugins.values()

    async def load_all(self, app_state: dict | None = None) -> None:
        if self._loaded:
            return
        self._app_state = app_state or {}

        order = resolve_load_order(self._plugins)
        loaded_count = 0
        for name in order:
            record = self._plugins.get(name)
            if not record or not record.manifest.enabled:
                continue
            try:
                if hasattr(record.module, 'on_load'):
                    await record.module.on_load(app_state)
                self._mount_plugin_routes(name, record.module)
                loaded_count += 1
            except Exception as e:
                if hasattr(record.module, '_last_error'):
                    record.module._last_error = str(e)
                logger.exception("[PluginRegistry] Failed to load %s: %s", name, e)
        self._loaded = True
        logger.info("[PluginRegistry] %d/%d plugins loaded", loaded_count, self.count)

    async def unload_all(self) -> None:
        for name in reversed(resolve_load_order(self._plugins)):
            record = self._plugins.get(name)
            if not record:
                continue
            try:
                self._unmount_plugin_routes(name)
                if hasattr(record.module, 'on_unload'):
                    await record.module.on_unload()
            except Exception as e:
                logger.exception("[PluginRegistry] Failed to unload %s: %s", name, e)
        self._loaded = False
        logger.info("[PluginRegistry] All plugins unloaded")

    async def enable_plugin(self, name: str, app_state: dict | None = None) -> bool:
        record = self._plugins.get(name)
        if not record:
            logger.warning("[PluginRegistry] Cannot enable %s: not found", name)
            return False
        if record.manifest.enabled:
            return True
        record.manifest.enabled = True
        try:
            if hasattr(record.module, 'on_load'):
                await record.module.on_load(app_state or self._app_state)
            self._mount_plugin_routes(name, record.module)
            logger.info("[PluginRegistry] Enabled %s", name)
            return True
        except Exception as e:
            record.manifest.enabled = False
            logger.exception("[PluginRegistry] Failed to enable %s: %s", name, e)
            return False

    async def disable_plugin(self, name: str) -> bool:
        record = self._plugins.get(name)
        if not record:
            logger.warning("[PluginRegistry] Cannot disable %s: not found", name)
            return False
        if not record.manifest.enabled:
            return True
        self._unmount_plugin_routes(name)
        if hasattr(record.module, 'on_unload'):
            await record.module.on_unload()
        record.manifest.enabled = False
        logger.info("[PluginRegistry] Disabled %s", name)
        return True

    def enable(self, plugin_id: str) -> bool:
        record = self._plugins.get(plugin_id)
        if not record:
            return False
        record.manifest.enabled = True
        logger.info("Plugin enabled: %s", plugin_id)
        return True

    def disable(self, plugin_id: str) -> bool:
        record = self._plugins.get(plugin_id)
        if not record:
            return False
        record.manifest.enabled = False
        logger.info("Plugin disabled: %s", plugin_id)
        return True

    async def reload_plugin(self, name: str, importlib_reload: bool = True) -> bool:
        record = self._plugins.get(name)
        if not record:
            logger.warning("[PluginRegistry] Cannot reload %s: not found", name)
            return False

        self._unmount_plugin_routes(name)
        if hasattr(record.module, 'on_unload'):
            await record.module.on_unload()

        if not importlib_reload:
            try:
                if hasattr(record.module, 'on_load'):
                    await record.module.on_load(self._app_state)
                self._mount_plugin_routes(name, record.module)
                logger.info("[PluginRegistry] Re-initialized %s", name)
                return True
            except Exception as e:
                logger.exception("[PluginRegistry] Failed to re-init %s: %s", name, e)
                return False

        mod_name = record.manifest.name
        mod = sys.modules.get(mod_name) or sys.modules.get(f"plugins.{mod_name}")
        if mod is None:
            logger.warning("[PluginRegistry] Cannot find module for %s", name)
            return False

        try:
            import importlib as _il
            _il.reload(mod)
            new_class = getattr(mod, "Plugin", None)
            if not new_class or not issubclass(new_class, Plugin):
                logger.warning("[PluginRegistry] Reloaded module has no Plugin class for %s", name)
                if hasattr(record.module, 'on_load'):
                    await record.module.on_load(self._app_state)
                self._mount_plugin_routes(name, record.module)
                return False

            new_instance = new_class(record.manifest)
            from core.plugins.api import PluginAPI
            new_instance._api = PluginAPI(plugin=new_instance)
            new_instance._config = dict(getattr(record.module, '_config', {}))
            self._plugins[name] = _PluginRecord(new_instance.manifest, new_instance)
            await new_instance.on_load(self._app_state)
            self._mount_plugin_routes(name, new_instance)
            logger.info("[PluginRegistry] Reloaded %s via importlib.reload", name)
            return True
        except Exception as e:
            logger.exception("[PluginRegistry] Failed to reload %s: %s", name, e)
            try:
                if hasattr(record.module, 'on_load'):
                    await record.module.on_load(self._app_state)
            except Exception as _e:
                logger.debug("plugins base on_load hook failed: %s", _e)
            return False

    def _mount_plugin_routes(self, name: str, module: Any) -> None:
        http_routes = getattr(module, 'http_routes', None) or getattr(module, '_http_routes', None) or []
        if not http_routes:
            return
        app = (self._app_state or {}).get("app")
        if not app:
            logger.warning("[PluginRegistry] Routes for %s not attached: FastAPI app missing in app_state", name)
            return
        from fastapi import APIRouter
        router = APIRouter(prefix=f"/plugins/{name}")
        for method, path, handler in http_routes:
            getattr(router, method.lower())(path)(handler)
        app.include_router(router)
        self._route_routers[name] = router
        logger.info("[PluginRegistry] Mounted %d route(s) for %s", len(http_routes), name)

    def _unmount_plugin_routes(self, name: str) -> None:
        router = self._route_routers.pop(name, None)
        if router is None:
            return
        app = (self._app_state or {}).get("app")
        if app and hasattr(app, "routes"):
            app.routes[:] = [r for r in app.routes if getattr(r, "router", None) is not router]
            logger.debug("[PluginRegistry] Unmounted routes for %s", name)

    # ------------------------------------------------------------------ #
    # Module-plugin API (compatibility with registry.py / loader.py)
    # ------------------------------------------------------------------ #

    def list_plugins(self) -> list[dict]:
        return [
            {
                "id":      getattr(r.manifest, 'id', r.manifest.name),
                "name":    r.manifest.name,
                "version": r.manifest.version,
                "enabled": r.manifest.enabled,
                "hooks":   r.manifest.hooks,
            }
            for r in self._plugins.values()
        ]

    def get_settings(self, plugin_id: str) -> dict:
        from core.plugins.settings_store import get_settings_store
        return get_settings_store().get_all(plugin_id)

    def update_settings(self, plugin_id: str, settings: dict) -> bool:
        record = self._plugins.get(plugin_id)
        if not record:
            logger.warning("update_settings: unknown plugin %s", plugin_id)
            return False
        schema = getattr(record.manifest, 'settings_schema', None) or getattr(record.manifest, 'config_schema', None)
        if schema:
            ok, err = _validate_json_schema(settings, schema)
            if not ok:
                logger.error("Settings validation failed for %s: %s", plugin_id, err)
                return False
        from core.plugins.settings_store import get_settings_store
        get_settings_store().set_all(plugin_id, settings)
        return True

    async def run_hook(self, hook: str, **kwargs: Any) -> list[tuple[str, Any]]:
        results: list[tuple[str, Any]] = []
        for record in list(self._plugins.values()):
            if not record.manifest.enabled or hook not in record.manifest.hooks:
                continue
            hook_fn = getattr(record.module, hook, None)
            if hook_fn is None:
                continue
            try:
                if inspect.iscoroutinefunction(hook_fn):
                    result = await hook_fn(**kwargs)
                else:
                    result = hook_fn(**kwargs)
                rec_id = getattr(record.manifest, 'id', record.manifest.name)
                results.append((rec_id, result))
            except Exception as e:
                logger.exception("[PluginRegistry] Hook %s on %s failed: %s", hook, record.manifest.name, e)
                results.append((record.manifest.name, _HookFailed(e)))

        try:
            from core.plugins.events import PluginEventBus
            asyncio.ensure_future(PluginEventBus.instance().emit(hook, **kwargs))
        except Exception as _e:
            logger.debug("plugins base run_hook event bus failed: %s", _e)

        return results

    def get_tools(self) -> list[dict]:
        tools = []
        for record in self._plugins.values():
            if record.manifest.enabled:
                tls = getattr(record.module, 'tools', None) or getattr(record.module, '_tools', None) or {}
                if callable(tls):
                    tls = tls()
                tools.extend(tls.values() if isinstance(tls, dict) else tls)
        return tools

    def get_providers(self) -> list[dict]:
        providers = []
        for record in self._plugins.values():
            if record.manifest.enabled:
                provs = getattr(record.module, 'providers', None) or getattr(record.module, '_providers', None) or []
                if callable(provs):
                    provs = provs()
                providers.extend(provs)
        return providers

    def discover_from_manifest(self, manifest_dir: str | Path) -> None:
        manifest_dir = Path(manifest_dir)
        if not manifest_dir.is_dir():
            logger.warning("[PluginRegistry] Manifest dir %s not found", manifest_dir)
            return
        for manifest_path in sorted(manifest_dir.glob("*.json")):
            try:
                data = json.loads(manifest_path.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    logger.warning("[PluginRegistry] Manifest %s is not a JSON object", manifest_path)
                    continue
                required = {"name", "version", "description"}
                missing = required - set(data.keys())
                if missing:
                    logger.warning("[PluginRegistry] Manifest %s missing fields: %s", manifest_path, ", ".join(sorted(missing)))
                    continue
                manifest = PluginManifest(**data)
                if not manifest.enabled:
                    logger.info("[PluginRegistry] Skipping disabled plugin: %s", manifest.name)
                    continue
                plugin = self._load_from_manifest(manifest, manifest_path.parent, strict_sandbox=self.strict_sandbox)
                if plugin:
                    self.register(plugin)
            except Exception as e:
                logger.exception("[PluginRegistry] Failed to load manifest %s: %s", manifest_path, e)

    def _load_from_manifest(self, manifest: PluginManifest, base_dir: Path, strict_sandbox: bool = False) -> Plugin | None:
        if not manifest.entry_point:
            logger.warning("[PluginRegistry] No entry_point for %s", manifest.name)
            return None
        entry_path = base_dir / manifest.entry_point
        if not entry_path.exists():
            logger.warning("[PluginRegistry] Entry point %s not found for %s", entry_path, manifest.name)
            return None

        from core.plugins.sandbox import validate_manifest_imports
        disallowed = validate_manifest_imports(str(entry_path))
        if disallowed:
            msg = f"[PluginRegistry] {manifest.name} uses disallowed imports: {', '.join(disallowed)}"
            if strict_sandbox:
                logger.error(msg)
                return None
            logger.warning(msg + " (loading anyway)")

        try:
            spec = importlib.util.spec_from_file_location(manifest.name, entry_path)
            if not spec or not spec.loader:
                logger.warning("[PluginRegistry] Could not load spec for %s", manifest.name)
                return None
            mod = importlib.util.module_from_spec(spec)
            sys.modules[manifest.name] = mod
            spec.loader.exec_module(mod)
            plugin_class = getattr(mod, "Plugin", None)
            if plugin_class and issubclass(plugin_class, Plugin):
                plugin_instance = plugin_class(manifest)
                from core.plugins.api import PluginAPI
                plugin_instance._api = PluginAPI(plugin=plugin_instance)
                logger.info("[PluginRegistry] Loaded plugin from %s: %s", entry_path, manifest.name)
                return plugin_instance
            logger.warning("[PluginRegistry] No Plugin class found in %s", entry_path)
        except Exception as e:
            logger.exception("[PluginRegistry] Error loading %s from %s: %s", manifest.name, entry_path, e)
        return None


# ------------------------------------------------------------------ #
# JSON Schema mini-validator (no external deps)
# ------------------------------------------------------------------ #

def _validate_json_schema(data: dict, schema: dict) -> tuple[bool, str]:
    required = schema.get("required", [])
    properties = schema.get("properties", {})
    for field in required:
        if field not in data:
            return False, f"Missing required field: {field}"
    for key, val in data.items():
        prop_schema = properties.get(key, {})
        expected_type = prop_schema.get("type")
        if expected_type:
            type_map = {"string": str, "integer": int, "number": (int, float), "boolean": bool, "array": list, "object": dict}
            py_type = type_map.get(expected_type)
            if py_type and not isinstance(val, py_type):
                return False, f"Field '{key}' expected {expected_type}, got {type(val).__name__}"
    return True, ""


plugin_registry = PluginRegistry(strict_sandbox=True)
