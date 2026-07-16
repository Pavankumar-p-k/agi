"""Integrations routes."""
from core.routes.integrations.integrations_router import router as integrations_router
from core.routes.integrations.cloud_router import router as cloud_router
from core.routes.integrations.hybrid_router import router as hybrid_router
from core.routes.integrations.plugin_router import router as plugin_router
from core.routes.integrations.ragflow_router import router as ragflow_router
from core.routes.integrations.mcp_router import router as mcp_router

__all__ = [
    "integrations_router",
    "cloud_router",
    "hybrid_router",
    "plugin_router",
    "ragflow_router",
    "mcp_router",
]