from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jarvis_os.memory.memory_manager import MemoryManager as CanonicalMemoryManager


@dataclass
class _CompatConfig:
    data_dir: str
    short_term_limit: int = 200


class AIOSMemoryAdapter:
    """
    Legacy ai_os memory adapter delegated to canonical memory authority.
    """

    def __init__(self, config: Any | None = None):
        cfg = config or object()
        data_dir = str(getattr(cfg, "data_dir", Path(getattr(cfg, "sqlite_path", "data/ai_os_memory.db")).parent))
        short_term = int(getattr(cfg, "short_term_limit", 200))
        self._memory = CanonicalMemoryManager(_CompatConfig(data_dir=data_dir, short_term_limit=short_term))

    def save_short_term(self, event: dict[str, Any]) -> None:
        self._memory.remember("short_term", str(event), event)

    def get_short_term(self) -> list[dict[str, Any]]:
        return self._memory.recent(kinds=["short_term"], limit=200)

    def clear_short_term(self) -> None:
        return None

    def persist(self, obj_type: str, payload: dict[str, Any]) -> None:
        self._memory.remember(obj_type, str(payload), payload)

    def query(self, obj_type: str, limit: int = 100) -> list[dict[str, Any]]:
        return self._memory.recent(kinds=[obj_type], limit=limit)


MemoryManager = AIOSMemoryAdapter
