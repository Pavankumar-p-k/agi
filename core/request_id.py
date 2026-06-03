import uuid
import time
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("jarvis.request_id")

_REQUEST_ID_CTX: dict = {}

def get_request_id() -> str:
    return _REQUEST_ID_CTX.get("id", "")

class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        start = time.perf_counter()

        _REQUEST_ID_CTX["id"] = rid
        logger.info(f"[{rid}] → {request.method} {request.url.path}")

        try:
            response: Response = await call_next(request)
        except Exception as e:
            elapsed = (time.perf_counter() - start) * 1000
            logger.error(f"[{rid}] ✗ {request.method} {request.url.path} — {e} ({elapsed:.0f}ms)")
            raise

        elapsed = (time.perf_counter() - start) * 1000
        logger.info(f"[{rid}] ← {response.status_code} ({elapsed:.0f}ms)")
        response.headers["X-Request-ID"] = rid
        return response
