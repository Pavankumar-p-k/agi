"""Files routes."""
from core.routes.files.artifacts import router as artifacts_router
from core.routes.files.dot_routes import router as dot_router
from core.routes.files.website_routes import router as website_router

__all__ = [
    "artifacts_router",
    "dot_router",
    "website_router",
]