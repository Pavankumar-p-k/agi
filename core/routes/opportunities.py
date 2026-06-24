"""core/routes/opportunities.py — Opportunity Discovery API.

Bridges the existing opportunity pipeline (Phases 17-23) with:
  - The improvement system (accepted opportunities → experiments)
  - The negotiation system (contentious opportunities → agent debate)
  - The analytics system (opportunity scoring → planner dashboard)
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.opportunity.calibration import OpportunityCalibrator
from core.opportunity.engine import OpportunityDiscoveryEngine
from core.opportunity.store import OpportunityStore
from core.opportunity.forecasting import ForecastingEngine
from core.opportunity.bottlenecks import BottleneckAnalyzer
from core.opportunity.graph import build_default_graph
from core.opportunity.roadmap import RoadmapGenerator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/opportunities", tags=["Opportunities"])


def _get_store() -> OpportunityStore:
    return OpportunityStore()


def _get_calibrator() -> OpportunityCalibrator:
    store = _get_store()
    return OpportunityCalibrator(store=store)


def _get_engine() -> OpportunityDiscoveryEngine:
    calibrator = _get_calibrator()
    return OpportunityDiscoveryEngine(calibrator=calibrator)


def _get_forecaster() -> ForecastingEngine:
    return ForecastingEngine()


def _get_bottleneck_analyzer() -> BottleneckAnalyzer:
    return BottleneckAnalyzer()


def _get_roadmap_generator() -> RoadmapGenerator:
    return RoadmapGenerator()


class AcceptRequest(BaseModel):
    create_negotiation: bool = False


# ── Discovery ───────────────────────────────────────────────────────────────


@router.get("")
def list_opportunities(
    status: str | None = None,
    source: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """List persisted opportunity candidates, optionally filtered."""
    store = _get_store()
    opportunities = store.list_opportunities(
        status=status, source=source, limit=limit
    )
    return [o.to_dict() for o in opportunities]


@router.post("/discover")
def discover_opportunities() -> dict[str, Any]:
    """Run the discovery engine and persist all new opportunities."""
    engine = _get_engine()
    store = _get_store()

    # Wire up available stores from the current runtime
    activity_store = _resolve_activity_store()
    principle_store = _resolve_principle_store()
    registry = _resolve_registry()
    experiment_runner = _resolve_experiment_runner()

    results = engine.discover_all(
        activity_store=activity_store,
        principle_store=principle_store,
        registry=registry,
        experiment_runner=experiment_runner,
    )

    count = 0
    for opp in results:
        try:
            existing = store.get_opportunity(opp.id)
            if existing is None:
                store.save_opportunity(opp)
                count += 1
        except Exception as e:
            logger.warning(f"Failed to save opportunity {opp.id}: {e}")

    return {"discovered": count, "total": len(results)}


@router.post("/{opp_id}/accept")
def accept_opportunity(opp_id: str, req: AcceptRequest | None = None) -> dict[str, Any]:
    """Accept an opportunity — optionally create a negotiation for debate."""
    store = _get_store()
    opp = store.get_opportunity(opp_id)
    if opp is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")

    store.update_opportunity_status(opp_id, "in_progress")

    result: dict[str, Any] = {"status": "in_progress", "opportunity": opp.to_dict()}

    if req and req.create_negotiation:
        try:
            from core.negotiation.engine import NegotiationEngine
            neg = NegotiationEngine()
            session = neg.create_session(
                goal=f"Should we pursue: {opp.improvement_description}",
            )
            result["negotiation"] = {
                "id": session["id"],
                "decision": session["consensus"]["decision"],
            }
        except Exception as e:
            logger.warning(f"Negotiation creation failed: {e}")

    return result


@router.post("/{opp_id}/reject")
def reject_opportunity(opp_id: str) -> dict[str, str]:
    """Reject an opportunity."""
    store = _get_store()
    opp = store.get_opportunity(opp_id)
    if opp is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    store.update_opportunity_status(opp_id, "rejected")
    return {"status": "rejected"}


@router.get("/scored-systems")
def get_scored_systems() -> dict[str, float]:
    """Return current system capability scores."""
    engine = _get_engine()
    return engine.get_scored_systems()


# ── Forecast ────────────────────────────────────────────────────────────────


@router.get("/forecast")
def get_forecast(horizon: str = "medium_term") -> list[dict[str, Any]]:
    """Get forecasted opportunity scores for all systems."""
    forecaster = _get_forecaster()
    store = _get_store()
    opportunities_list = store.list_opportunities(limit=50)

    # Build graph and bottlenecks for forecasting
    try:
        from core.opportunity.graph import build_default_graph
        graph = build_default_graph()
    except Exception:
        graph = type('EmptyGraph', (), {'nodes': [], 'edges': []})()

    try:
        from core.opportunity.bottlenecks import BottleneckAnalyzer
        analyzer = BottleneckAnalyzer()
        engine = _get_engine()
        system_scores = engine.get_scored_systems()
        bottlenecks_list = analyzer.analyze(graph=graph, system_scores=system_scores)
    except Exception:
        bottlenecks_list = None

    try:
        result = forecaster.forecast(
            opportunities=opportunities_list,
            graph=graph,
            bottlenecks=bottlenecks_list,
            history_store=store,
        )
    except Exception as e:
        logger.warning(f"Forecast failed: {e}")
        return []

    # Filter by horizon if requested
    forecasts = getattr(result, 'forecasts', result if isinstance(result, list) else [])
    if isinstance(forecasts, list):
        filtered = [f for f in forecasts if getattr(f, 'horizon', '') == horizon or not horizon]
        return [f.to_dict() if hasattr(f, 'to_dict') else f for f in filtered]
    return forecasts


# ── Bottlenecks ─────────────────────────────────────────────────────────────


@router.get("/bottlenecks")
def get_bottlenecks() -> list[dict[str, Any]]:
    """List bottleneck systems ranked by constrained value."""
    try:
        from core.opportunity.graph import build_default_graph
        graph = build_default_graph()
    except Exception:
        return []

    analyzer = _get_bottleneck_analyzer()
    engine = _get_engine()
    system_scores = engine.get_scored_systems()

    bottlenecks = analyzer.analyze(
        graph=graph,
        system_scores=system_scores,
    )
    return [b.to_dict() if hasattr(b, 'to_dict') else b for b in bottlenecks]


# ── Roadmap ─────────────────────────────────────────────────────────────────


@router.post("/roadmap")
def generate_roadmap() -> list[dict[str, Any]]:
    """Generate a phased improvement roadmap."""
    store = _get_store()
    opportunities_list = store.list_opportunities(status="open")
    engine = _get_engine()
    system_scores = engine.get_scored_systems()

    try:
        from core.opportunity.graph import build_default_graph
        graph = build_default_graph()
    except Exception:
        return []

    try:
        from core.opportunity.bottlenecks import BottleneckAnalyzer
        analyzer = BottleneckAnalyzer()
        bottlenecks_list = analyzer.analyze(graph=graph, system_scores=system_scores)
    except Exception:
        bottlenecks_list = None

    generator = _get_roadmap_generator()
    roadmap = generator.generate(
        opportunities=opportunities_list,
        graph=graph,
        bottlenecks=bottlenecks_list,
        system_scores=system_scores,
    )
    phases = getattr(roadmap, 'phases', []) or []
    if isinstance(roadmap, dict):
        phases = roadmap.get('phases', [])
    return [p.to_dict() if hasattr(p, 'to_dict') else p for p in phases]


# ── Dependency Graph ────────────────────────────────────────────────────────


@router.get("/graph")
def get_opportunity_graph() -> dict[str, Any]:
    """Get the opportunity dependency graph."""
    graph = build_default_graph()
    return {
        "nodes": [n.to_dict() for n in graph.nodes.values()],
        "edges": [e.to_dict() for e in graph.edges],
    }


# ── Store Resolvers ─────────────────────────────────────────────────────────


def _resolve_activity_store() -> Any:
    """Try to wire up an ActivityStore from the current runtime."""
    try:
        from core.activity.storage import ActivityStore as _ActivityStore
        return _ActivityStore()
    except Exception:
        return None


def _resolve_principle_store() -> Any:
    """Try to wire up a PrincipleStore from the current runtime."""
    try:
        from core.generalization.store import PrincipleStore as _PrincipleStore
        return _PrincipleStore()
    except Exception:
        return None


def _resolve_registry() -> Any:
    """Try to wire up the StructuralPropertyRegistry."""
    try:
        from core.generalization.registry import StructuralPropertyRegistry as _Registry
        return _Registry()
    except Exception:
        return None


def _resolve_experiment_runner() -> Any:
    """Try to wire up the experiment runner from improvement system."""
    try:
        from core.improvement.experiment import ExperimentRunner as _Runner
        return _Runner()
    except Exception:
        return None
