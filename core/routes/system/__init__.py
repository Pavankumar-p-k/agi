"""System routes."""
from core.routes.system.activity import router as activity_router
from core.routes.system.infrastructure import router as infrastructure_router
from core.routes.system.scheduler import router as scheduler_router
from core.routes.system.screen_routes import router as screen_router
from core.routes.system.setup import router as setup_router
from core.routes.system.setup_routes import router as setup_routes_router
from core.routes.system.terminal import router as terminal_router
from core.routes.system.utility import router as utility_router

__all__ = [
    "activity_router",
    "infrastructure_router",
    "scheduler_router",
    "screen_router",
    "setup_router",
    "setup_routes_router",
    "terminal_router",
    "utility_router",
]