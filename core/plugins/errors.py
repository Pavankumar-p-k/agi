from __future__ import annotations

import traceback
from typing import Any


class PluginError(Exception):
    CATEGORIES = {
        "LOAD": "plugin_load",
        "CONFIG": "plugin_config",
        "HOOK": "plugin_hook",
        "TOOL": "plugin_tool",
        "ROUTE": "plugin_route",
        "STATE": "plugin_state",
        "SECRET": "plugin_secret",
        "NETWORK": "plugin_network",
        "DEPENDENCY": "plugin_dependency",
        "SANDBOX": "plugin_sandbox",
        "RELOAD": "plugin_reload",
        "UNKNOWN": "plugin_unknown",
    }

    def __init__(
        self,
        code: str,
        message: str,
        category: str = "plugin_unknown",
        plugin_name: str | None = None,
        cause: BaseException | None = None,
        details: dict | None = None,
    ):
        self.code = code
        self.category = category
        self.plugin_name = plugin_name
        self.cause = cause
        self.details = details or {}
        super().__init__(self.format_message())

    def format_message(self) -> str:
        parts = [f"[{self.code}] {self.args[0] if self.args else ''}"]
        if self.plugin_name:
            parts.insert(0, f"{self.plugin_name}:")
        if self.cause:
            parts.append(f"(caused by: {type(self.cause).__name__}: {self.cause})")
        return " ".join(parts)

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "message": str(self.args[0]) if self.args else "",
            "category": self.category,
            "plugin": self.plugin_name,
            "details": self.details,
            "traceback": traceback.format_exc() if self.cause else None,
        }


class PluginLoadError(PluginError):
    def __init__(self, message: str, plugin_name: str | None = None, cause: BaseException | None = None):
        super().__init__("PLUGIN_LOAD_FAILED", message, "plugin_load", plugin_name, cause)


class PluginConfigError(PluginError):
    def __init__(self, message: str, plugin_name: str | None = None, details: dict | None = None):
        super().__init__("PLUGIN_CONFIG_ERROR", message, "plugin_config", plugin_name, details=details)


class PluginHookError(PluginError):
    def __init__(self, hook: str, message: str, plugin_name: str | None = None, cause: BaseException | None = None):
        super().__init__("PLUGIN_HOOK_FAILED", f"hook={hook}: {message}", "plugin_hook", plugin_name, cause)
        self.hook = hook


class PluginNetworkError(PluginError):
    def __init__(self, url: str, message: str, plugin_name: str | None = None):
        super().__init__("PLUGIN_NETWORK_BLOCKED", f"{message}: {url}", "plugin_network", plugin_name, details={"url": url})


class PluginDependencyError(PluginError):
    def __init__(self, dependency: str, message: str, plugin_name: str | None = None):
        super().__init__("PLUGIN_DEPENDENCY_ERROR", f"dep={dependency}: {message}", "plugin_dependency", plugin_name)


def format_plugin_error(err: Exception) -> dict:
    if isinstance(err, PluginError):
        return err.to_dict()
    return {
        "code": "UNHANDLED",
        "message": str(err),
        "category": "plugin_unknown",
        "plugin": None,
        "details": {},
        "traceback": traceback.format_exc(),
    }
