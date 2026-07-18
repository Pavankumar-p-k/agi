"""Agents routes."""
from core.routes.agents.autonomous_router import router as autonomous_router
from core.routes.agents.cowork_router import router as cowork_router
from core.routes.agents.intelligence_router import router as intelligence_router
from core.routes.agents.planner_router import router as planner_router
from core.routes.agents.research_router import router as research_router
from core.routes.agents.vision_router import router as vision_router
from core.routes.agents.research_routes import router as research_routes_router
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
    "api_agent_router",
    "governance_router",
    "jarvishub_router",
]