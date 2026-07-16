"""Memory routes."""
from core.routes.memory.knowledge import router as knowledge_router
from core.routes.memory.research_routes import router as research_router

__all__ = ["knowledge_router", "research_router"]