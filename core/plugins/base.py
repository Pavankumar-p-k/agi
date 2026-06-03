from __future__ import annotations

import importlib.util
import json
import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, TYPE_CHECKING

_VALID_HTTP_METHODS = {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"}


class _HookFailed:
    def __init__(self, exception: Exception):
        self.exception = exception

    def __repr__(self) -> str:
        return f"_HookFailed({self.exception!r})"


logger = logging.getLogger(__name__)


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


def resolve_load_order(plugins: dict[str, Plugin]) -> list[str]:
    cache_key = tuple(sorted(plugins.keys()))
    if cache_key in _DEPENDENCY_GRAPH_CACHE:
        return _DEPENDENCY_GRAPH_CACHE[cache_key]

    graph: dict[str, list[str]] = {}
    for name, p in plugins.items():
        graph[name] = list(p.manifest.dependencies)

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

    def register(self, plugin: Plugin) -> None:
        self._plugins[plugin.manifest.name] = plugin
        logger.info("[PluginRegistry] Registered: %s v%s", plugin.manifest.name, plugin.manifest.version)

    def unregister(self, name: str) -> Plugin | None:
        return self._plugins.pop(name, None)

    def get(self, name: str) -> Plugin | None:
        return self._plugins.get(name)

    def list_by_hook(self, hook: str) -> list[Plugin]:
        return [
            p for p in self._plugins.values()
            if p._enabled and hook in p.manifest.hooks
        ]

    def list_enabled(self) -> list[Plugin]:
        return [p for p in self._plugins.values() if p._enabled]

    def list_disabled(self) -> list[Plugin]:
        return [p for p in self._plugins.values() if not p._enabled]

    async def load_all(self, app_state: dict | None = None) -> None:
        if self._loaded:
            return
        self._app_state = app_state or {}

        order = resolve_load_order(self._plugins)
        loaded_count = 0
        for name in order:
            plugin = self._plugins.get(name)
            if not plugin or not plugin._enabled:
                continue
            try:
                await plugin.on_load(app_state)
                self._mount_plugin_routes(name, plugin)
                loaded_count += 1
            except Exception as e:
                plugin._last_error = str(e)
                logger.exception("[PluginRegistry] Failed to load %s: %s", name, e)
        self._loaded = True
        logger.info("[PluginRegistry] %d/%d plugins loaded", loaded_count, self.count)

    async def unload_all(self) -> None:
        for name in reversed(resolve_load_order(self._plugins)):
            plugin = self._plugins.get(name)
            if not plugin:
                continue
            try:
                self._unmount_plugin_routes(name)
                await plugin.on_unload()
            except Exception as e:
                logger.exception("[PluginRegistry] Failed to unload %s: %s", name, e)
        self._loaded = False
        logger.info("[PluginRegistry] All plugins unloaded")

    async def enable_plugin(self, name: str, app_state: dict | None = None) -> bool:
        plugin = self._plugins.get(name)
        if not plugin:
            logger.warning("[PluginRegistry] Cannot enable %s: not found", name)
            return False
        if plugin._enabled:
            return True
        plugin.enable()
        try:
            await plugin.on_load(app_state or self._app_state)
            self._mount_plugin_routes(name, plugin)
            logger.info("[PluginRegistry] Enabled %s", name)
            return True
        except Exception as e:
            plugin._last_error = str(e)
            plugin.disable()
            logger.exception("[PluginRegistry] Failed to enable %s: %s", name, e)
            return False

    async def disable_plugin(self, name: str) -> bool:
        plugin = self._plugins.get(name)
        if not plugin:
            logger.warning("[PluginRegistry] Cannot disable %s: not found", name)
            return False
        if not plugin._enabled:
            return True
        self._unmount_plugin_routes(name)
        await plugin.on_unload()
        plugin.disable()
        logger.info("[PluginRegistry] Disabled %s", name)
        return True

    async def reload_plugin(self, name: str, importlib_reload: bool = True) -> bool:
        plugin = self._plugins.get(name)
        if not plugin:
            logger.warning("[PluginRegistry] Cannot reload %s: not found", name)
            return False

        self._unmount_plugin_routes(name)
        await plugin.on_unload()

        if not importlib_reload:
            try:
                await plugin.on_load(self._app_state)
                self._mount_plugin_routes(name, plugin)
                logger.info("[PluginRegistry] Re-initialized %s", name)
                return True
            except Exception as e:
                plugin._last_error = str(e)
                logger.exception("[PluginRegistry] Failed to re-init %s: %s", name, e)
                return False

        mod_name = plugin.manifest.name
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
                await plugin.on_load(self._app_state)
                self._mount_plugin_routes(name, plugin)
                return False

            new_instance = new_class(plugin.manifest)
            from core.plugins.api import PluginAPI
            new_instance._api = PluginAPI(plugin=new_instance)
            new_instance._config = dict(plugin._config)
            self._plugins[name] = new_instance
            await new_instance.on_load(self._app_state)
            self._mount_plugin_routes(name, new_instance)
            logger.info("[PluginRegistry] Reloaded %s via importlib.reload", name)
            return True
        except Exception as e:
            logger.exception("[PluginRegistry] Failed to reload %s: %s", name, e)
            try:
                await plugin.on_load(self._app_state)
            except Exception:
                pass
            return False

    def _mount_plugin_routes(self, name: str, plugin: Plugin) -> None:
        if not plugin.http_routes:
            return
        app = (self._app_state or {}).get("app")
        if not app:
            logger.warning("[PluginRegistry] Routes for %s not attached: FastAPI app missing in app_state", name)
            return
        from fastapi import APIRouter
        router = APIRouter(prefix=f"/plugins/{name}")
        for method, path, handler in plugin.http_routes:
            getattr(router, method.lower())(path)(handler)
        app.include_router(router)
        self._route_routers[name] = router
        logger.info("[PluginRegistry] Mounted %d route(s) for %s", len(plugin.http_routes), name)

    def _unmount_plugin_routes(self, name: str) -> None:
        router = self._route_routers.pop(name, None)
        if router is None:
            return
        app = (self._app_state or {}).get("app")
        if app and hasattr(app, "routes"):
            app.routes[:] = [r for r in app.routes if getattr(r, "router", None) is not router]
            logger.debug("[PluginRegistry] Unmounted routes for %s", name)

    async def run_hook(self, hook: str, **kwargs: Any) -> list[tuple[str, Any]]:
        results: list[tuple[str, Any]] = []
        for plugin in self.list_by_hook(hook):
            hook_fn = getattr(plugin, hook, None)
            if hook_fn is None:
                continue
            try:
                result = await hook_fn(**kwargs)
                results.append((plugin.manifest.name, result))
            except Exception as e:
                logger.exception("[PluginRegistry] Hook %s on %s failed: %s", hook, plugin.manifest.name, e)
                results.append((plugin.manifest.name, _HookFailed(e)))
        return results

    def get_tools(self) -> list[dict]:
        tools = []
        for plugin in self._plugins.values():
            if plugin._enabled:
                tools.extend(plugin.tools.values())
        return tools

    def get_providers(self) -> list[dict]:
        providers = []
        for plugin in self._plugins.values():
            if plugin._enabled:
                providers.extend(plugin.providers)
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


plugin_registry = PluginRegistry(strict_sandbox=True)
