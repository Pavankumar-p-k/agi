"""DEPRECATED — config_registry shim routing to ConfigurationService.

This module is a backward-compatibility shim. All config registry access
should route through `core.configuration.configuration`.

Deprecated: v3.2
Remove after: v4.0
"""
from __future__ import annotations

import warnings
from typing import Any

from core.configuration import configuration as _configuration
from core.config_schema import _REGISTRY as _REGISTRY
from core.config_schema import ConfigEntry as ConfigEntry
from core.config_schema import _REGISTRY_MAP as _REGISTRY_MAP
from core.config_schema import all_categories as all_categories
from core.config_schema import entries_by_category as entries_by_category
from core.config_schema import get_entry as get_entry

_warned = False


def _warn() -> None:
    global _warned
    if not _warned:
        warnings.warn(
            "core.config_registry is deprecated. "
            "Use 'from core.configuration import configuration' instead.",
            DeprecationWarning, stacklevel=3,
        )
        _warned = True


# Re-export the registry for backward compatibility
REGISTRY = _REGISTRY

# Re-export ConfigEntry
ConfigEntry = ConfigEntry


class Config:
    """Backward-compat singleton that delegates to ConfigurationService."""

    def __init__(self):
        _warn()

    def get(self, key: str, default: Any = None) -> Any:
        _warn()
        return _configuration.get(key, default)

    def set(self, key: str, value: Any) -> None:
        _warn()
        _configuration.set(key, value)

    def reset(self, key: str) -> None:
        _warn()
        _configuration.reset(key)

    def reset_all(self) -> None:
        _warn()
        _configuration.reset_all()

    def as_dict(self, category: str | None = None) -> dict:
        _warn()
        return _configuration.as_dict(category)

    def as_api_dict(self, category: str | None = None) -> list[dict]:
        _warn()
        return _configuration.as_api_dict(category)

    def on_change(self, key: str, callback):
        _warn()
        _configuration.on_change(key, callback)

    class _Proxy:
        def __init__(self, config, prefix):
            self._config = config
            self._prefix = prefix

        def __getattr__(self, name):
            full_key = f"{self._prefix}.{name}" if self._prefix else name
            val = self._config.get(full_key)
            if val is None:
                raise AttributeError(f"Config has no key: {full_key}")
            return val

        def __setattr__(self, name, value):
            if name.startswith("_"):
                super().__setattr__(name, value)
            else:
                full_key = f"{self._prefix}.{name}" if self._prefix else name
                self._config.set(full_key, value)

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return self._Proxy(self, name)


# Singleton — NO auto-load at import time. Call config.load() explicitly.
config = Config()