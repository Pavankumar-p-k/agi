from __future__ import annotations

from typing import Any, Optional


class TemporalMemoryCore:
    """
    Stub for hot/warm/cold tiered temporal memory.
    """

    def __init__(self) -> None:
        self._store: dict[str, Any] = {}

    async def store(self, key: str, value: Any, tier: str = "hot") -> None:
        self._store[f"{tier}:{key}"] = value

    async def recall(self, key: str, tier: Optional[str] = None) -> Optional[Any]:
        if tier:
            return self._store.get(f"{tier}:{key}")
        for k, v in self._store.items():
            if k.endswith(f":{key}"):
                return v
        return None

    async def remember(self, data: Any) -> None:
        import json, time
        key = f"mem_{int(time.time())}"
        self._store[f"warm:{key}"] = data

    def status(self) -> dict[str, Any]:
        return {"entries": len(self._store), "tiers": ["hot", "warm", "cold"]}
