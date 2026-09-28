"""Verdict + Verifier — the verification framework primitives (Sprint 3)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Verdict:
    verifier_name: str
    outcome: str  # PASS | WARNING | FAIL
    message: str = ""


class Verifier:
    """Interface: async verify(ctx) -> Verdict."""

    @property
    def name(self) -> str:
        raise NotImplementedError

    async def verify(self, ctx: Any) -> Verdict:
        raise NotImplementedError


__all__ = ["Verdict", "Verifier"]
