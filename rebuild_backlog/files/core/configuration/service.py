"""Configuration Service."""
from __future__ import annotations
from typing import Any
from dataclasses import dataclass, field


class ConfigurationService:
    def __init__(self, data: dict[str, Any] | None = None):
        self._data = data or {}

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    def load(self) -> None:
        pass

    def as_dict(self) -> dict[str, Any]:
        return dict(self._data)


configuration = ConfigurationService()
