"""core/routes/improvements.py — Improvement System API.

Provides endpoints for:
  - Listing improvement opportunities
  - Creating and managing experiments
  - Promoting/rolling back changes
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.improvement.knob_store import KnobStore
from core.improvement.planner_detector import PlannerImprovementDetector

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/improvements", tags=["Improvements"])


class CreateExperimentRequest(BaseModel):
    opportunity_id: str


# ── Detector ────────────────────────────────────────────────────────────────


@router.get("")
def list_opportunities() -> list[dict[str, Any]]:
    """Scans planner analytics and returns all improvement opportunities."""
    detector = PlannerImprovementDetector()
    return detector.detect_all()


# ── Experiments ─────────────────────────────────────────────────────────────


def _get_manager():
    from core.improvement.planner_experiment import PlannerExperimentManager
    return PlannerExperimentManager()


@router.get("/experiments")
def list_experiments(status: str | None = None) -> list[dict[str, Any]]:
    mgr = _get_manager()
    return mgr.list_all(status=status)


@router.post("/experiments", status_code=201)
def create_experiment(req: CreateExperimentRequest) -> dict[str, Any]:
    """Create an experiment from an improvement opportunity."""
    detector = PlannerImprovementDetector()
    all_opps = detector.detect_all()
    opp = next((o for o in all_opps if o["id"] == req.opportunity_id), None)
    if opp is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")

    mgr = _get_manager()
    knob_store = KnobStore()
    experiment = mgr.create(opp, knob_store)
    return experiment


@router.post("/experiments/{exp_id}/start")
def start_experiment(exp_id: str) -> dict[str, Any]:
    mgr = _get_manager()
    knob_store = KnobStore()
    result = mgr.start(exp_id, knob_store)
    if result is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return result


@router.post("/experiments/{exp_id}/complete")
def complete_experiment(exp_id: str) -> dict[str, Any]:
    mgr = _get_manager()
    knob_store = KnobStore()
    result = mgr.complete(exp_id, knob_store)
    if result is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return result


@router.post("/experiments/{exp_id}/promote")
def promote_experiment(exp_id: str) -> dict[str, Any]:
    mgr = _get_manager()
    knob_store = KnobStore()
    result = mgr.promote(exp_id, knob_store)
    if result is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return result


@router.post("/experiments/{exp_id}/rollback")
def rollback_experiment(exp_id: str) -> dict[str, Any]:
    mgr = _get_manager()
    knob_store = KnobStore()
    result = mgr.rollback(exp_id, knob_store)
    if result is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return result
