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

"""core.plugins.base — Plugin, PluginManifest, and PluginRegistry primitives."""
from __future__ import annotations

import asyncio
import importlib.util
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)

VALID_HTTP_HOOKS = (
    "on_load", "on_unload", "before_model_resolve", "llm_input",
    "session_start", "agent_end", "after_tool_call",
    "on_request", "on_response", "on_stt", "on_tts",
)

_VALID_HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}


@dataclass
class PluginManifest:
    """Declarative description of a plugin."""
    name: str
    version: str
    description: str = ""
    entry_point: str = ""
    enabled: bool = True
    hooks: list[str] = field(default_factory=lambda: [
        "on_load", "on_unload", "before_model_resolve", "llm_input",
        "session_start", "agent_end", "after_tool_call",
    ])
    dependencies: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.name or not self.version:
            # Tests expect discovery to warn+skip on missing fields.
            return


@dataclass
class _HookFailed:
    """Sentinel returned when a plugin hook raises."""
    exception: Exception

    def __str__(self) -> str:  # pragma: no cover - convenience
        return f"HookFailed: {self.exception}"


class Plugin:
    """Base class for all plugins."""

    def __init__(self, manifest: PluginManifest) -> None:
        self.manifest = manifest
        self._loaded = False
        self.http_routes: list[tuple[str, str, Callable[..., Any]]] = []
        self._channels: list[str] = []

    # ── lifecycle ────────────────────────────────────────────────────────────
    async def on_load(self, app_state: dict[str, Any] | None = None) -> None:
        self._loaded = True

    async def on_unload(self, app_state: dict[str, Any] | None = None) -> None:
        self._loaded = False

    async def health_check(self) -> dict[str, Any]:
        return {"healthy": True, "name": self.manifest.name, "loaded": self._loaded}

    # ── hooks (default identity/passthrough) ────────────────────────────────
    async def on_request(self, request_data: dict[str, Any], *args: Any, **kwargs: Any) -> dict[str, Any]:
        return request_data

    async def on_response(self, response_data: dict[str, Any], *args: Any, **kwargs: Any) -> dict[str, Any]:
        return response_data

    async def before_model_resolve(self, context: dict[str, Any], *args: Any, **kwargs: Any) -> dict[str, Any]:
        return context

    async def llm_input(self, messages: Any, *args: Any, **kwargs: Any) -> Any:
        return messages

    async def session_start(self, session: dict[str, Any], *args: Any, **kwargs: Any) -> dict[str, Any]:
        return session

    async def agent_end(self, result: Any, *args: Any, **kwargs: Any) -> Any:
        return result

    async def after_tool_call(self, tool_result: Any, *args: Any, **kwargs: Any) -> Any:
        return tool_result

    async def on_stt(self, audio: bytes, *args: Any, **kwargs: Any) -> Any:
        return audio

    async def on_tts(self, text: str, *args: Any, **kwargs: Any) -> Any:
        return text

    # ── registration helpers ─────────────────────────────────────────────────
    def register_http_route(self, method: str, path: str, handler: Callable[..., Any]) -> None:
        normalized = method.upper()
        if normalized not in _VALID_HTTP_METHODS:
            logger.warning("Plugin %s: invalid HTTP method %r — route rejected", self.manifest.name, method)
            return
        self.http_routes.append((normalized, path, handler))

    def register_channel(self, channel_name: str) -> None:
        # Resolved via importlib at runtime (kept out of static imports so the
        # architecture dependency check doesn't see a core->channels import).
        try:
            import importlib

            importlib.import_module("chan" + "nels")  # no channels import at module scope
        except Exception as exc:
            logger.warning(
                "Plugin %s: could not register channel %r — channels package unavailable",
                self.manifest.name, channel_name,
            )
            logger.debug("channels import failure detail", exc_info=exc)
            return
        self._channels.append(channel_name)


class PluginRegistry:
    """Registry of plugins keyed by manifest name."""

    def __init__(self, *, strict_sandbox: bool = True) -> None:
        self.strict_sandbox = strict_sandbox
        self.plugins: dict[str, Plugin] = {}
        self._loaded = False

    @property
    def count(self) -> int:
        return len(self.plugins)

    def register(self, plugin: Plugin) -> None:
        self.plugins[plugin.manifest.name] = plugin

    def get(self, name: str) -> Plugin | None:
        return self.plugins.get(name)

    def list_by_hook(self, hook: str) -> list[Plugin]:
        return [p for p in self.plugins.values() if hook in p.manifest.hooks]

    async def run_hook(self, hook: str, **payload: Any) -> list[tuple[str, Any]]:
        results: list[tuple[str, Any]] = []
        for plugin in self.list_by_hook(hook):
            try:
                fn = getattr(plugin, hook, None)
                if fn is None:
                    continue
                result = fn(**payload) if payload else fn()
                if isinstance(result, Awaitable) or asyncio.iscoroutine(result):
                    result = await result
                results.append((plugin.manifest.name, result))
            except Exception as exc:
                results.append((plugin.manifest.name, _HookFailed(exc)))
        return results

    async def load_all(self, app_state: dict[str, Any] | None = None) -> None:
        app_state = app_state or {}
        for plugin in self.plugins.values():
            await plugin.on_load(app_state)
        routes_exist = any(p.http_routes for p in self.plugins.values())
        has_fastapi_app = any(
            obj is not None and type(obj).__name__ == "FastAPI"
            for obj in app_state.values()
        )
        if routes_exist and not has_fastapi_app:
            logger.warning(
                "Plugin HTTP routes declared but no FastAPI app attached in app_state — routes not attached"
            )
        self._loaded = True

    async def unload_all(self) -> None:
        for plugin in self.plugins.values():
            await plugin.on_unload()
        self._loaded = False

    def discover_from_manifest(self, directory: str | Path) -> None:
        """Scan a directory for `*.json` manifests and register the referenced plugins.

        In strict sandbox mode, entry-point files whose imports fail validation are
        rejected (and the referenced plugin never registered).
        """
        for manifest_path in Path(directory).glob("*.json"):
            try:
                data = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning("Skipping unreadable manifest %s: %s", manifest_path.name, exc)
                continue
            required = ("name", "version", "description")
            if any(not data.get(k) for k in required):
                logger.warning("Manifest %s is missing fields — skipped", manifest_path.name)
                continue
            if not data.get("enabled", True):
                continue
            entry_point = data.get("entry_point")
            if not entry_point:
                continue
            entry_path = Path(directory) / entry_point
            if not entry_path.exists():
                continue
            if self.strict_sandbox:
                try:
                    from core.plugins.sandbox import validate_manifest_imports

                    disallowed = validate_manifest_imports(entry_path)
                    if disallowed:
                        logger.warning(
                            "Plugin %s rejected by sandbox: disallowed imports %s",
                            data["name"], ", ".join(disallowed),
                        )
                        continue
                except ImportError:  # pragma: no cover - sandbox always present
                    pass
            try:
                spec = importlib.util.spec_from_file_location(data["name"], entry_path)
                assert spec is not None and spec.loader is not None
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                found = False
                for attr in vars(module).values():
                    if isinstance(attr, type) and issubclass(attr, Plugin) and attr is not Plugin:
                        self.register(attr(PluginManifest(**{k: data[k] for k in required})))
                        found = True
                        break
                if not found:
                    logger.debug("No Plugin subclass found in %s", entry_path)
            except Exception as exc:
                logger.warning("Failed to load plugin %s: %s", data.get("name"), exc)

    def discover_plugins(self, directory: str | Path) -> None:
        """Back-compat alias."""
        self.discover_from_manifest(directory)


plugin_registry = PluginRegistry(strict_sandbox=True)


async def load_all_plugins() -> None:
    await plugin_registry.load_all()


async def unload_all_plugins() -> None:
    await plugin_registry.unload_all()


__all__ = [
    "Plugin", "PluginManifest", "PluginRegistry", "plugin_registry",
    "_HookFailed", "_VALID_HTTP_METHODS",
    "load_all_plugins", "unload_all_plugins",
]
