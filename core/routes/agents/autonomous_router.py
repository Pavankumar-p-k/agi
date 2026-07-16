"""core/routes/autonomous.py — Autonomous Improvement Loop API.

Provides endpoints for the autonomous opportunity→experiment→outcome→calibration cycle.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException

from core.improvement.autonomous_loop import AutonomousLoop

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/autonomous", tags=["Autonomous"])


def _get_loop() -> AutonomousLoop:
    return AutonomousLoop()


@router.post("/tick")
def tick() -> dict[str, Any]:
    """Advance one opportunity one step in the autonomous loop."""
    loop = _get_loop()
    return loop.tick()


@router.post("/advance/{opp_id}")
def advance_opportunity(opp_id: str) -> dict[str, Any]:
    """Advance a specific opportunity one step."""
    loop = _get_loop()
    result = loop.advance_opportunity(opp_id)
    if result.get("action") == "not_found":
        raise HTTPException(status_code=404, detail=f"Opportunity {opp_id} not found")
    return result


@router.post("/run/{opp_id}")
def run_full_cycle(opp_id: str) -> list[dict[str, Any]]:
    """Run the full lifecycle for an opportunity."""
    loop = _get_loop()
    return loop.run_full_cycle(opp_id)
