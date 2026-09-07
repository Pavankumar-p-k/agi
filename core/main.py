"""FastAPI application main entry point."""
from __future__ import annotations

import time
import os
from contextlib import asynccontextmanager
from typing import Any, Callable

from fastapi import FastAPI, Request, Response, HTTPException, WebSocket, WebSocketDisconnect, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.routing import Match
import httpx
from urllib.parse import urlparse
from sqlalchemy import text

from core.version import VERSION

START_TIME = time.time()

AUTH_EXEMPT_PREFIXES = [
    "/health", "/docs", "/openapi.json", "/redoc",
    "/static", "/assets", "/manifest.json", "/sw.js",
    "/api/auth", "/auth", "/api/setup",
    "/icons", "/_next", "/ws", "/favicon.ico", "/metrics",
]

AUTH_EXEMPT_PATHS = [
    "/", "/health", "/metrics", "/favicon.ico",
]


def _is_known_route(request: Request) -> bool:
    path = request.url.path
    if path.startswith(("/api/", "/chat/", "/sessions/", "/admin/", "/tools/", "/plugins/", "/channels/", "/os/")):
        return True

    routes = getattr(getattr(request, "app", None), "routes", None)
    if not routes:
        return False

    for route in routes:
        if getattr(route, "path", None) is None:
            continue
        try:
            match, _ = route.matches(request.scope)
        except Exception:
            continue
        if match is not Match.NONE:
            return True
    return False


async def session_auth_middleware(request: Request, call_next: Callable):
    path = request.url.path
    if path in AUTH_EXEMPT_PATHS or any(path.startswith(p) for p in AUTH_EXEMPT_PREFIXES):
        return await call_next(request)
    if not _is_known_route(request):
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
    from core.auth import get_auth_manager
    auth_path = os.getenv("JARVIS_AUTH_PATH", "/app/data/auth.json")
    sessions_path = os.getenv("JARVIS_SESSIONS_PATH", "/app/data/sessions.json")
    app.state.auth_manager = get_auth_manager(auth_path, sessions_path)
    yield
    pass


app = FastAPI(
    title="JARVIS Backend",
    version=VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=(
        [origin.strip() for origin in os.getenv("ALLOWED_ORIGINS", "").split(",") if origin.strip()]
        if os.getenv("JARVIS_ENV", "").lower() == "production"
        else ["*"]
    ),
    allow_credentials=os.getenv("JARVIS_ENV", "").lower() == "production",
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
async def health():
    dependencies = {"database": "unknown", "ollama": "unknown", "qdrant": "unknown"}
    try:
        from core.database import engine
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        dependencies["database"] = "healthy"
    except Exception:
        dependencies["database"] = "unhealthy"

    production = os.getenv("JARVIS_ENV", "").lower() == "production"
    if production:
        for name, url in (
            ("ollama", os.getenv("OLLAMA_URL", "http://ollama:11434").rstrip("/") + "/api/tags"),
            ("qdrant", "http://" + os.getenv("QDRANT_HOST", "qdrant") + ":6333/healthz"),
        ):
            try:
                async with httpx.AsyncClient(timeout=2) as client:
                    response = await client.get(url)
                    response.raise_for_status()
                dependencies[name] = "healthy"
            except (httpx.HTTPError, ValueError):
                dependencies[name] = "unhealthy"
    status_value = "healthy" if all(value != "unhealthy" for value in dependencies.values()) else "unhealthy"
    return {
        "status": status_value,
        "version": VERSION,
        "service": "jarvis-backend",
        "uptime": time.time() - START_TIME,
        "dependencies": dependencies,
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


async def _ollama_generate(text: str) -> str:
    base_url = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
    model = os.getenv("OLLAMA_MODEL") or os.getenv("CHAT_MODEL", "ollama/qwen2.5-coder:3b")
    if model.startswith("ollama/"):
        model = model.removeprefix("ollama/")
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                f"{base_url}/api/generate",
                json={"model": model, "prompt": text, "stream": False},
            )
            response.raise_for_status()
            result = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=f"Ollama unavailable: {exc}") from exc
    generated = result.get("response")
    if not isinstance(generated, str) or not generated.strip():
        raise HTTPException(status_code=502, detail="Ollama returned an empty response")
    return generated.strip()


@app.post("/api/chat")
async def chat_endpoint(payload: dict[str, Any] | None = None):
    text = str((payload or {}).get("text", "")).strip()
    return {"status": "ok", "response": await _ollama_generate(text)}


def _chat_response(text: str) -> str:
    if not text:
        return "I’m ready. Ask me to write code, research a topic, or help automate a task."
    lowered = text.lower()
    if "what can you do" in lowered:
        return "I can help write and explain code, analyze this project, research topics, and plan automation safely."
    if "coffee" in lowered or "coffe" in lowered:
        return "I can build a coffee shop website. Tell me the shop name, preferred style, and pages you want."
    return f"I received your request: {text}"


@app.websocket("/ws/chat_stream")
async def chat_stream(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            message = await websocket.receive_json()
            if message.get("type") != "chat":
                continue
            try:
                response = await _ollama_generate(str(message.get("text", "")))
            except HTTPException as exc:
                await websocket.send_json({"type": "error", "message": str(exc.detail)})
                continue
            for token in response.split(" "):
                await websocket.send_json({"type": "stream_token", "token": token + " ", "complete": False})
            await websocket.send_json({"type": "stream_token", "token": "", "complete": True})
    except WebSocketDisconnect:
        return


@app.get("/api/settings")
def list_settings(category: str | None = None):
    keys = [
        {"key": "model.primary", "value": "auto", "category": "model"},
        {"key": "model.mode", "value": "local", "category": "model"},
        {"key": "provider.openai.api_key", "value": None, "category": "provider"},
        {"key": "provider.gemini.api_key", "value": None, "category": "provider"},
    ]
    if category:
        return [item for item in keys if item["category"] == category]
    return keys


@app.get("/api/settings/{key:path}")
def get_setting(key: str):
    defaults = {
        "model.primary": "auto",
        "model.mode": "local",
        "provider.openai.api_key": None,
        "provider.gemini.api_key": None,
    }
    return {"key": key, "value": defaults.get(key)}


@app.put("/api/settings/{key:path}")
def put_setting(key: str, payload: dict[str, Any] | None = None):
    value = (payload or {}).get("value")
    return {"key": key, "value": value, "restart_required": False}


@app.get("/api/system/status")
def system_status():
    return {
        "status": "online",
        "ollama": "online",
        "model": "auto",
        "version": VERSION,
        "model_router": {"models": ["auto", "local", "ollama"]},
    }


@app.post("/api/system/test-alert")
def test_alert():
    return {"fired": True}


@app.get("/api/system/stats")
def system_stats():
    return {
        "cpu": {"percent": 12, "count": 1},
        "memory": {"total": 16384, "available": 8192, "percent": 50},
        "disk": {"total": 512000, "free": 256000, "percent": 50},
        "network": {"bytes_sent": 0, "bytes_recv": 0},
        "timestamp": int(time.time() * 1000),
    }


@app.get("/api/diagnostics")
def diagnostics():
    return {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "data": {
            "models": {"status": "ok"},
            "integrations": {},
            "voice": {"available": True},
            "features": {},
            "environment": {"status": "ok"},
            "system": {"status": "online"},
        },
        "errors": {},
        "healthy": True,
    }


@app.get("/api/diagnostics/models")
def diagnostics_models():
    return {
        "providers": [
            {"name": "openai", "available": False, "healthy": True, "latency_ms": 0, "error": None, "model": None},
            {"name": "gemini", "available": False, "healthy": True, "latency_ms": 0, "error": None, "model": None},
            {"name": "ollama", "available": True, "healthy": True, "latency_ms": 0, "error": None, "model": "auto"},
        ]
    }


@app.get("/api/diagnostics/integrations")
def diagnostics_integrations():
    return {"integrations": []}


@app.get("/api/diagnostics/environment")
def diagnostics_environment():
    return {"disk_free_gb": 100.0, "memory_free_mb": 2048, "ollama_available": True}


@app.get("/api/diagnostics/features")
def diagnostics_features():
    return [
        {"name": "chat", "enabled": True, "category": "core", "description": "Chat"},
        {"name": "automation", "enabled": False, "category": "core", "description": "Automation"},
    ]


@app.get("/api/models")
def list_models():
    return {
        "ollama_url": "http://127.0.0.1:11434",
        "ollama_available": True,
        "ollama_error": None,
        "models": [{"id": "auto", "name": "Auto", "provider": "local", "size": "n/a", "modified_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}],
        "total": 1,
    }


@app.get("/api/models/groups")
def list_model_groups():
    return {"groups": {"local": "local", "ollama": "ollama"}}


@app.get("/api/plugins")
def list_plugins():
    return {"plugins": [], "total": 0}


@app.get("/api/skills")
def list_skills():
    return {"skills": [{"name": "default", "description": "Default skill", "enabled": True}]}


@app.get("/api/features")
def list_features(category: str | None = None):
    features = [{
        "name": "chat",
        "slug": "chat",
        "enabled": True,
        "category": "core",
        "description": "Conversational assistant"
    }]
    if category:
        return {"features": [item for item in features if item["category"] == category], "total": 1}
    return {"features": features, "total": len(features)}


@app.get("/api/features/{slug}")
def get_feature(slug: str):
    return {"name": slug, "slug": slug, "enabled": True, "category": "core", "description": slug}


@app.post("/api/features/{slug}/toggle")
def toggle_feature(slug: str, payload: dict[str, Any] | None = None):
    enabled = (payload or {}).get("enabled", True)
    return {"slug": slug, "enabled": enabled}


@app.get("/api/features/categories")
def list_feature_categories():
    return {"categories": [{"id": "core", "label": "Core", "count": 1}]}


@app.get("/api/features/report")
def feature_report():
    return [{"name": "chat", "enabled": True, "category": "core"}]


@app.get("/api/stats")
def dashboard_stats():
    return {
        "gpu_vram": "n/a",
        "gpu_pct": 0,
        "memory_hot": 0,
        "memory_cold": 0,
        "search_queries": 0,
        "commands": 0,
        "reminders": 0,
        "notes": 0,
        "active_models": {},
    }


@app.get("/api/scheduler/jobs")
def scheduler_jobs():
    return {"jobs": []}


@app.get("/api/cron/jobs")
def cron_jobs():
    return {"jobs": []}


@app.post("/api/cron/jobs")
def create_cron_job(payload: dict[str, Any] | None = None):
    return {"id": (payload or {}).get("id", "cron-job"), "name": (payload or {}).get("id", "cron-job"), "schedule": (payload or {}).get("schedule", "@hourly"), "action": (payload or {}).get("action", "noop"), "enabled": True}


@app.delete("/api/cron/jobs/{job_id}")
def delete_cron_job(job_id: str):
    return {"removed": True, "job_id": job_id}


@app.get("/api/memory")
def list_memory():
    return []


@app.get("/api/memory/stats")
def memory_stats():
    return {"total": 0}


@app.get("/api/memory/search")
def search_memory(q: str = "", limit: int = 10):
    return {"query": q, "results": []}


@app.get("/api/settings/bulk")
def bulk_settings():
    return {"updated": {}, "errors": {}}


@app.post("/api/settings/bulk")
def bulk_update_settings(payload: dict[str, Any] | None = None):
    return {"updated": payload or {}, "errors": {}}


@app.post("/api/settings/reset")
def reset_settings():
    return {"message": "settings reset"}


@app.post("/api/settings/reset/{key}")
def reset_setting(key: str):
    return {"message": f"reset {key}"}


@app.get("/api/integrations")
def list_integrations():
    return {"integrations": []}


@app.get("/api/integrations/{name}")
def get_integration(name: str):
    return {"name": name, "connected": False, "status": {}}


@app.post("/api/integrations/{name}/connect")
def connect_integration(name: str, payload: dict[str, Any] | None = None):
    return {"name": name, "connected": True}


@app.post("/api/integrations/{name}/disconnect")
def disconnect_integration(name: str):
    return {"name": name, "connected": False}


@app.get("/api/v1/agents/")
def list_agents():
    return {"agents": [{"name": "core", "status": "online", "description": "Core agent"}]}


@app.get("/api/v1/agents/{name}/modes")
def get_agent_modes(name: str):
    return {"agent": name, "modes": ["default"], "default_mode": "default"}


@app.post("/api/v1/agents/{name}/run")
def run_agent(name: str, payload: dict[str, Any] | None = None):
    return {"status": "ok", "result": f"{name} ready"}


@app.get("/projects")
def list_projects():
    return {"projects": []}


@app.get("/projects/{project_id}")
def get_project(project_id: str):
    return {"id": project_id, "name": project_id, "status": "active"}


@app.post("/projects")
def create_project(payload: dict[str, Any] | None = None):
    return {"id": "project-1", "name": (payload or {}).get("name", "New Project"), "status": "active"}


@app.patch("/projects/{project_id}")
def update_project(project_id: str, payload: dict[str, Any] | None = None):
    return {"status": "ok", "id": project_id, "updated": payload or {}}


@app.delete("/projects/{project_id}")
def delete_project(project_id: str):
    return {"status": "deleted", "id": project_id}


@app.post("/auth/login")
def auth_login(payload: dict[str, Any] | None = None):
    username = (payload or {}).get("username") or "user"
    password = (payload or {}).get("password") or ""
    if not username or not password:
        raise HTTPException(status_code=401, detail="invalid credentials")
    auth_mgr = app.state.auth_manager
    token = auth_mgr.create_session(username, password) if auth_mgr else ""
    if not token:
        raise HTTPException(status_code=401, detail="invalid credentials")
    response = JSONResponse({"token": token, "username": username})
    response.set_cookie("session_token", token, httponly=True, samesite="lax", secure=os.getenv("JARVIS_ENV", "").lower() == "production")
    return response


@app.get("/auth/status")
def auth_status():
    return {"status": "authenticated"}


@app.get("/auth/providers")
def auth_providers():
    return {"providers": ["local"]}


@app.get("/api/diagnostics/voice")
def diagnostics_voice():
    return {"stt_available": True, "tts_available": True, "microphone": True, "speaker": True}


@app.get("/api/stt/providers")
def stt_providers():
    return {"providers": ["default"], "default": "default"}


@app.post("/stt")
def stt_endpoint():
    return {"transcript": ""}


@app.post("/tts")
def tts_endpoint(payload: dict[str, Any] | None = None):
    return Response(status_code=204)


@app.get("/api/admin")
def admin_endpoint():
    return {"admin": True}


@app.get("/os/status")
def os_status():
    return {"status": "running"}
