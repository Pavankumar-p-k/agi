"""DeterministicServices — injectable deterministic primitives for tests."""
from __future__ import annotations

import uuid
from typing import Any, Callable


class DeterministicServices:
    """Source of IDs/time with a .fake() preset for deterministic tests."""

    def __init__(self, uuid_fn: Callable[[], str] | None = None, clock: Any = None):
        self._uuid_fn = uuid_fn
        self._clock = clock

    @classmethod
    def fake(cls) -> "DeterministicServices":
        """Deterministic UUID4s derived from a counter (stable per test run)."""
        counter = {"n": 0}

        def _uuid4() -> str:
            counter["n"] += 1
            return uuid.uuid5(uuid.NAMESPACE_OID, f"fake-{counter['n']}").hex

        return cls(uuid_fn=_uuid4)

    @classmethod
    def fixed(cls) -> "DeterministicServices":
        """Fully deterministic preset: fixed seed ids, frozen clock."""
        counter = {"n": 0}

        def _uuid4() -> str:
            counter["n"] += 1
            return uuid.uuid5(uuid.NAMESPACE_OID, f"fixed-{counter['n']}").hex

        return cls(uuid_fn=_uuid4, clock=lambda: 1_700_000_000.0)

    def uuid4(self) -> str:
        if self._uuid_fn is not None:
            return str(self._uuid_fn())
        return uuid.uuid4().hex

    def now(self) -> float:
        if self._clock is not None:
            return self._clock()
        import time
        return time.time()


__all__ = ["DeterministicServices"]
