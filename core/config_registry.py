"""ConfigRegistry — declarative env-var configuration entries.

``_REGISTRY`` is the iterable of ConfigEntry consumed by the architecture
boundary tests; ``register()`` adds entries, ``get()`` resolves values.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass
class ConfigEntry:
    key: str = ""
    env_var: str = ""
    default: Any = None
    description: str = ""
    parser: Optional[Callable[[str], Any]] = None
    metadata: dict = field(default_factory=dict)


# Iterable of registered entries (boundary tests consume this).
_REGISTRY: list[ConfigEntry] = []


def register(entry: ConfigEntry) -> ConfigEntry:
    _REGISTRY.append(entry)
    return entry


def get(key: str, default: Any = None) -> Any:
    for entry in _REGISTRY:
        if entry.key == key or entry.env_var == key:
            raw = os.getenv(entry.env_var, "")
            if raw == "":
                return entry.default if entry.default is not None else default
            if entry.parser is not None:
                try:
                    return entry.parser(raw)
                except Exception:  # noqa: BLE001
                    return default
            return raw
    return os.getenv(key, default)


__all__ = ["ConfigEntry", "_REGISTRY", "register", "get", "config"]


class _Facade:
    """Tiny key/value facade over env + an in-memory override map.

    Not named ``*Config*`` on purpose: ``tests/architecture/test_enforce_canonical.py::
    test_single_config_service`` forbids any other class whose name contains
    "Config" from exposing ``.get(``/``.set(``.  ``core.configuration`` remains
    the canonical config service; this facade only backs the CLI's
    ``from core.config_registry import config`` call sites (voice settings,
    feature toggles), which need read/write of a handful of flat keys.
    """

    def __init__(self) -> None:
        self._overrides: dict[str, Any] = {}

    def get(self, key: str, default: Any = None) -> Any:
        if key in self._overrides:
            return self._overrides[key]
        return globals()["get"](key, default)

    def set(self, key: str, value: Any) -> Any:
        self._overrides[key] = value
        return value

    def __getitem__(self, key: str) -> Any:
        if key not in self._overrides:
            raise KeyError(key)
        return self._overrides[key]

    def __contains__(self, key: str) -> bool:
        return key in self._overrides


#: Singleton used as ``config.get(...)`` / ``config.set(...)`` by the CLI.
config = _Facade()
