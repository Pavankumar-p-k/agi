"""Agents routes."""
from core.routes.agents.autonomous import router as autonomous_router
from core.routes.agents.cowork import router as cowork_router
from core.routes.agents.intelligence import router as intelligence_router
from core.routes.agents.planner import router as planner_router
from core.routes.agents.research import router as research_router
from core.routes.agents.vision import router as vision_router
from core.routes.agents.research_routes import router as research_routes_router
from core.routes.agents.agi_routes import router as agi_router
from core.routes.agents.api_agent_routes import router as api_agent_router
from core.routes.agents.governance_routes import router as governance_router
from core.routes.agents.jarvishub_routes import router as jarvishub_router

__all__ = [
    "autonomous_router",
    "cowork_router",
    "intelligence_router",
    "planner_router",
    "research_router",
    "vision_router",
    "research_routes_router",
    "agi_router",
    "api_agent_router",
    "governance_router",
    "jarvishub_router",
]