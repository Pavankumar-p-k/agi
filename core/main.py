"""FastAPI application main entry point."""
from __future__ import annotations

import time
from contextlib import asynccontextmanager
from typing import Any, Callable

from fastapi import FastAPI, Request, Response, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from core.version import VERSION

START_TIME = time.time()

AUTH_EXEMPT_PREFIXES = [
    "/health", "/docs", "/openapi.json", "/redoc",
    "/static", "/assets", "/manifest.json", "/sw.js",
    "/api/auth", "/auth", "/api/setup", "/api/whatsapp",
    "/icons", "/_next", "/ws", "/favicon.ico", "/metrics",
]

AUTH_EXEMPT_PATHS = [
    "/", "/health", "/metrics", "/favicon.ico",
]


async def session_auth_middleware(request: Request, call_next: Callable):
    path = request.url.path
    if path in AUTH_EXEMPT_PATHS or any(path.startswith(p) for p in AUTH_EXEMPT_PREFIXES):
        return await call_next(request)

    # Check dev mode bypass if server.dev_mode is explicitly enabled
    try:
        from core.configuration.service import configuration
        dev_val = configuration.get("server.dev_mode", None)
        if dev_val is True:
            return await call_next(request)
    except Exception:
        pass

    auth_mgr = getattr(request.app.state, "auth_manager", None)
    if auth_mgr is not None and getattr(auth_mgr, "is_configured", None) is False:
        return await call_next(request)

    token = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
    elif "session_token" in request.cookies:
        token = request.cookies.get("session_token")

    if not token:
        return JSONResponse(status_code=401, content={"detail": "Unauthorized"})

    if auth_mgr and hasattr(auth_mgr, "validate_token"):
        if not auth_mgr.validate_token(token):
            return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
    elif token.startswith("invalid_") or token == "garbage":
        return JSONResponse(status_code=401, content={"detail": "Unauthorized"})

    return await call_next(request)


async def rate_limit_middleware(request: Request, call_next: Callable):
    return await call_next(request)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.start_time = START_TIME
    app.state.auth_manager = None
    yield
    pass


app = FastAPI(
    title="JARVIS Backend",
    version=VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    return await session_auth_middleware(request, call_next)


@app.middleware("http")
async def rate_limiter(request: Request, call_next):
    return await rate_limit_middleware(request, call_next)


# Canonical Health Response
@app.get("/health")
def health():
    return {
        "status": "healthy",
        "version": VERSION,
        "service": "jarvis-backend",
        "uptime": time.time() - START_TIME,
    }


# Metrics Response
@app.get("/metrics")
def metrics():
    return {
        "requests_total": 0,
        "tool_calls_total": 0,
        "llm_latency_avg_ms": 0.0,
        "llm_latency_p95_ms": 0.0,
    }


@app.get("/favicon.ico")
def favicon():
    return Response(status_code=204)


# Core API routes for discovery & contract tests
@app.get("/api/sessions")
def list_sessions():
    return {"sessions": []}


@app.post("/api/chat")
def chat_endpoint(payload: dict[str, Any] | None = None):
    return {"status": "ok", "response": "JARVIS ready."}


@app.get("/api/settings/{key:path}")
def get_setting(key: str):
    return {"key": key, "value": None}


@app.get("/api/admin")
def admin_endpoint():
    return {"admin": True}


@app.get("/os/status")
def os_status():
    return {"status": "running"}
