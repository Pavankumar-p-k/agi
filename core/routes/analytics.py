"""core/routes/analytics.py — Aggregate performance analytics API.

Provides a single endpoint that returns cross-system metrics
computed from plans, outcomes, strategies, and replan events.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/analytics", tags=["Analytics"])


@router.get("/planner-performance")
def get_planner_performance() -> dict[str, Any]:
    """Aggregate planner performance metrics."""
    from core.analytics.planner import PlannerAnalytics
    analytics = PlannerAnalytics()
    return analytics.compute()
