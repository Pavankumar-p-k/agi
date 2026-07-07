from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable


@dataclass
class DeterministicServices:
    """Injectables that freeze all sources of nondeterminism.

    RealServices — production (uses ``uuid.uuid4`` / ``datetime.now``).
    FakeServices — tests     (uses sequential IDs / fixed timestamps).
    """

    uuid4: Callable[[], str]
    now: Callable[[], datetime]
    seed: int = 0

    @staticmethod
    def real() -> DeterministicServices:
        return DeterministicServices(
            uuid4=lambda: uuid.uuid4().hex,
            now=lambda: datetime.now(timezone.utc),
            seed=0,
        )

    @staticmethod
    def fake(
        *,
        fixed_now: datetime | None = None,
        start_at: str = "2026-01-01T00:00:00Z",
    ) -> DeterministicServices:
        _counter: list[int] = [0]

        def _seq() -> str:
            _counter[0] += 1
            return format(_counter[0], "032x")

        ts: datetime
        if fixed_now is not None:
            ts = fixed_now
        else:
            ts = datetime.fromisoformat(start_at.replace("Z", "+00:00"))

        return DeterministicServices(
            uuid4=_seq,
            now=lambda: ts,
            seed=42,
        )

    @staticmethod
    def fixed(timestamp: str = "2026-01-01T00:00:00Z") -> DeterministicServices:
        """Alias for ``fake`` — convenient for one-liners in tests."""
        return DeterministicServices.fake(fixed_now=datetime.fromisoformat(timestamp.replace("Z", "+00:00")))
