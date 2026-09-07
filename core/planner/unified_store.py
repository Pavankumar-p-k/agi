"""Unified Planner Store."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


class UnifiedStore:
    def __init__(self, **kwargs):
        self.store = {}

    def get(self, key: str, default: Any = None) -> Any:
        return self.store.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self.store[key] = value
