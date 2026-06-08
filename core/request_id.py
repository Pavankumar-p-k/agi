import uuid
import time
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from core.observability.logging import LogContext

logger = logging.getLogger("jarvis.request_id")

_REQUEST_ID_CTX: dict = {}

def get_request_id() -> str:
    return _REQUEST_ID_CTX.get("id", "")

class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        start = time.perf_counter()

        _REQUEST_ID_CTX["id"] = rid
        LogContext.set_request_id(rid)
        uid = getattr(request.state, "current_user", "")
        if uid:
            LogContext.set_user_id(uid)

        logger.info("→ %s %s", request.method, request.url.path)

        try:
            response: Response = await call_next(request)
        except Exception as e:
            elapsed = (time.perf_counter() - start) * 1000
            logger.error("✗ %s %s — %s (%dms)", request.method, request.url.path, e, elapsed)
            raise

        elapsed = (time.perf_counter() - start) * 1000
        logger.info("← %d (%dms)", response.status_code, elapsed)
        response.headers["X-Request-ID"] = rid
        LogContext.reset()
        return response
