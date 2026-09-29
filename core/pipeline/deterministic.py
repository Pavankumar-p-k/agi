"""DeterministicServices — injectable id/clock primitives for the pipeline.

Three presets:
  ``real()``        — wall clock + real UUID4s (production default)
  ``fake()``        — counter-based UUID5s + frozen clock (replay tests)
  ``fixed(when)``   — ``fake()`` pinned to an explicit timestamp
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Optional

#: Timestamp ``fake()``/``fixed()`` freeze on when none is supplied.
DEFAULT_FAKE_NOW = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

#: Seed advertised by the deterministic presets (asserted by tests).
FAKE_SEED = 42


def _as_datetime(when: Any) -> datetime:
    """Coerce an ISO-8601 string / epoch number / datetime into aware UTC."""
    if isinstance(when, datetime):
        return when if when.tzinfo is not None else when.replace(tzinfo=timezone.utc)
    if isinstance(when, str):
        text = when.strip()
        if text.endswith(("Z", "z")):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
    if isinstance(when, (int, float)):
        return datetime.fromtimestamp(float(when), tz=timezone.utc)
    raise TypeError(f"cannot interpret {when!r} as a timestamp")


class DeterministicServices:
    """Source of IDs and time; injectable via ``PipelineContext.services``."""

    def __init__(
        self,
        uuid_fn: Optional[Callable[[], str]] = None,
        clock: Optional[Callable[[], datetime]] = None,
        seed: Optional[int] = None,
    ):
        self._uuid_fn = uuid_fn
        self._clock = clock
        self.seed = seed

    # ── presets ──────────────────────────────────────────────────────
    @classmethod
    def real(cls) -> "DeterministicServices":
        """Real UUID4s and the real wall clock."""
        return cls()

    @classmethod
    def fake(cls, fixed_now: Any = None,
             seed: int = FAKE_SEED) -> "DeterministicServices":
        """Sequential UUID5s (32 hex chars, never repeating) + frozen clock."""
        counter = {"n": 0}
        frozen = _as_datetime(fixed_now) if fixed_now is not None else DEFAULT_FAKE_NOW

        def _uuid4() -> str:
            counter["n"] += 1
            return uuid.uuid5(uuid.NAMESPACE_OID, f"fake-{counter['n']}").hex

        return cls(uuid_fn=_uuid4, clock=lambda: frozen, seed=seed)

    @classmethod
    def fixed(cls, when: Any = None) -> "DeterministicServices":
        """Deterministic preset pinned to ``when`` (ISO string, epoch, datetime)."""
        frozen = _as_datetime(when) if when is not None else DEFAULT_FAKE_NOW
        return cls.fake(fixed_now=frozen)

    # ── primitives ───────────────────────────────────────────────────
    def uuid4(self) -> str:
        if self._uuid_fn is not None:
            return str(self._uuid_fn())
        return uuid.uuid4().hex

    def now(self) -> datetime:
        if self._clock is not None:
            return self._clock()
        return datetime.now(timezone.utc)


__all__ = ["DeterministicServices", "DEFAULT_FAKE_NOW", "FAKE_SEED"]
