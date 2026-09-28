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


__all__ = ["ConfigEntry", "_REGISTRY", "register", "get"]
