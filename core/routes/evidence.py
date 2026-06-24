"""core/routes/evidence.py — Evidence Generation API.

Provides endpoints to trigger continuous evidence generation,
which feeds the autonomous learning loop with fresh plan outcomes,
research facts, strategy competitions, and negotiation feedback.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter

from core.evidence.generator import EvidenceGenerator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/evidence", tags=["Evidence"])


def _get_generator() -> EvidenceGenerator:
    return EvidenceGenerator()


@router.post("/tick")
def tick(count: int = 5) -> dict[str, Any]:
    """Generate one batch of evidence from the next source mode."""
    gen = _get_generator()
    return gen.tick(count=count)


@router.post("/run")
def run_cycles(cycles: int = 100, batch_size: int = 5) -> dict[str, Any]:
    """Run multiple evidence generation cycles across all modes."""
    gen = _get_generator()
    return gen.run_cycles(cycles=cycles, batch_size=batch_size)
