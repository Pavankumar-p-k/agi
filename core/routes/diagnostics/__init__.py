"""Diagnostics routes."""
from core.routes.diagnostics.diagnostics_router import router as diagnostics_router
from core.routes.diagnostics.analytics_router import router as analytics_router
from core.routes.diagnostics.quality_router import router as quality_router

__all__ = [
    "diagnostics_router",
    "analytics_router",
    "quality_router",
]