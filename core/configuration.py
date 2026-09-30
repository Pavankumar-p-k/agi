"""Central configuration access.

A minimal in-process key/value store. Values set here win over defaults;
callers supply sensible defaults via ``get(key, default)``.
"""
from __future__ import annotations

from typing import Any


class Configuration:
    """Process-wide configuration registry."""

    def __init__(self) -> None:
        self._values: dict[str, Any] = {}

    def get(self, key: str, default: Any = None) -> Any:
        return self._values.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._values[key] = value

    def delete(self, key: str) -> None:
        self._values.pop(key, None)

    def clear(self) -> None:
        self._values.clear()


configuration = Configuration()
