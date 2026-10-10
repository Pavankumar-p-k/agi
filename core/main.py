"""core.main — FastAPI application, auth middleware, action dispatcher.

Rebuilt from the committed contracts:

- tests/unit/test_auth_middleware.py —
      AUTH_EXEMPT_PREFIXES contains "/health", "/docs", "/api/auth" and NOT
      "/api/admin" / "/api/chat"; AUTH_EXEMPT_PATHS contains "/".
      session_auth_middleware(request, call_next):
        exempt path            -> pass through
        auth manager absent    -> 401 for auth-required prefixes (fail closed)
        manager not configured -> pass through (auth explicitly disabled)
        configured + no/invalid token (cookie "session_token" first, then
        "Authorization: Bearer") -> 401; valid token -> 200 + request.state.user
      rate_limit_middleware: exempt paths (/health, /docs, /openapi.json)
        skip the limiter; otherwise core.rate_limiter.api_rate_limiter.check
        returning False -> 429.
- tests/integration/test_api_auth.py — middleware reads
      request.app.state.auth_manager (None == absent); real AuthManager has no
      validate_token, so validation falls back to get_username_for_token.
- tests/contract/test_api_contract.py — GET /health {status, version},
      GET /metrics {requests_total, tool_calls_total, llm_latency_*},
      anonymous /api/* -> 401/403/422, unknown route -> 404.
- tests/integration/test_get_info_routing.py — execute_action dispatches
      info intents (weather/news/stocks/sports/time) through
      core.integrations.get_info and returns {"executed": True, "action": str}.
- network/websocket_server.py — await execute_action(intent_data, message=text).
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, Optional

logger = logging.getLogger(__name__)

VERSION = "0.1.0"

# -- auth routing tables (contract-pinned) ---------------------------------- #
AUTH_EXEMPT_PREFIXES: tuple[str, ...] = (
    "/health", "/docs", "/openapi", "/favicon.ico", "/metrics", "/api/auth",
)
AUTH_EXEMPT_PATHS: tuple[str, ...] = ("/",)
AUTH_REQUIRED_PREFIXES: tuple[str, ...] = (
    "/api/", "/chat/", "/sessions/", "/admin/", "/tools/", "/plugins/",
    "/channels/",
)

_INFO_INTENTS = frozenset({"weather", "news", "stocks", "sports", "time"})

_requests_seen = 0


def _is_exempt(path: str) -> bool:
    return path in AUTH_EXEMPT_PATHS or any(
        path.startswith(prefix) for prefix in AUTH_EXEMPT_PREFIXES
    )


def _requires_auth(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in AUTH_REQUIRED_PREFIXES)


def _get_auth_manager(request: Any) -> Any:
    try:
        return getattr(request.app.state, "auth_manager", None)
    except Exception:  # noqa: BLE001 - mock/partial requests
        return None


def _manager_configured(manager: Any) -> bool:
    configured = getattr(manager, "is_configured", None)
    if isinstance(configured, bool):
        return configured
    users = getattr(manager, "users", None)
    try:
        return bool(users() if callable(users) else users)
    except Exception:  # noqa: BLE001
        return False


def _resolve_user(manager: Any, token: str) -> Optional[str]:
    """Validate a token -> username or None.

    Prefers validate_token(); real AuthManager exposes only
    get_username_for_token() which returns None for invalid tokens.
    """
    validate = getattr(manager, "validate_token", None)
    if callable(validate):
        try:
            if not validate(token):
                return None
        except Exception:  # noqa: BLE001
            return None
    getter = getattr(manager, "get_username_for_token", None)
    if callable(getter):
        try:
            return getter(token)
        except Exception:  # noqa: BLE001
            return None
    return None


def _bearer_token(headers: Any) -> Optional[str]:
    try:
        raw = headers.get("Authorization") or ""
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(raw, str):
        return None
    if raw.lower().startswith("bearer "):
        return raw[7:].strip()
    return None


async def session_auth_middleware(request: Any, call_next: Any) -> Any:
    """Cookie ("session_token") / Bearer auth gate (fail closed on /api/*)."""
    from fastapi.responses import JSONResponse

    global _requests_seen
    _requests_seen += 1

    path = request.url.path
    if _is_exempt(path):
        return await call_next(request)

    manager = _get_auth_manager(request)
    if manager is None:
        # No auth system attached: refuse auth-required surfaces, pass
        # everything else (unknown routes still 404 naturally).
        if _requires_auth(path):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        return await call_next(request)

    if not _manager_configured(manager):
        # Auth exists but no accounts yet — enforcement would lock everyone
        # out (this also covers local dev: lifespan attaches the real
        # manager, and a fresh install has zero users). Explicit
        # configuration (first account) is the gate.
        return await call_next(request)

    token: Any = None
    try:
        token = request.cookies.get("session_token")
    except Exception:  # noqa: BLE001
        token = None
    if not token:
        token = _bearer_token(request.headers)

    if token:
        user = _resolve_user(manager, token)
        if user is not None:
            try:
                request.state.user = user
            except Exception:  # noqa: BLE001
                pass
            return await call_next(request)
    return JSONResponse({"error": "unauthorized"}, status_code=401)


async def rate_limit_middleware(request: Any, call_next: Any) -> Any:
    """Sliding-window limiter on non-exempt paths -> 429 when over limit."""
    from fastapi.responses import JSONResponse

    path = request.url.path
    if _is_exempt(path):
        return await call_next(request)
    try:
        from core.rate_limiter import api_rate_limiter

        client = getattr(request, "client", None)
        ip = getattr(client, "host", None) or "unknown"
        allowed = bool(api_rate_limiter.check("api", ip))
    except Exception:  # noqa: BLE001 - limiter must never take the app down
        allowed = True
    if not allowed:
        return JSONResponse({"error": "rate limit exceeded"}, status_code=429)
    return await call_next(request)


# -- application -------------------------------------------------------------- #
@asynccontextmanager
async def _lifespan(app: Any) -> Any:
    try:
        from core.auth import get_auth_manager

        app.state.auth_manager = get_auth_manager()
    except Exception as exc:  # noqa: BLE001
        logger.warning("[main] auth manager unavailable: %s", exc)
        app.state.auth_manager = None
    yield {"background_tasks": []}


from fastapi import FastAPI  # noqa: E402 - after helpers for readability
from starlette.middleware.base import BaseHTTPMiddleware  # noqa: E402

app = FastAPI(title="JARVIS", version=VERSION, lifespan=_lifespan)
app.state.auth_manager = None

# add_middleware prepends: rate limiting is added last so it wraps auth
# (a 429 fires before a 401 for over-limit requests).
app.add_middleware(BaseHTTPMiddleware, dispatch=session_auth_middleware)
app.add_middleware(BaseHTTPMiddleware, dispatch=rate_limit_middleware)


@app.get("/health")
async def health() -> dict[str, Any]:
    """Public health probe (contract: status + version fields)."""
    return {"status": "ok", "version": VERSION}


@app.get("/metrics")
async def metrics() -> dict[str, Any]:
    """Public metrics (contract: requests_total, tool_calls_total,
    llm_latency_* keys)."""
    return {
        "requests_total": _requests_seen,
        "tool_calls_total": 0,
        "llm_latency_avg_ms": 0.0,
        "llm_latency_p50_ms": 0.0,
    }


@app.get("/favicon.ico")
async def favicon() -> Any:
    from fastapi.responses import Response

    return Response(status_code=204)


# -- settings ---------------------------------------------------------------
@app.get("/api/settings")
async def settings_list() -> dict[str, Any]:
    """Return the current configuration (contract-pinned address)."""
    from core.configuration import configuration

    return {"settings": configuration.snapshot()}


@app.get("/api/settings/llm.chat_model")
async def settings_llm_chat_model() -> dict[str, Any]:
    """Return the configured chat model (defaults to the role env var)."""
    from core.configuration import configuration

    return {"model": configuration.get("llm.chat_model", "ollama/qwen2.5-coder:3b")}


@app.get("/")
async def root() -> dict[str, Any]:
    return {"name": "jarvis", "version": VERSION}


# -- action dispatcher -------------------------------------------------------- #
async def execute_action(intent_data: Optional[dict[str, Any]],
                         message: str = "", **kwargs: Any) -> dict[str, Any]:
    """Dispatch an extracted intent to an action handler.

    Info intents route through core.integrations.get_info; everything else
    is honestly reported as not-yet-executed (callers fall back to chat).
    """
    data = intent_data or {}
    intent = str(data.get("intent") or "chat")
    target = str(data.get("target") or message or "")

    if intent in _INFO_INTENTS:
        try:
            from core.integrations import get_info

            info = await get_info(intent, target)
            return {"executed": True, "intent": intent, "action": str(info)}
        except Exception as exc:  # noqa: BLE001
            logger.error("[main] execute_action(%s) failed: %s", intent, exc)
            return {"executed": False, "intent": intent, "action": "",
                    "error": str(exc)}

    return {"executed": False, "intent": intent, "action": ""}


__all__ = [
    "app", "execute_action", "session_auth_middleware", "rate_limit_middleware",
    "AUTH_EXEMPT_PREFIXES", "AUTH_EXEMPT_PATHS", "AUTH_REQUIRED_PREFIXES",
    "VERSION",
]
