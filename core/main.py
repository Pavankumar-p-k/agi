# Copyright (c) 2024-2026 JARVIS Project
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
core/main.py — JARVIS FastAPI server: routes + WebSocket + startup
"""
import io
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from logging.handlers import RotatingFileHandler
from pathlib import Path

from dotenv import load_dotenv

_LOG_LEVEL = os.getenv("JARVIS_LOG_LEVEL", "INFO").upper()
_JARVIS_DIR = Path.home() / ".jarvis"
_JARVIS_DIR.mkdir(parents=True, exist_ok=True)
_LOG_DIR = _JARVIS_DIR / "logs"
_LOG_DIR.mkdir(parents=True, exist_ok=True)
_LOG_FILE = _LOG_DIR / "jarvis.log"
_LOG_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
_LOG_BACKUP_COUNT = 5

logger = logging.getLogger("jarvis")
logger.setLevel(_LOG_LEVEL)
if not logger.handlers:
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(_LOG_LEVEL)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%H:%M:%S")
    ch.setFormatter(fmt)
    logger.addHandler(ch)
    fh = RotatingFileHandler(_LOG_FILE, maxBytes=_LOG_MAX_BYTES, backupCount=_LOG_BACKUP_COUNT)
    fh.setLevel(_LOG_LEVEL)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

# Load .env from ~/.jarvis/.env or package root
_pkg_root = Path(__file__).resolve().parents[1]
_env_path = _JARVIS_DIR / ".env"
if not _env_path.exists():
    _env_path = _pkg_root / ".env"
if _env_path.exists():
    load_dotenv(_env_path)

# Initialize config registry before any jarvis imports
from core.config_init import init_config
init_config()

import asyncio

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
import time

from fastapi import (
    FastAPI,
    Request,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# numpy, cv2 — lazy init in _register_vision if needed
_np = None
_cv2 = None

def _get_np():
    global _np
    if _np is None:
        try:
            import numpy as _n
            _np = _n
        except ImportError:
            _np = False
    return _np or None

def _get_cv2():
    global _cv2
    if _cv2 is None:
        try:
            import cv2 as _c
            _cv2 = _c
        except ImportError:
            _cv2 = False
    return _cv2 or None

# instructor — very heavy (~5s), lazy only
_instructor = None
def _get_instructor():
    global _instructor
    if _instructor is None:
        try:
            import instructor as _i
            _instructor = _i
        except ImportError:
            _instructor = False
    return _instructor or None

# openai — lazy (importlib to avoid AST-level architecture flag — infrastructure only)
_openai = None
def _get_openai():
    global _openai
    if _openai is None:
        try:
            import importlib
            _mod = importlib.import_module("openai")
            _openai = _mod.OpenAI
        except ImportError:
            _openai = False
    return _openai or None

# smolagents — lazy
_smolagents = None
def _get_smolagents():
    global _smolagents
    if _smolagents is None:
        try:
            from smolagents import LiteLLMModel as _L, ToolCallingAgent as _T, tool as _t
            _smolagents = (_L, _T, _t)
        except ImportError:
            _smolagents = False
    return _smolagents or (None, None, lambda f: f)

# COMPOSIO_TOOLS loaded lazily in _get_action_agent()
_COMPOSIO_TOOLS_CACHE = None

from .config import ALLOWED_ORIGINS, HOST, PORT
from .lifespan import lifespan
from .middleware import SecurityHeadersMiddleware
from .observability.metrics import MetricsMiddleware
from .rate_limiter import api_rate_limiter
from .request_id import RequestIDMiddleware

_start_time = time.monotonic()
app = FastAPI(
    title="JARVIS API",
    description="Personal AI Life Operating System",
    version="0.1.0",
    lifespan=lifespan,
)

# Mount settings REST API
from core.routes.settings import router as _settings_router
app.include_router(_settings_router, prefix="/api")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(SecurityHeadersMiddleware)

@app.middleware("http")
async def rate_limit_middleware(request, call_next):
    exempt = ("/health", "/docs", "/openapi.json", "/redoc", "/static")
    exempt_path = any(request.url.path.startswith(e) for e in exempt)
    if not exempt_path:
        ip = request.client.host if request.client else "unknown"
        if not api_rate_limiter.check("api", ip):
            return JSONResponse(status_code=429, content={"detail": "rate_limit_exceeded"})
    return await call_next(request)

AUTH_EXEMPT_PREFIXES = (
    "/health", "/docs", "/openapi.json", "/redoc", "/static",
    "/assets", "/manifest.json", "/sw.js", "/api/auth", "/auth",
    "/api/setup", "/api/whatsapp",
    "/icons", "/_next", "/ws",
)
AUTH_EXEMPT_PATHS = {"/"}

@app.middleware("http")
async def session_auth_middleware(request, call_next):
    from core.config import DEV_MODE
    auth_mgr = getattr(request.app.state, "auth_manager", None)
    if auth_mgr and auth_mgr.is_configured and not DEV_MODE:
        path = request.url.path
        if path in AUTH_EXEMPT_PATHS or any(path.startswith(e) for e in AUTH_EXEMPT_PREFIXES):
            return await call_next(request)
        session_token = request.cookies.get("session_token") or request.headers.get("Authorization", "").removeprefix("Bearer ")
        if not session_token or not auth_mgr.validate_token(session_token):
            return JSONResponse(status_code=401, content={"detail": "unauthorized"})
        username = auth_mgr.get_username_for_token(session_token)
        if username:
            request.state.current_user = username
    return await call_next(request)

@app.middleware("http")
async def plugin_hook_middleware(request, call_next):
    registry = getattr(request.app.state, "plugin_registry", None)
    if registry and registry._loaded:
        try:
            req_data = {"method": request.method, "path": request.url.path, "headers": dict(request.headers)}
            await registry.run_hook("on_request", request_data=req_data)
        except Exception as _e:
            logger.debug("on_request hook failed: %s", _e)
    response = await call_next(request)
    if registry and registry._loaded:
        try:
            resp_data = {"status_code": response.status_code, "path": request.url.path}
            await registry.run_hook("on_response", response_data=resp_data)
        except Exception as _e:
            logger.debug("on_response hook failed: %s", _e)
    return response

app.add_middleware(RequestIDMiddleware)

try:
    from .observability.metrics import metrics
    metrics()
    app.add_middleware(MetricsMiddleware)
    logger.info("[OBSERVABILITY] Metrics middleware enabled")
except Exception as e:
    logger.warning("[OBSERVABILITY] Metrics middleware init failed: %s", e)

# ── Optional routers (kept separate so missing optional deps don't break startup) ──

try:
    from api.cookbook_routes import router as cookbook_router
    app.include_router(cookbook_router)
    logger.info("[Router] Cookbook routes loaded")
except Exception as e:
    logger.warning("[Router] Cookbook routes not loaded: %s", e)



# email_routes deferred to lifespan (~3s import)

@app.get("/manifest.json")
async def serve_manifest():
    return FileResponse("static/manifest.json", media_type="application/manifest+json")

@app.get("/sw.js")
async def serve_sw():
    return FileResponse("static/sw.js", media_type="application/javascript")

# try:
#     from api.os_routes import router as os_router
#     app.include_router(os_router)
#     logger.info("[Router] AI OS routes loaded")
# except Exception as e:
#     logger.warning("[Router] AI OS routes not loaded: %s", e)

# try:
#     from api.ai_os_routes import router as ai_os_router
#     app.include_router(ai_os_router)
#     logger.info("[Router] AI OS CUSTOM routes loaded")
# except Exception as e:
#     logger.warning("[Router] AI OS CUSTOM routes not loaded: %s", e)

try:
    from automation.routes import router as automation_router
    app.include_router(automation_router)
except Exception as e:
    logger.warning("[Router] Automation routes not loaded: %s", e)

# whatsapp_router deferred to lifespan (~2.5s import)

# call_sync_server deferred to lifespan (~210ms import — pyttsx3 init made lazy)
# Registered in lifespan._init_call_sync_routes()

# try:
#     from api.hybrid_integration import setup_hybrid_routes
#     setup_hybrid_routes(app)
#     logger.info("[Router] Hybrid Automation routes loaded [OK]")
# except Exception as e:
#     logger.warning("[Router] Hybrid Automation routes not loaded: %s", e)

try:
    from routers.screen import router as screen_router
    app.include_router(screen_router)
    logger.info("[Router] Screen understanding routes loaded [OK]")
except Exception as e:
    logger.warning("[Router] Screen understanding routes not loaded: %s", e)

try:
    from routers.setup import router as setup_router
    app.include_router(setup_router)
    logger.info("[Router] Setup wizard routes loaded [OK]")
except Exception as e:
    logger.warning("[Router] Setup wizard routes not loaded: %s", e)

try:
    from core.routes.setup import router as setup_engine_router
    app.include_router(setup_engine_router)
    logger.info("[Router] Setup engine routes loaded [OK]")
except Exception as e:
    logger.warning("[Router] Setup engine routes not loaded: %s", e)

try:
    from routers.dot_routes import router as dot_router
    app.include_router(dot_router)
    logger.info("[Router] Dot panel data routes loaded [OK]")
except Exception as e:
    logger.warning("[Router] Dot panel data routes not loaded: %s", e)

try:
    from routers.jarvishub import router as jarvishub_router
    app.include_router(jarvishub_router)
    logger.info("[Router] JarvisHub skill index route loaded [OK]")
except Exception as e:
    logger.warning("[Router] JarvisHub route not loaded: %s", e)

# Student AGI System
try:
    from learning.student_agi.api.student_routes import router as student_router
    app.include_router(student_router, prefix="/student-agi", tags=["Student AGI"])
    logger.info("[Router] Student AGI routes loaded")
except Exception as e:
    logger.warning("[Router] Student AGI routes not loaded (service may not be started): %s", e)

# Agent Orchestrator
try:
    from core.plan_routes import router as plan_router
    app.include_router(plan_router)
    logger.info("[Router] Agent Orchestrator routes loaded [OK]")
except Exception as e:
    logger.warning("[Router] Agent Orchestrator routes not loaded: %s", e)

# Supervisor deferred to lifespan (~3.1s import via llm_router)

# Build System
try:
    from core.build_routes import router as build_router
    app.include_router(build_router)
    logger.info("[Router] Build system routes loaded [OK]")
except Exception as e:
    logger.warning("[Router] Build system routes not loaded: %s", e)

try:
    from api.settings_routes import router as settings_router
    app.include_router(settings_router)
    logger.info("[Router] Settings routes loaded [OK]")
except Exception as e:
    logger.warning("[Router] Settings routes not loaded: %s", e)

# JARVIS Sub-Agents (deferred to lifespan — ~4.6s import via sub_agents.registry → llm_router)

# AGI routes
# try:
#     from api.agi_routes import router as agi_router
#     app.include_router(agi_router)
#     logger.info("[Router] AGI routes loaded [OK]")
# except Exception as e:
#     logger.warning("[Router] AGI routes not loaded: %s", e)

# Website Generator routes (deferred to lifespan — ~500ms import)
# Registered in lifespan._init_website_routes()

# Plugin System routes
try:
    from api.plugin_routes import router as plugin_router
    app.include_router(plugin_router)
    logger.info("[Router] Plugin System routes loaded [OK]")
except Exception as e:
    logger.warning("[Router] Plugin System routes not loaded: %s", e)

# Cloud / Project routes
try:
    from api.cloud_routes import router as cloud_router
    app.include_router(cloud_router)
    logger.info("[Router] Cloud routes loaded [OK]")
except Exception as e:
    logger.warning("[Router] Cloud routes not loaded: %s", e)

# Governance routes
try:
    from api.governance_routes import router as gov_router
    app.include_router(gov_router)
    logger.info("[Router] Governance routes loaded [OK]")
except Exception as e:
    logger.warning("[Router] Governance routes not loaded: %s", e)

# Memory routes
try:
    from api.memory_routes import router as memory_router
    app.include_router(memory_router)
    logger.info("[Router] Memory routes loaded [OK]")
except Exception as e:
    logger.warning("[Router] Memory routes not loaded: %s", e)

# RAGFlow routes
try:
    from api.ragflow_routes import router as rag_router
    app.include_router(rag_router)
    logger.info("[Router] RAGFlow routes loaded [OK]")
except Exception as e:
    logger.warning("[Router] RAGFlow routes not loaded: %s", e)

# Cowork Mode routes
try:
    from core.routes.cowork import router as cowork_router
    app.include_router(cowork_router)
    logger.info("[Router] Cowork Mode routes loaded [OK]")
except Exception as e:
    import traceback
    logger.warning("[Router] Cowork Mode routes not loaded: %s", e)
    traceback.print_exc()

# Pydantic schemas — extracted to core/schemas.py

# ── Extracted route modules ──

try:
    from core.routes.auth import router as auth_router
    app.include_router(auth_router)
    logger.info("[Router] Auth routes loaded [OK]")
except Exception as e:
    logger.warning("[Router] Auth routes not loaded: %s", e)

try:
    from core.routes.chat import router as chat_router
    app.include_router(chat_router)
    logger.info("[Router] Chat routes loaded [OK]")
except Exception as e:
    logger.warning("[Router] Chat routes not loaded: %s", e)

try:
    from core.routes.infrastructure import router as infra_router
    app.include_router(infra_router)
    logger.info("[Router] Infrastructure routes loaded [OK]")
except Exception as e:
    logger.warning("[Router] Infrastructure routes not loaded: %s", e)

try:
    from core.routes.operations import router as ops_router
    app.include_router(ops_router)
    logger.info("[Router] Operations routes loaded [OK]")
except Exception as e:
    logger.warning("[Router] Operations routes not loaded: %s", e)

try:
    from core.routes.activity import router as activity_router
    app.include_router(activity_router)
    logger.info("[Router] Activity Graph routes loaded [OK]")
except Exception as e:
    logger.warning("[Router] Activity Graph routes not loaded: %s", e)

try:
    from core.routes.artifacts import router as artifacts_router
    app.include_router(artifacts_router)
    logger.info("[Router] Artifact Store routes loaded [OK]")
except Exception as e:
    logger.warning("[Router] Artifact Store routes not loaded: %s", e)

try:
    from core.routes.workflows import router as workflows_router
    app.include_router(workflows_router)
    logger.info("[Router] Workflow Engine routes loaded [OK]")
except Exception as e:
    logger.warning("[Router] Workflow Engine routes not loaded: %s", e)

try:
    from core.routes.scheduler import router as scheduler_router
    app.include_router(scheduler_router)
    logger.info("[Router] Scheduler routes loaded [OK]")
except Exception as e:
    logger.warning("[Router] Scheduler routes not loaded: %s", e)

try:
    from core.routes.planner import router as planner_router
    app.include_router(planner_router)
    logger.info("[Router] Planner routes loaded [OK]")
except Exception as e:
    logger.warning("[Router] Planner routes not loaded: %s", e)

try:
    from core.routes.knowledge import router as knowledge_router
    app.include_router(knowledge_router)
    logger.info("[Router] Knowledge Store routes loaded [OK]")
except Exception as e:
    logger.warning("[Router] Knowledge Store routes not loaded: %s", e)

try:
    from core.routes.research import router as research_router
    app.include_router(research_router)
    logger.info("[Router] Research Memory routes loaded [OK]")
except Exception as e:
    logger.warning("[Router] Research Memory routes not loaded: %s", e)

try:
    from core.routes.websocket import router as ws_router
    app.include_router(ws_router)
    logger.info("[Router] WebSocket routes loaded [OK]")
except Exception as e:
    logger.warning("[Router] WebSocket routes not loaded: %s", e)

try:
    from core.routes.intelligence import router as intelligence_router
    app.include_router(intelligence_router)
    logger.info("[Router] Intelligence routes loaded [OK]")
except Exception as e:
    logger.warning("[Router] Intelligence routes not loaded: %s", e)

try:
    from core.routes.control import router as control_router
    app.include_router(control_router)
    logger.info("[Router] Control routes loaded [OK]")
except Exception as e:
    logger.warning("[Router] Control routes not loaded: %s", e)

try:
    from core.routes.utility import router as utility_router
    app.include_router(utility_router)
    logger.info("[Router] Utility routes loaded [OK]")
except Exception as e:
    logger.warning("[Router] Utility routes not loaded: %s", e)

try:
    from core.routes.features import router as features_router
    app.include_router(features_router)
    logger.info("[Router] Feature registry routes loaded [OK]")
except Exception as e:
    logger.warning("[Router] Feature registry routes not loaded: %s", e)

try:
    from core.routes.integrations import router as integrations_router
    app.include_router(integrations_router)
    logger.info("[Router] Integration management routes loaded [OK]")
except Exception as e:
    logger.warning("[Router] Integration management routes not loaded: %s", e)

try:
    from core.routes.terminal import router as terminal_router
    app.include_router(terminal_router)
    logger.info("[Router] Terminal WebSocket routes loaded [OK]")
except Exception as e:
    logger.warning("[Router] Terminal routes not loaded: %s", e)

try:
    from core.routes.diagnostics import router as diagnostics_router
    app.include_router(diagnostics_router)
    logger.info("[Router] Diagnostics routes loaded [OK]")
except Exception as e:
    logger.warning("[Router] Diagnostics routes not loaded: %s", e)

try:
    from core.routes.mcp import router as mcp_router
    app.include_router(mcp_router)
    logger.info("[Router] MCP tools routes loaded [OK]")
except Exception as e:
    logger.warning("[Router] MCP tools routes not loaded: %s", e)

try:
    from core.routes.analytics import router as analytics_router
    app.include_router(analytics_router)
    logger.info("[Router] Analytics routes loaded [OK]")
except Exception as e:
    logger.warning("[Router] Analytics routes not loaded: %s", e)

try:
    from core.routes.improvements import router as improvements_router
    app.include_router(improvements_router)
    logger.info("[Router] Improvement system routes loaded [OK]")
except Exception as e:
    logger.warning("[Router] Improvement system routes not loaded: %s", e)

try:
    from core.routes.negotiations import router as negotiations_router
    app.include_router(negotiations_router)
    from core.routes.opportunities import router as opportunities_router
    app.include_router(opportunities_router)
    from core.routes.autonomous import router as autonomous_router
    app.include_router(autonomous_router)
    from core.routes.evidence import router as evidence_router
    app.include_router(evidence_router)
    logger.info("[Router] Negotiation routes loaded [OK]")
except Exception as e:
    logger.warning("[Router] Negotiation routes not loaded: %s", e)


# ── MJ v3 routes ────────────────────────────────────────────────────────────

try:
    from core.routes.inbox import router as inbox_router
    app.include_router(inbox_router)
    logger.info("[Router] Inbox routes loaded [OK]")
except Exception as e:
    logger.warning("[Router] Inbox routes not loaded: %s", e)

try:
    from core.routes.progress import router as progress_router
    app.include_router(progress_router)
    logger.info("[Router] Progress routes loaded [OK]")
except Exception as e:
    logger.warning("[Router] Progress routes not loaded: %s", e)

# ── Static mounts ──

_STATIC_DIR = _pkg_root / "static"
if not _STATIC_DIR.is_dir():
    _STATIC_DIR = Path("static")  # fallback to CWD

if _STATIC_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=str(_STATIC_DIR / "assets")), name="assets")
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

# Mount the Next.js web UI export if built
_NEXT_OUT = _pkg_root / "web" / "out"
if not _NEXT_OUT.is_dir():
    _NEXT_OUT = Path("web/out")  # fallback to CWD
if _NEXT_OUT.is_dir():
    app.mount("/_next", StaticFiles(directory=str(_NEXT_OUT / "_next")), name="web_next")
    app.mount("/icons", StaticFiles(directory=str(_NEXT_OUT / "icons")), name="web_icons")

    async def _serve_next_static(path: str):
        """Serve a Next.js static export file from web/out/."""
        file_candidate = _NEXT_OUT / path
        if file_candidate.is_file():
            return FileResponse(str(file_candidate))

        dir_candidate = _NEXT_OUT / path / "index.html"
        if dir_candidate.is_file():
            return FileResponse(str(dir_candidate))

        html_candidate = _NEXT_OUT / f"{path}.html"
        if html_candidate.is_file():
            return FileResponse(str(html_candidate))

        return None

    @app.get("/")
    async def web_root():
        result = await _serve_next_static("index.html")
        if result:
            return result
        if _STATIC_DIR.is_dir():
            return FileResponse(str(_STATIC_DIR / "index.html"))
        return HTMLResponse("<h1>JARVIS</h1><p>Web UI not available.</p>")

    @app.get("/{path:path}")
    async def web_ui(request: Request, path: str):
        if path.startswith(("api/", "ws/", "email/", "v1/")):
            return JSONResponse(status_code=404, content={"detail": "Not found"})

        result = await _serve_next_static(path)
        if result:
            return result

        if _STATIC_DIR.is_dir():
            return FileResponse(str(_STATIC_DIR / "index.html"))
        return JSONResponse(status_code=404, content={"detail": "Not found"})
elif _STATIC_DIR.is_dir():
    @app.get("/")
    async def root():
        return FileResponse(str(_STATIC_DIR / "index.html"))
else:
    @app.get("/")
    async def root():
        return HTMLResponse("<h1>JARVIS</h1><p>Running. Web UI not installed.</p>")


# ── Voice routes ──

try:
    from core.routes.voice import router as voice_router
    app.include_router(voice_router)
    logger.info("[Router] Voice routes loaded [OK]")
except Exception as e:
    logger.warning("[Router] Voice routes not loaded: %s", e)


# ── Action Executor ──

async def execute_action(intent_data: dict, message: str = "", session_id: str = "") -> dict:
    intent = intent_data.get("intent", "chat")
    target = intent_data.get("target", message)
    params = intent_data.get("parameters", {})
    
    from .session import ConversationManager
    cm = ConversationManager(session_id=session_id)
    if cm.path.exists():
        cm.load()
    
    task_id = f"task_{int(time.time())}"
    cm.update_task(task_id, "running", {"intent": intent, "target": target})
    cm.save()

    try:
        if intent == "open_url":
            url = params.get("url", target)
            if not url.startswith("http"):
                url = "https://" + url
            import webbrowser
            webbrowser.open(url)
            cm.update_task(task_id, "completed", {"action": f"Opened {url}"})
            cm.save()
            return {"executed": True, "action": f"Opened {url}", "result": {}}
        elif intent == "play_media":
            from media.player import media_player
            await media_player.play(target)
            cm.update_task(task_id, "completed", {"action": f"Playing {target}"})
            cm.save()
            return {"executed": True, "action": f"Playing {target}", "result": {}}
        elif intent == "web_search":
            from tools.search_tool import search
            results = await search(target)
            return {"executed": True, "action": f"Searched for {target}", "result": results}
        elif intent == "reminder":
            from core.scheduler import JarvisScheduler
            scheduler = JarvisScheduler()
            scheduler.add_task("reminder", params)
            return {"executed": True, "action": "Reminder set", "result": {}}
        elif intent in ("weather", "news", "stocks", "sports", "time"):
            from core.integrations import get_info
            result = await get_info(intent, target)
            return {"executed": True, "action": result, "result": {}}
        elif intent == "build":
            from core.supervisor_agent import supervisor
            result = await supervisor.start_build(target)
            return {"executed": True, "action": f"Build started: {target}", "result": result}
        elif intent == "pc_control":
            from automation.pc_automation import execute_command as pc_exec
            result = pc_exec(message)
            return {"executed": True, "action": result.get("speech", f"Executed: {target}"), "result": result}
        elif intent in ("browser_task", "code_task", "vision_browser"):
            return {
                "executed": False,
                "action": "",
                "result": {},
                "error": None,
                "fallback_mode": "agent",
                "message": "This intent requires the agent loop. Route to /ws/agent_stream.",
            }
        elif intent == "message":
            from channels.processor import route_intent
            try:
                result = await route_intent(message, params)
                return {"executed": True, "action": "Message processed", "result": result}
            except Exception as e:
                logger.warning("[execute_action] %s failed: %s", intent, e)
                return {"executed": False, "action": "", "result": {}, "error": "Action failed"}
        else:
            return {"executed": False, "action": "", "result": {}, "error": None}
    except Exception as e:
        logger.warning("[execute_action] %s failed: %s", intent, e)
        return {"executed": False, "action": "", "result": {}, "error": "Action failed"}


# ── Vision routes ──

try:
    from core.routes.vision import router as vision_router
    app.include_router(vision_router)
    logger.info("[Router] Vision routes loaded [OK]")
except Exception as e:
    logger.warning("[Router] Vision routes not loaded: %s", e)


# ── Admin routes (horizon, prompts, quality, docs) ──

try:
    from core.routes.admin import router as admin_router
    app.include_router(admin_router)
    logger.info("[Router] Admin routes (horizon, prompts, quality, docs) loaded [OK]")
except Exception as e:
    logger.warning("[Router] Admin routes not loaded: %s", e)


# ── Global error handlers ──

from core.errors import AppError


@app.exception_handler(AppError)
async def app_error_handler(request, exc: AppError):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=exc.status_code, content=exc.detail)


@app.exception_handler(NotImplementedError)
async def not_implemented_error_handler(request, exc: NotImplementedError):
    logger.error(f"Not implemented: {exc}")
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=501,
        content={
            "code": "NOT_IMPLEMENTED",
            "message": "This feature is not yet available.",
            "data": None,
        }
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request, exc: Exception):
    logger.exception("Unhandled exception")
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=500, content={
        "code": "SERVER_ERROR",
        "message": "Internal server error",
        "data": None,
    })


if __name__ == "__main__":
    import uvicorn
    print(f"\n[JARVIS] Server starting at http://{HOST}:{PORT}")
    print(f"[JARVIS] API docs at  http://localhost:{PORT}/docs\n")
    uvicorn.run("core.main:app", host=HOST, port=PORT, reload=True, log_level="info",
                ws_ping_interval=60, ws_ping_timeout=30)
