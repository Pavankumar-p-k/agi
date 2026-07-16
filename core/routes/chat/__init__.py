"""Chat routes."""
from core.routes.chat.router import router as chat_router
from core.routes.chat.inbox_router import router as inbox_router
from core.routes.chat.websocket_router import router as websocket_router
from core.routes.chat.whatsapp_chat_routes import router as whatsapp_router

__all__ = [
    "chat_router",
    "inbox_router",
    "websocket_router",
    "whatsapp_router",
]