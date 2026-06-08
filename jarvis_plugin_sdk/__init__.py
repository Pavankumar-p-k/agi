from __future__ import annotations

from typing import Any, Callable, TypeVar

T = TypeVar("T", bound=Callable[..., Any])

try:
    from core.plugins.base import Plugin as _CorePlugin, PluginManifest as _PluginManifest
    from core.plugins.base import PluginRegistry
    from core.plugins.events import PluginEventBus
    _HAVE_CORE = True
except ImportError:
    _HAVE_CORE = False
    PluginRegistry = None  # type: ignore
    PluginEventBus = None  # type: ignore

_registry: Any | None = None


def get_registry() -> Any | None:
    global _registry
    if _registry is None and _HAVE_CORE:
        from core.plugins.base import plugin_registry
        _registry = plugin_registry
    return _registry


def get_event_bus() -> Any | None:
    if _HAVE_CORE:
        from core.plugins.events import PluginEventBus
        return PluginEventBus.instance()
    return None


def hook(name: str):
    """Decorator to mark a method as a JARVIS hook handler.

    Example:
        @hook("message_received")
        async def on_message(self, message: dict) -> dict:
            ...
    """
    def decorator(func: T) -> T:
        func._jarvis_hook = name
        return func
    return decorator


if _HAVE_CORE:

    class Plugin(_CorePlugin):
        """Base class for JARVIS plugins (wraps core.plugins.base.Plugin).

        Provides backward compatibility with the SDK-style ``name``, ``description``,
        ``version``, ``author`` attributes and the ``@hook`` decorator.
        """

        name: str = ""
        description: str = ""
        version: str = "0.1.0"
        author: str = ""

        def __init__(self, manifest: _PluginManifest | None = None):
            if manifest is None:
                manifest = _PluginManifest(
                    name=self.name or self.__class__.__name__,
                    version=self.version,
                    description=self.description,
                    author=self.author,
                    hooks=self._collect_hooks(),
                )
            super().__init__(manifest)
            self._merge_jarvis_hooks()

        def _collect_hooks(self) -> list[str]:
            hooks: list[str] = []
            for attr_name in dir(self):
                attr = getattr(self, attr_name, None)
                hook_name = getattr(attr, "_jarvis_hook", None)
                if hook_name:
                    hooks.append(hook_name)
            return hooks

        def _merge_jarvis_hooks(self) -> None:
            for attr_name in dir(self):
                attr = getattr(self, attr_name, None)
                hook_name = getattr(attr, "_jarvis_hook", None)
                if hook_name and hook_name not in self.manifest.hooks:
                    self.manifest.hooks.append(hook_name)

    PluginManifest = _PluginManifest

else:

    class Plugin:
        """Standalone base class for JARVIS plugins (no core runtime).

        Used when the SDK is imported outside the JARVIS application.
        When running inside JARVIS, the full ``core.plugins.base.Plugin``
        class is used instead, providing tool registration, HTTP routes,
        lifecycle hooks, and more.
        """

        name: str = ""
        description: str = ""
        version: str = "0.1.0"
        author: str = ""

        def __init__(self):
            self._hooks: list[str] = self._collect_hooks()

        def _collect_hooks(self) -> list[str]:
            hooks: list[str] = []
            for attr_name in dir(self):
                attr = getattr(self, attr_name, None)
                hook_name = getattr(attr, "_jarvis_hook", None)
                if hook_name:
                    hooks.append(hook_name)
            return hooks

        def on_load(self) -> None:
            pass

        def on_unload(self) -> None:
            pass


__all__ = [
    "Plugin",
    "hook",
    "get_registry",
    "get_event_bus",
]

if _HAVE_CORE:
    __all__ += ["PluginManifest", "PluginRegistry", "PluginEventBus"]
