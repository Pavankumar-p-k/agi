"""brain/memory/base.py
MemoryProvider ABC — common interface for all memory types.
"""

from abc import ABC, abstractmethod
from typing import Any


class MemoryProvider(ABC):
    @abstractmethod
    def count(self) -> int:
        ...

    @abstractmethod
    def clear(self) -> int:
        """Delete all entries. Returns count of deleted items."""
        ...

    def get_recent(self, limit: int = 20) -> list[dict]:
        """Return most recent entries. Optional — subclasses may override."""
        return []

    def maintenance(self) -> int:
        """Run maintenance (decay, summarization, etc.). Returns items affected."""
        return 0
