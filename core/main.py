
"""
core/main.py â€” JARVIS FastAPI server: all routes + WebSocket + startup
"""
import os
import sys
import io
import logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

logger = logging.getLogger("jarvis")
logger.setLevel(logging.DEBUG)
if not logger.handlers:
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%H:%M:%S")
    ch.setFormatter(fmt)
    logger.addHandler(ch)

import asyncio
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
from datetime import datetime
from typing import Optional, List, Literal

from fastapi import FastAPI, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect, UploadFile, File, Form, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
import base64
import httpx
import webbrowser
import subprocess
import json
import re
import urllib.parse
try:
    import numpy as np
except ImportError:
    np = None
try:
    import cv2
except ImportError:
    cv2 = None
try:
    import instructor
except ImportError:
    instructor = None
try:
    from openai import OpenAI
except ImportError:
    OpenAI = None
try:
    from smolagents import ToolCallingAgent, tool, LiteLLMModel
except ImportError:
    tool = lambda f: f
    ToolCallingAgent = None
    LiteLLMModel = None

# COMPOSIO_TOOLS loaded lazily in _get_action_agent()
_COMPOSIO_TOOLS_CACHE = None

from brain.epistemic_tagger import epistemic_tagger
from .config import HOST, PORT, ALLOWED_ORIGINS
from .database import get_db, init_db, User
from .auth import verify_token, init_firebase
from .config import SUPABASE_URL, SUPABASE_SERVICE_KEY

from .lifespan import lifespan, startup_status
from .request_id import RequestIDMiddleware
from .rate_limiter import api_rate_limiter

app = FastAPI(
    title="JARVIS API",
    description="Personal AI Life Operating System",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security headers middleware
@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com; style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com; connect-src 'self' ws:; img-src 'self' data: https:; font-src 'self' https://cdnjs.cloudflare.com"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response

# Rate-limiting middleware â€” global 120 req/min per IP, exempts health/docs/static
@app.middleware("http")
async def rate_limit_middleware(request, call_next):
    exempt = ("/health", "/docs", "/openapi.json", "/redoc", "/static")
    if not request.url.path.startswith(exempt):
        ip = request.client.host if request.client else "unknown"
        if not api_rate_limiter.check("api", ip):
            return JSONResponse(status_code=429, content={"detail": "rate_limit_exceeded"})
    return await call_next(request)

# Plugin hook middleware â€” runs on_request / on_response for each registered plugin
@app.middleware("http")
async def plugin_hook_middleware(request, call_next):
    registry = getattr(request.app.state, "plugin_registry", None)
    if registry and registry._loaded:
        try:
            req_data = {"method": request.method, "path": request.url.path, "headers": dict(request.headers)}
            await registry.run_hook("on_request", request_data=req_data)
        except Exception:
            pass
    response = await call_next(request)
    if registry and registry._loaded:
        try:
            resp_data = {"status_code": response.status_code, "path": request.url.path}
            await registry.run_hook("on_response", response_data=resp_data)
        except Exception:
            pass
    return response

# Request-ID tracing middleware â€” logs every request with timing
app.add_middleware(RequestIDMiddleware)

# Optional routers (kept separate so missing optional deps don't break startup)
try:
    from api.vision_routes import router as vision_router
    app.include_router(vision_router)
except Exception as e:
    logger.warning("[Router] Vision routes not loaded: %s", e)

try:
    from api.cookbook_routes import router as cookbook_router
    app.include_router(cookbook_router)
    logger.info("[Router] Cookbook routes loaded")
except Exception as e:
    logger.warning("[Router] Cookbook routes not loaded: %s", e)

try:
    from api.research_routes import router as research_router
    app.include_router(research_router)
    logger.info("[Router] Research routes loaded")
except Exception as e:
    logger.warning("[Router] Research routes not loaded: %s", e)

try:
    from api.email_routes import router as email_router
    app.include_router(email_router)
    logger.info("[Router] Email routes loaded")
except Exception as e:
    logger.warning("[Router] Email routes not loaded: %s", e)

@app.get("/manifest.json")
async def serve_manifest():
    return FileResponse("static/manifest.json", media_type="application/manifest+json")

@app.get("/sw.js")
async def serve_sw():
    return FileResponse("static/sw.js", media_type="application/javascript")

try:
    from api.os_routes import router as os_router
    app.include_router(os_router)
    logger.info("[Router] AI OS routes loaded")
except Exception as e:
    logger.warning("[Router] AI OS routes not loaded: %s", e)

try:
    from api.ai_os_routes import router as ai_os_router
    app.include_router(ai_os_router)
    logger.info("[Router] AI OS CUSTOM routes loaded")
except Exception as e:
    logger.warning("[Router] AI OS CUSTOM routes not loaded: %s", e)

try:
    from automation.routes import router as automation_router
    app.include_router(automation_router)
except Exception as e:
    logger.warning("[Router] Automation routes not loaded: %s", e)

try:
    from routers.whatsapp import router as whatsapp_router
    app.include_router(whatsapp_router)
    logger.info("[Router] WhatsApp webhook routes loaded [OK]")
except Exception as e:
    logger.warning("[Router] WhatsApp routes not loaded: %s", e)

try:
    from automation.call_sync_server import get_fastapi_router
    app.include_router(get_fastapi_router())
except Exception as e:
    logger.warning("[Router] Call sync routes not loaded: %s", e)

try:
    from api.hybrid_integration import setup_hybrid_routes
    setup_hybrid_routes(app)
    logger.info("[Router] Hybrid Automation routes loaded [OK]")
except Exception as e:
    logger.warning("[Router] Hybrid Automation routes not loaded: %s", e)

try:
    from routers.chat import chat_handler as three_pass_handler
except Exception as e:
    three_pass_handler = None

# Student AGI System â€” optional separate service
# Runs as: python learning/student_agi/student_agi_main.py
# Can be called via /student-agi/... endpoints when available
try:
    from learning.student_agi.api.student_routes import router as student_router
    app.include_router(student_router, prefix="/student-agi", tags=["Student AGI"])
    logger.info("[Router] Student AGI routes loaded")
except Exception as e:
    logger.warning("[Router] Student AGI routes not loaded (service may not be started): %s", e)

# Agent Orchestrator â€” goal/plan/execution routes
try:
    from core.plan_routes import router as plan_router
    app.include_router(plan_router)
    logger.info("[Router] Agent Orchestrator routes loaded [OK]")
except Exception as e:
    logger.warning("[Router] Agent Orchestrator routes not loaded: %s", e)

# Supervisor â€” autonomous multi-agent build orchestrator
try:
    from core.supervisor_agent import supervisor
    from notifications.notifier import notifier
    supervisor.on_notify(notifier.notify)
    from core.supervisor_routes import router as supervisor_router
    app.include_router(supervisor_router)
    logger.info("[Router] Supervisor routes loaded [OK]")
except Exception as e:
    logger.warning("[Router] Supervisor routes not loaded: %s", e)

# Build System â€” control loop, project management, daemon
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

# JARVIS Sub-Agents — 10 specialized agents

try:
    from api.agent_routes import router as agent_router
    app.include_router(agent_router, prefix="/api/v1")
    logger.info("[Router] JARVIS Sub-Agents routes loaded [OK]")
except Exception as e:
    logger.warning("[Router] Sub-Agents routes not loaded: %s", e)


# AGI routes — /agi/status, /agi/solve, /agi/agents, etc.
try:
    from api.agi_routes import router as agi_router
    app.include_router(agi_router)
    logger.info("[Router] AGI routes loaded [OK]")
except Exception as e:
    logger.warning("[Router] AGI routes not loaded: %s", e)


# Website Generator routes — /website/generate, /website/status, etc.
try:
    from api.website_routes import router as website_router
    app.include_router(website_router)
    logger.info("[Router] Website Generator routes loaded [OK]")
except Exception as e:
    logger.warning("[Router] Website Generator routes not loaded: %s", e)


# Plugin System routes — /plugins/*
try:
    from api.plugin_routes import router as plugin_router
    app.include_router(plugin_router)
    logger.info("[Router] Plugin System routes loaded [OK]")
except Exception as e:
    logger.warning("[Router] Plugin System routes not loaded: %s", e)


# Cloud / Project routes — /cloud/*, /projects/*
try:
    from api.cloud_routes import router as cloud_router
    app.include_router(cloud_router)
    logger.info("[Router] Cloud routes loaded [OK]")
except Exception as e:
    logger.warning("[Router] Cloud routes not loaded: %s", e)


# Governance routes — /governance/*
try:
    from api.governance_routes import router as gov_router
    app.include_router(gov_router)
    logger.info("[Router] Governance routes loaded [OK]")
except Exception as e:
    logger.warning("[Router] Governance routes not loaded: %s", e)

# Memory routes — /memory/*
try:
    from api.memory_routes import router as memory_router
    app.include_router(memory_router)
    logger.info("[Router] Memory routes loaded [OK]")
except Exception as e:
    logger.warning("[Router] Memory routes not loaded: %s", e)

# RAGFlow routes — /rag/*
try:
    from api.ragflow_routes import router as rag_router
    app.include_router(rag_router)
    logger.info("[Router] RAGFlow routes loaded [OK]")
except Exception as e:
    logger.warning("[Router] RAGFlow routes not loaded: %s", e)


# Cowork Mode routes â€” files, skills, builds
try:
    from fastapi import APIRouter
    cowork = APIRouter(prefix="/cowork", tags=["Cowork"])

    # â”€â”€ File Agent routes â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    @cowork.post("/files/read")
    async def cowork_file_read(path: str = ""):
        from .file_agent import file_agent
        content = await file_agent.read_file(path)
        return {"path": path, "content": content, "size": len(content)}

    @cowork.post("/files/write")
    async def cowork_file_write(path: str = "", content: str = ""):
        from .file_agent import file_agent
        await file_agent.write_file(path, content)
        return {"path": path, "written": True, "size": len(content)}

    @cowork.post("/files/organize")
    async def cowork_file_organize(folder: str = "", instruction: str = ""):
        from .file_agent import file_agent
        result = await file_agent.organize_folder(folder, instruction)
        return result

    @cowork.post("/files/generate")
    async def cowork_file_generate(template: str = "", data: dict = {}, output_path: str = ""):
        from .file_agent import file_agent
        await file_agent.generate_document(template, data, output_path)
        return {"output_path": output_path, "status": "generated"}

    @cowork.get("/files/list")
    async def cowork_file_list(folder: str = "", pattern: str = ""):
        from .file_agent import file_agent
        files = await file_agent.list_files(folder, pattern)
        return {"folder": folder, "files": files, "count": len(files)}

    # â”€â”€ Skills routes â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    @cowork.post("/skills/create")
    async def cowork_skill_create(name: str = "", description: str = "", template: str = ""):
        from .database import AsyncSessionLocal, JarvisSkill
        from sqlalchemy import select
        async with AsyncSessionLocal() as session:
            existing = await session.execute(select(JarvisSkill).where(JarvisSkill.name == name))
            if existing.scalar_one_or_none():
                raise HTTPException(400, f"Skill '{name}' already exists")
            skill = JarvisSkill(name=name, description=description, template=template)
            session.add(skill)
            await session.commit()
            await session.refresh(skill)
            return {"id": skill.id, "name": skill.name, "status": "created"}

    @cowork.get("/skills/list")
    async def cowork_skills_list():
        from .database import AsyncSessionLocal, JarvisSkill
        from sqlalchemy import select
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(JarvisSkill).order_by(JarvisSkill.name))
            skills = result.scalars().all()
            return {"skills": [{"id": s.id, "name": s.name, "description": s.description, "template": s.template[:100]} for s in skills]}

    class SkillRunRequest(BaseModel):
        variables: dict = {}

    @cowork.post("/skills/run/{skill_name}")
    async def cowork_skill_run(skill_name: str, req: SkillRunRequest):
        from .database import AsyncSessionLocal, JarvisSkill
        from .llm_router import complete as llm_complete
        from sqlalchemy import select
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(JarvisSkill).where(JarvisSkill.name == skill_name))
            skill = result.scalar_one_or_none()
        if not skill:
            raise HTTPException(404, f"Skill '{skill_name}' not found")
        filled = skill.template
        for k, v in req.variables.items():
            filled = filled.replace("{" + k + "}", str(v))
        output = (await llm_complete("creative", [{"role": "user", "content": filled}])).unwrap_or("")
        return {"skill": skill_name, "input": filled, "output": output.strip()}

    # â”€â”€ Overnight Builder route â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    class BuildRequest(BaseModel):
        goal: str
        output_dir: str = "."

    @cowork.post("/build/overnight")
    async def cowork_overnight_build(req: BuildRequest):
        from .agent_executor import run_overnight_build
        task = asyncio.create_task(run_overnight_build(req.goal, req.output_dir))
        return {"status": "started", "goal": req.goal, "output_dir": req.output_dir, "message": "Overnight build running in background"}

    # â”€â”€ Scheduler management routes â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    class TaskAddRequest(BaseModel):
        task_id: str
        schedule: str
        action_type: str = "custom"
        params: dict = {}

    @cowork.post("/schedule/add")
    async def cowork_schedule_add(req: TaskAddRequest):
        from .scheduler import scheduler
        scheduler.add_task(req.task_id, req.schedule, {"type": req.action_type, "params": req.params})
        return {"task_id": req.task_id, "schedule": req.schedule, "status": "scheduled"}

    @cowork.get("/schedule/list")
    async def cowork_schedule_list():
        from .scheduler import scheduler
        return {"tasks": scheduler.get_tasks()}

    @cowork.post("/schedule/remove/{task_id}")
    async def cowork_schedule_remove(task_id: str):
        from .scheduler import scheduler
        scheduler.remove_task(task_id)
        return {"task_id": task_id, "status": "removed"}

    app.include_router(cowork)
    logger.info("[Router] Cowork Mode routes loaded [OK]")
except Exception as e:
    import traceback
    logger.warning("[Router] Cowork Mode routes not loaded: %s", e)
    traceback.print_exc()


# Pydantic schemas â€” extracted to core/schemas.py
from .schemas import (
    ChatRequest, BrowserActionRequest, ReminderCreate, NoteCreate, NoteUpdate,
    MessageRequest, FaceRegisterRequest, IntentResult, CodeReviewRequest, QualityGradeRequest,
)

if three_pass_handler:
    @app.post("/api/chat")
    async def chat_route(req: ChatRequest):
        # Phase 3: mem0 + RAGFlow Integration
        user_id = req.session_id or "default_user"
        
        # 1. Retrieve relevant memories
        from memory.mem0_adapter import mem0_memory
        memories = mem0_memory.search(req.message, user_id=user_id, limit=5)
        memory_context = mem0_memory.format_context(memories)

        # 2. Retrieve RAGFlow document context
        from tools.ragflow_tool import ragflow_search, format_rag_context
        rag_result = await ragflow_search(req.message, top_k=5)
        rag_context = format_rag_context(rag_result.get("chunks", []))

        # Enhance req.context
        combined_context = req.context or ""
        if memory_context:
            combined_context = memory_context + "\n\n" + combined_context
        if rag_context:
            combined_context = rag_context + "\n\n" + combined_context
        
        req.context = combined_context.strip()

        # Call original handler
        result = await three_pass_handler(req)
        
        # After getting response, store the exchange:
        response_text = result.get("response", "")
        mem0_memory.add(
            [{"role": "user", "content": req.message}, {"role": "assistant", "content": response_text}],
            user_id=user_id,
        )
        
        return result
    logger.info("[Router] POST /api/chat route loaded")
else:
    logger.warning("[Router] POST /api/chat route not loaded: chat_handler unavailable")


# ==============================================
#  ROUTES â€” HEALTH
# ==============================================
@app.get("/")
async def root():
    return FileResponse("static/index.html")

# ==============================================
#  OPENAI COMPATIBILITY — /v1/chat/completions
# ==============================================
@app.post("/v1/chat/completions")
async def openai_compat(body: dict):
    """
    OpenAI-compatible endpoint for tools like Open WebUI.
    Routes to Jarvis's three-pass chat handler.
    """
    messages = body.get("messages", [])
    if not messages:
        raise HTTPException(400, "No messages provided")

    # Extract last user message and context
    last_msg = messages[-1].get("content", "")
    context = "\n".join([f"{m['role']}: {m['content']}" for m in messages[:-1]])

    from core.schemas import ChatRequest
    req = ChatRequest(message=last_msg, context=context)

    try:
        if three_pass_handler:
            result = await three_pass_handler(req)
            content = result.get("response", "")
        else:
            from core.llm_router import complete
            res = await complete(last_msg, context=context)
            content = res.unwrap_or("Error processing request.")

        return {
            "id": f"chatcmpl-{uuid.uuid4()}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": body.get("model", "jarvis-reasoning"),
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": content,
                },
                "finish_reason": "stop"
            }],
            "usage": {
                "prompt_tokens": len(last_msg) // 4,
                "completion_tokens": len(content) // 4,
                "total_tokens": (len(last_msg) + len(content)) // 4
            }
        }
    except Exception as e:
        logger.error(f"[OpenAI Compat] Error: {e}")
        raise HTTPException(500, str(e))

# ==============================================
#  ROUTES — OAUTH FLOW
# ==============================================
@app.get("/auth/providers")
async def oauth_providers():
    from .oauth import oauth_manager
    return {"providers": oauth_manager.get_providers()}


@app.get("/auth/tokens")
async def oauth_tokens():
    from .oauth import oauth_manager
    return {"tokens": oauth_manager.list_tokens()}


@app.get("/auth/login/{provider}")
async def oauth_login(provider: str, request: Request):
    from .oauth import oauth_manager
    redirect_uri = str(request.url_for("oauth_callback"))
    return await oauth_manager.authorize_redirect(provider, request, redirect_uri)


@app.get("/auth/callback")
async def oauth_callback(request: Request):
    from .oauth import oauth_manager
    provider = request.query_params.get("provider", "")
    if not provider:
        for p in oauth_manager.get_providers():
            if request.query_params.get("code") or request.query_params.get("state", "").startswith(p):
                provider = p
                break
    result = await oauth_manager.authorize_access_token(provider or "google", request)
    if result:
        return {"success": True, "user": result["userinfo"]}
    return {"success": False, "error": "OAuth failed"}


@app.post("/auth/revoke")
async def oauth_revoke(body: dict):
    from .oauth import oauth_manager
    provider = body.get("provider", "")
    sub = body.get("sub", "")
    ok = oauth_manager.remove_token(provider, sub)
    return {"success": ok}


# ==============================================
#  ROUTES â€” DOCKER SANDBOX
# ==============================================
@app.get("/api/sandbox/status")
async def sandbox_status():
    from ai_os.docker_sandbox import docker_sandbox
    return {"available": docker_sandbox.available}


@app.post("/api/sandbox/exec")
async def sandbox_exec(body: dict):
    from ai_os.docker_sandbox import docker_sandbox
    if not docker_sandbox.available:
        raise HTTPException(503, "Docker sandbox not available")
    code = body.get("code", "")
    if not code:
        raise HTTPException(400, "code is required")
    result = await docker_sandbox.exec_python(code=code, timeout=body.get("timeout", 30))
    return result


# ==============================================
#  ROUTES â€” STT PROVIDERS
# ==============================================
@app.get("/api/stt/providers")
async def stt_list_providers():
    from assistant.stt_protocol import stt_registry
    from assistant.stt import init_stt_providers
    if not stt_registry.list():
        init_stt_providers()
    return {"providers": stt_registry.list(), "default": stt_registry.default}


# ==============================================
#  ROUTES â€” PLUGINS
# ==============================================
@app.get("/api/plugins")
async def list_plugins():
    registry = getattr(app.state, "plugin_registry", None)
    if not registry:
        return {"plugins": [], "total": 0}
    plugins = []
    for name, plugin in registry.plugins.items():
        try:
            health = await plugin.health_check()
        except Exception:
            health = {"healthy": False}
        plugins.append({
            "name": name,
            "version": plugin.manifest.version,
            "description": plugin.manifest.description,
            "hooks": plugin.manifest.hooks,
            "health": health,
        })
    return {"plugins": plugins, "total": registry.count}


# ==============================================
#  ROUTES â€” BACKUP
# ==============================================
@app.post("/api/backup/create")
async def backup_create():
    bm = getattr(app.state, "backup_manager", None)
    if not bm:
        raise HTTPException(503, "Backup manager not available")
    result = await bm.create_backup()
    return result


@app.get("/api/backup/list")
async def backup_list():
    bm = getattr(app.state, "backup_manager", None)
    if not bm:
        return {"backups": []}
    return {"backups": bm.list_backups()}


@app.post("/api/backup/restore")
async def backup_restore(body: dict):
    bm = getattr(app.state, "backup_manager", None)
    if not bm:
        raise HTTPException(503, "Backup manager not available")
    path = body.get("path", "")
    result = await bm.restore_backup(path)
    return result


# ==============================================
#  ROUTES â€” CRON
# ==============================================
@app.get("/api/cron/jobs")
async def cron_list_jobs():
    cs = getattr(app.state, "cron_scheduler", None)
    if not cs:
        return {"jobs": []}
    return {"jobs": cs.list_jobs()}


@app.post("/api/cron/jobs")
async def cron_add_job(body: dict):
    cs = getattr(app.state, "cron_scheduler", None)
    if not cs:
        raise HTTPException(503, "Cron scheduler not available")
    job = cs.add_job(
        job_id=body.get("id", f"job_{len(cs.list_jobs())}"),
        schedule=body.get("schedule", "24h"),
        action=body.get("action", "custom"),
        params=body.get("params"),
    )
    return job


@app.delete("/api/cron/jobs/{job_id}")
async def cron_remove_job(job_id: str):
    cs = getattr(app.state, "cron_scheduler", None)
    if not cs:
        raise HTTPException(503, "Cron scheduler not available")
    ok = cs.remove_job(job_id)
    return {"removed": ok}


# ==============================================
#  ROUTES â€” SKILLS
# ==============================================
@app.get("/api/skills")
async def skills_list():
    sm = getattr(app.state, "skill_manager", None)
    if not sm:
        return {"skills": []}
    return {"skills": sm.list()}


# ==============================================
#  ROUTES â€” SECURITY AUDIT
# ==============================================
@app.post("/api/security/audit")
async def security_run_audit():
    from .security_audit import security_auditor
    report = await security_auditor.run_full_audit()
    return report


# ==============================================
#  ROUTES â€” MEDIA GENERATION
# ==============================================
@app.post("/api/media/generate/image")
async def generate_image(body: dict):
    from tools.image_gen import image_generator
    prompt = body.get("prompt", "")
    if not prompt:
        raise HTTPException(400, "prompt is required")
    urls = await image_generator.generate(
        prompt=prompt,
        size=body.get("size", "1024x1024"),
        n=body.get("n", 1),
    )
    return {"success": len(urls) > 0, "urls": urls, "prompt": prompt}


# ==============================================
#  ROUTES â€” COMMITMENTS
# ==============================================
@app.get("/api/commitments")
async def commitments_list(status: str | None = None):
    ct = getattr(app.state, "commitment_tracker", None)
    if not ct:
        return {"commitments": []}
    return {"commitments": ct.list(status=status)}


@app.post("/api/commitments")
async def commitments_add(body: dict):
    ct = getattr(app.state, "commitment_tracker", None)
    if not ct:
        raise HTTPException(503, "Commitment tracker not available")
    cmt = ct.add(
        description=body.get("description", ""),
        source=body.get("source", "api"),
        due=body.get("due"),
        priority=body.get("priority", "medium"),
    )
    return cmt


@app.post("/api/commitments/{cmt_id}/complete")
async def commitments_complete(cmt_id: str):
    ct = getattr(app.state, "commitment_tracker", None)
    if not ct:
        raise HTTPException(503, "Commitment tracker not available")
    ok = ct.complete(cmt_id)
    return {"success": ok}


@app.post("/api/commitments/{cmt_id}/dismiss")
async def commitments_dismiss(cmt_id: str):
    ct = getattr(app.state, "commitment_tracker", None)
    if not ct:
        raise HTTPException(503, "Commitment tracker not available")
    ok = ct.dismiss(cmt_id)
    return {"success": ok}


# ==============================================
#  ROUTES â€” CHANNEL INTEGRATIONS
# ==============================================
@app.get("/api/channels")
async def list_channels():
    controller = getattr(app.state, "channel_controller", None)
    if not controller:
        return {"channels": [], "total": 0}
    channels = []
    for cid, channel in controller.channels.items():
        channels.append({
            "id": cid,
            "name": channel.name,
            "description": channel.description,
            "running": channel.is_running,
            "config": {
                "enabled": channel.config.enabled if channel.config else False,
            },
        })
    return {"channels": channels, "total": len(channels)}


@app.post("/api/channels/send")
async def channel_send(
    req: MessageRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_token),
):
    controller = getattr(app.state, "channel_controller", None)
    if not controller:
        raise HTTPException(503, "Channel controller not available")
    channel = controller.get(req.platform)
    if not channel:
        raise HTTPException(400, f"Unknown channel '{req.platform}'. Available: {list(controller.channels.keys())}")
    if not channel.is_running:
        raise HTTPException(503, f"Channel '{req.platform}' is not running")
    success = await channel.send(req.recipient, req.message)
    from notes.activity_tracker import activity_tracker
    await activity_tracker.log(
        db, user.id, "message_sent",
        f"Sent {req.platform} message to {req.recipient}",
    )
    return {"success": success, "channel": req.platform, "recipient": req.recipient}


# ==============================================
#  ROUTES â€” SHOWCASE (3rd Particle UI)
# ==============================================
import calendar as _cal

@app.get("/showcase")
async def showcase():
    return FileResponse("jarvis_showcase.html")

@app.get("/api/monthly-highlights")
async def monthly_highlights():
    now = datetime.now()
    month_name = now.strftime("%B %Y")
    from core.database import get_db, ChatHistory, ExecutionLog
    from sqlalchemy import select, func, and_
    from datetime import datetime, timedelta
    
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    conversations = 0
    commands_executed = 0
    searches = 0
    reminders = 0
    
    try:
        async for session in get_db():
            # Count conversations (unique sessions this month)
            from core.database import ChatHistory, ExecutionLog
            from sqlalchemy import select, func, and_
            q_conv = select(func.count(func.distinct(ChatHistory.session_id))).where(ChatHistory.timestamp >= start_of_month)
            conversations = (await session.execute(q_conv)).scalar() or 0
            
            # Count commands executed
            q_cmd = select(func.count(ExecutionLog.id)).where(ExecutionLog.created_at >= start_of_month)
            commands_executed = (await session.execute(q_cmd)).scalar() or 0
            
            # Count searches
            q_search = select(func.count(ChatHistory.id)).where(
                and_(ChatHistory.timestamp >= start_of_month, ChatHistory.intent == "web_search")
            )
            searches = (await session.execute(q_search)).scalar() or 0
            
            from reminders.manager import count_reminders
            reminders = await count_reminders(session)
            break # Only need one session
    except Exception as e:
        logger.exception("[Stats] Failed to count highlights: %s", e)
        
    return {
        "month": month_name,
        "conversations": conversations,
        "commands_executed": commands_executed,
        "searches": searches,
        "reminders": reminders,
        "top_models": [
            os.getenv("CHAT_MODEL", "qwen3:4b"),
            os.getenv("CODE_MODEL", "qwen2.5-coder:3b"),
            os.getenv("VISION_MODEL", "moondream")
        ],
        "highlights": [
            "13 AI models running across 9 Ollama ports",
            "6 autonomous agents for diverse tasks",
            "54K+ lines of Python and TypeScript",
            "100% local privacy â€” zero cloud dependency"
        ]
    }

app.mount("/assets", StaticFiles(directory="static/assets"), name="assets")
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/health")
async def health():
    health_state = getattr(app.state, "health", None)
    ollama_ready = health_state.ollama_alive() if health_state else False
    
    # Actually test DB connectivity
    from core.database import AsyncSessionLocal
    from sqlalchemy import text
    db_connected = False
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
            db_connected = True
    except Exception:
        pass
        
    registry = getattr(app.state, "plugin_registry", None)
    return {
        "status": "ok",
        "ollama": ollama_ready,
        "db": db_connected,
        "plugins": registry.count if registry else 0,
        "version": "1.0.0",
    }


@app.post("/api/browser")
async def browser_action(
    req: BrowserActionRequest,
    user: User = Depends(verify_token),
):
    """Browser automation: navigate, fill forms, click, screenshot."""
    from tools.browser_tool import JarvisBrowser
    browser = JarvisBrowser(headless=True)
    try:
        if req.action == "navigate":
            if not req.url:
                return {"error": "url required for navigate"}
            result = await browser.navigate(req.url)
        elif req.action == "fill":
            if not req.selector or req.value is None:
                return {"error": "selector and value required for fill"}
            await browser._ensure()
            await browser._page.fill(req.selector, req.value)
            result = {"status": "success", "action": f"filled {req.selector}"}
        elif req.action == "click":
            if not req.selector:
                return {"error": "selector required for click"}
            await browser._ensure()
            await browser._page.click(req.selector)
            result = {"status": "success", "action": f"clicked {req.selector}"}
        elif req.action == "screenshot":
            await browser._ensure()
            await browser._page.wait_for_load_state()
            result = {"status": "success", "action": "screenshot captured"}
        elif req.action == "evaluate":
            if not req.script:
                return {"error": "script required for evaluate"}
            await browser._ensure()
            value = await browser._page.evaluate(req.script)
            result = {"status": "success", "value": str(value)[:1000]}
        else:
            return {"error": f"Unknown action: {req.action}, supported: navigate, fill, click, screenshot, evaluate"}
    finally:
        await browser.close()
    return result


@app.post("/api/generate-ui")
async def generate_ui(
    req: ChatRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_token),
):
    """Template-first UI generation. Finds a matching template and fills content."""
    from tools.template_library import TemplateLibrary

    tl = TemplateLibrary()
    if not tl.registry:
        tl._load_registry()

    if not tl.registry:
        return {"error": "No templates downloaded. Run: python -m tools.template_library", "code": None}

    description = req.message
    framework = req.context or "html"

    result = tl.generate_ui(description)
    if result.get("error"):
        return {"error": result["error"], "code": None}

    file_path = result["file_path"]
    code = Path(file_path).read_text(encoding="utf-8")

    return {
        "code": code,
        "file_path": file_path,
        "framework": framework,
        "template_name": result.get("template_name"),
        "template_category": result.get("template_category", []),
    }


@app.get("/api/chat/history")
async def get_chat_history(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_token),
    limit: int = 50,
    session_id: Optional[str] = Query(None),
):
    from sqlalchemy import select
    from core.database import ChatHistory
    q = select(ChatHistory).where(ChatHistory.user_id == user.id)
    if session_id:
        q = q.where(ChatHistory.session_id == session_id)
    result = await db.execute(
        q.order_by(ChatHistory.timestamp.desc()).limit(limit)
    )
    messages = result.scalars().all()
    return [{"role": m.role, "message": m.message, "ts": m.timestamp} for m in reversed(messages)]


@app.get("/api/sessions")
async def list_sessions(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_token),
):
    from sqlalchemy import select, func
    from core.database import ChatHistory
    result = await db.execute(
        select(ChatHistory.session_id, func.count(ChatHistory.id), func.min(ChatHistory.timestamp), func.max(ChatHistory.timestamp))
        .where(ChatHistory.user_id == user.id)
        .where(ChatHistory.session_id.isnot(None))
        .group_by(ChatHistory.session_id)
        .order_by(func.max(ChatHistory.timestamp).desc())
    )
    return [
        {"session_id": row[0], "count": row[1], "first": row[2].isoformat() if row[2] else None, "last": row[3].isoformat() if row[3] else None}
        for row in result
    ]


# ==============================================
#  ROUTES â€” REMINDERS
# ==============================================
@app.get("/api/reminders")
async def list_reminders(db: AsyncSession = Depends(get_db), user: User = Depends(verify_token)):
    from reminders.manager import get_user_reminders
    items = await get_user_reminders(db, user)
    return [{"id": r.id, "title": r.title, "remind_at": r.remind_at, "repeat": r.repeat, "description": r.description} for r in items]

@app.post("/api/reminders")
async def create_reminder_route(
    req: ReminderCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_token)
):
    from reminders.manager import create_reminder
    r = await create_reminder(db, user, req.title, req.remind_at, req.description, req.repeat)
    return {"id": r.id, "title": r.title, "remind_at": r.remind_at}

@app.delete("/api/reminders/{reminder_id}")
async def delete_reminder_route(
    reminder_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_token)
):
    from reminders.manager import delete_reminder
    success = await delete_reminder(db, user, reminder_id)
    if not success:
        raise HTTPException(404, "Reminder not found")
    return {"deleted": True}


# ==============================================
#  ROUTES â€” NOTES
# ==============================================
@app.get("/api/notes")
async def list_notes(db: AsyncSession = Depends(get_db), user: User = Depends(verify_token)):
    from notes.activity_tracker import notes_manager
    items = await notes_manager.get_all(db, user)
    return [{"id": n.id, "title": n.title, "content": n.content, "tags": n.tags, "updated_at": n.updated_at} for n in items]

@app.post("/api/notes")
async def create_note(req: NoteCreate, db: AsyncSession = Depends(get_db), user: User = Depends(verify_token)):
    from notes.activity_tracker import notes_manager
    n = await notes_manager.create(db, user, req.title, req.content, req.tags)
    return {"id": n.id, "title": n.title}

@app.put("/api/notes/{note_id}")
async def update_note(note_id: int, req: NoteUpdate, db: AsyncSession = Depends(get_db), user: User = Depends(verify_token)):
    from notes.activity_tracker import notes_manager
    n = await notes_manager.update(db, user, note_id, req.title, req.content)
    if not n:
        raise HTTPException(404, "Note not found")
    return {"id": n.id, "title": n.title}

@app.delete("/api/notes/{note_id}")
async def delete_note(note_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(verify_token)):
    from notes.activity_tracker import notes_manager
    success = await notes_manager.delete(db, user, note_id)
    if not success:
        raise HTTPException(404, "Note not found")
    return {"deleted": True}


# ==============================================
#  ROUTES â€” ACTIVITY & SUMMARY
# ==============================================
@app.get("/api/activity/today")
async def today_activity(db: AsyncSession = Depends(get_db), user: User = Depends(verify_token)):
    from notes.activity_tracker import activity_tracker
    items = await activity_tracker.get_today(db, user.id)
    return [{"type": a.activity_type, "description": a.description, "ts": a.timestamp} for a in items]

@app.get("/api/activity/summary")
async def daily_summary(db: AsyncSession = Depends(get_db), user: User = Depends(verify_token)):
    from notes.activity_tracker import summary_generator
    summary = await summary_generator.generate(db, user)
    return {
        "date": summary.date,
        "summary": summary.summary,
        "productivity_score": summary.productivity_score,
        "data": summary.raw_data
    }


# ==============================================
#  ROUTES â€” MESSAGING AUTOMATION
# ==============================================
@app.post("/api/message/send")
async def send_message(
    req: MessageRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_token)
):
    from notes.activity_tracker import activity_tracker

    controller = getattr(app.state, "channel_controller", None)
    if controller:
        channel = controller.get(req.platform)
        if channel:
            if not channel.is_running:
                raise HTTPException(503, f"Channel '{req.platform}' is not running")
            success = await channel.send(req.recipient, req.message)
            await activity_tracker.log(
                db, user.id, "message_sent",
                f"Sent {req.platform} message to {req.recipient}",
            )
            return {"success": success, "platform": req.platform, "recipient": req.recipient}

    from automation.messaging import messaging

    if req.platform == "whatsapp":
        success = messaging.send_whatsapp(req.recipient, req.message)
    elif req.platform == "instagram":
        success = messaging.send_instagram_dm(req.recipient, req.message)
    else:
        raise HTTPException(400, f"Unknown platform '{req.platform}'. Supported: discord, slack, telegram, matrix, irc, whatsapp, instagram")

    await activity_tracker.log(
        db, user.id, "message_sent",
        f"Sent {req.platform} message to {req.recipient}"
    )
    return {"success": success, "platform": req.platform, "recipient": req.recipient}


# ==============================================
#  ROUTES â€” FACE RECOGNITION
# ==============================================
@app.post("/api/faces/register")
async def register_face(
    person_name: str = Form(...),
    relation: str = Form("unknown"),
    info: str = Form(""),
    access_level: str = Form("visitor"),
    images: List[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_token)
):
    if np is None or cv2 is None:
        raise HTTPException(503, "numpy or opencv not installed (pip install numpy opencv-python)")
    from vision.face_recognition import face_recognizer
    frames = []
    for img_file in images:
        data = await img_file.read()
        nparr = np.frombuffer(data, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if frame is not None:
            frames.append(frame)

    if not frames:
        raise HTTPException(400, "No valid images provided")

    kf = await face_recognizer.register_face(db, user, person_name, frames, relation, info, access_level)
    return {"id": kf.id, "person_name": kf.person_name, "image_count": kf.image_count}


@app.post("/api/faces/identify")
async def identify_face(
    image: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_token)
):
    if np is None or cv2 is None:
        raise HTTPException(503, "numpy or opencv not installed (pip install numpy opencv-python)")
    from vision.face_recognition import face_recognizer
    data = await image.read()
    nparr = np.frombuffer(data, np.uint8)
    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    result = await face_recognizer.identify_and_lookup(db, user, frame)
    return result

@app.get("/api/faces")
async def list_faces(db: AsyncSession = Depends(get_db), user: User = Depends(verify_token)):
    from sqlalchemy import select
    from core.database import KnownFace
    result = await db.execute(select(KnownFace).where(KnownFace.owner_id == user.id))
    faces = result.scalars().all()
    return [{"id": f.id, "name": f.person_name, "relation": f.relation, "access_level": f.access_level, "image_count": f.image_count} for f in faces]


# ==============================================
#  ROUTES â€” MEDIA PLAYER
# ==============================================
@app.get("/api/media/status")
async def media_status():
    from media.player import media_player
    return media_player.get_status()

@app.post("/api/media/play")
async def media_play(track_index: Optional[int] = None, query: Optional[str] = None):
    from media.player import media_player
    if query:
        found = media_player.play_by_name(query)
        return {"playing": found}
    elif track_index is not None:
        media_player.play_by_index(track_index)
    else:
        media_player.play()
    return {"playing": True}

@app.post("/api/media/pause")
async def media_pause():
    from media.player import media_player
    media_player.pause()
    return {"paused": True}

@app.post("/api/media/next")
async def media_next():
    from media.player import media_player
    media_player.next_track()
    return media_player.get_status()

@app.post("/api/media/volume/{volume}")
async def set_volume(volume: int):
    from media.player import media_player
    media_player.set_volume(volume)
    return {"volume": volume}

@app.get("/api/media/playlist")
async def get_playlist():
    from media.player import media_player
    return media_player.get_playlist()

@app.get("/api/media/suggest/{mood}")
async def suggest_music(mood: str):
    from media.player import music_suggester, media_player
    status = media_player.get_status()
    if mood == "similar" and status.get("track"):
        return music_suggester.suggest_similar(status["track"])
    return music_suggester.suggest_by_mood(mood)


# ==============================================
#  ROUTES â€” FILE MANAGER
# ==============================================
@app.get("/api/files")
async def list_files(path: str = "~", user: User = Depends(verify_token)):
    import os
    home = os.path.realpath(os.path.expanduser("~"))
    resolved = os.path.realpath(os.path.expanduser(path))
    if os.name == "nt":
        if not resolved.casefold().startswith(home.casefold() + os.sep) and resolved.casefold() != home.casefold():
            raise HTTPException(403, "Access denied: path outside home directory")
    else:
        if not resolved.startswith(home + os.sep) and resolved != home:
            raise HTTPException(403, "Access denied: path outside home directory")
    if not os.path.exists(resolved):
        raise HTTPException(404, "Path not found")
    if not os.path.isdir(resolved):
        raise HTTPException(400, "Not a directory")

    from datetime import datetime
    entries = []
    for entry in os.scandir(resolved):
        try:
            entries.append({
                "name":     entry.name,
                "is_dir":   entry.is_dir(),
                "size":     entry.stat().st_size if entry.is_file() else 0,
                "modified": datetime.fromtimestamp(entry.stat().st_mtime).isoformat()
            })
        except PermissionError:
            raise HTTPException(403, "Permission denied for this path")

    return {"path": resolved, "entries": sorted(entries, key=lambda x: (not x["is_dir"], x["name"]))}


@app.post("/api/files/upload")
async def upload_file(path: str = Form(...), file: UploadFile = File(...), user: User = Depends(verify_token)):
    import os
    home = os.path.realpath(os.path.expanduser("~"))
    dest_dir = os.path.realpath(os.path.expanduser(path))
    if os.name == "nt":
        if not dest_dir.casefold().startswith(home.casefold() + os.sep) and dest_dir.casefold() != home.casefold():
            raise HTTPException(403, "Access denied: path outside home directory")
    else:
        if not dest_dir.startswith(home + os.sep) and dest_dir != home:
            raise HTTPException(403, "Access denied: path outside home directory")
    safe_name = os.path.basename(file.filename.replace("\\", "/"))
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, safe_name)
    data = await file.read()
    with open(dest, "wb") as f:
        f.write(data)
    return {"saved_to": dest, "size": len(data)}


def _get_gpu_stats() -> tuple[str, int]:
    """Query nvidia-smi for real GPU VRAM and utilization. Falls back to placeholder values."""
    try:
        import subprocess
        cmd = ["nvidia-smi", "--query-gpu=memory.total,memory.used,utilization.gpu", "--format=csv,noheader,nounits"]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if r.returncode == 0:
            lines = r.stdout.strip().split("\n")
            if lines:
                parts = lines[0].split(",")
                if len(parts) >= 3:
                    mem_total = int(parts[0].strip())
                    mem_used = int(parts[1].strip())
                    gpu_pct = int(parts[2].strip())
                    return f"{mem_used} / {mem_total} MB", gpu_pct
    except Exception as e:
        logger.exception("[GPU] nvidia-smi parse failed: %s", e)
    return "Unknown", 0

# ==============================================
#  ROUTES â€” DASHBOARD STATS
# ==============================================
@app.get("/api/stats")
async def dashboard_stats():
    reminders_count = 0
    try:
        from core.database import get_db
        async for session in get_db():
            from reminders.manager import count_reminders
            reminders_count = await count_reminders(session)
    except Exception as e:
        logger.exception("[Dashboard] Reminder count failed: %s", e)
    gpu_vram, gpu_pct = _get_gpu_stats()
    return {
        "gpu_vram": gpu_vram,
        "gpu_pct": gpu_pct,
        "memory_hot": 0,
        "memory_cold": 0,
        "search_queries": 0,
        "commands": 0,
        "reminders": reminders_count,
        "notes": 0,
        "active_models": {
            "chat": os.getenv("CHAT_MODEL", "qwen3:4b"),
            "code": os.getenv("CODE_MODEL", "qwen2.5-coder:3b"),
            "vision": os.getenv("VISION_MODEL", "moondream")
        }
    }

try:
    from core.routes.voice import router as voice_router
    app.include_router(voice_router)
    logger.info("[Router] Voice routes loaded [OK]")
except Exception as e:
    logger.warning("[Router] Voice routes not loaded: %s", e)


# ==============================================
#  ROUTES â€” BROWSER AGENT
# ==============================================
@app.websocket("/ws/{device_id}/{user_id}")
async def websocket_endpoint(ws: WebSocket, device_id: str, user_id: int):
    from network.websocket_server import connection_manager, handle_message

    await connection_manager.connect(ws, device_id, user_id)
    try:
        await ws.send_json({
            "type": "connected",
            "payload": {
                "device_id": device_id,
                "user_id": user_id,
                "server_time": datetime.utcnow().isoformat()
            }
        })
        while True:
            raw = await ws.receive_text()
            await handle_message(ws, device_id, user_id, raw)
    except WebSocketDisconnect:
        connection_manager.disconnect(device_id, user_id)


# ==============================================
#  ACTION EXECUTOR â€” maps intents to execution handlers
# ==============================================
async def execute_action(intent_data: dict, message: str = "") -> dict:
    """Execute an action based on intent classification.
    Returns dict with keys: executed, error, action, result.
    """
    intent = intent_data.get("intent", "chat")
    target = intent_data.get("target", message)
    params = intent_data.get("parameters", {})
    try:
        if intent == "open_url":
            url = params.get("url", target)
            if not url.startswith("http"):
                url = "https://" + url
            import webbrowser
            webbrowser.open(url)
            return {"executed": True, "action": f"Opened {url}", "result": {}}
        elif intent == "play_media":
            from media.player import media_player
            await media_player.play(target)
            return {"executed": True, "action": f"Playing {target}", "result": {}}
        elif intent == "web_search":
            from tools.search_tool import search
            results = await search(target)
            return {"executed": True, "action": f"Searched for {target}", "result": results}
        elif intent == "reminder":
            from core.scheduler import JarvisScheduler
            scheduler = JarvisScheduler()
            scheduler.add_task("reminder", params)
            return {"executed": True, "action": f"Reminder set", "result": {}}
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
        elif intent in ("message", "browser_task", "code_task"):
            return {"executed": False, "action": "", "result": {}, "error": None}
        else:
            return {"executed": False, "action": "", "result": {}, "error": None}
    except Exception as e:
        logger.warning("[execute_action] %s failed: %s", intent, e)
        return {"executed": False, "action": "", "result": {}, "error": str(e)}


# ==============================================
#  WEBSOCKET â€” CHAT STREAM (for real-time streaming AI responses)
# ==============================================
@app.websocket("/ws/chat_stream")
async def chat_stream_websocket(ws: WebSocket):
    """
    Unified WebSocket handler: uses same LLM intent pipeline as REST API.
    """
    from core.model_router import route_request, get_router_model
    from core.llm_router import get_router
    from core.intent_router import extract_intent
    from core.plugins import plugin_registry

    await ws.accept()
    session_id = str(id(ws))
    await plugin_registry.run_hook("session_start", session_id=session_id, metadata={"source": "websocket"})
    try:
                while True:
                    raw = await ws.receive_text()
                    import json
                    msg = json.loads(raw)
                    msg_type = msg.get('type')

                    if msg_type == 'chat':
                        text = msg.get('text', '')
                        msg_data = {"id": session_id, "text": text, "type": "chat"}
                        for _, result in await plugin_registry.run_hook("message_received", message=msg_data):
                            if isinstance(result, dict) and result.get("text"):
                                text = result["text"]

                        for _, result in await plugin_registry.run_hook("before_dispatch", message=msg_data):
                            if result is None:
                                continue
                        # Duplicate detection â€“ avoid processing the same user message twice
                        if not hasattr(ws, 'last_user_message'):
                            ws.last_user_message = None
                        if text.strip() and text.strip() == ws.last_user_message:
                            # Send a short acknowledgement and skip processing
                            await ws.send_json({
                                'type': 'stream_token',
                                'token': 'Already processed.',
                                'complete': True,
                                'privacy_tier': 'LOCAL',
                                'model': 'unknown',
                                'intent': 'chat',
                            })
                            continue
                        ws.last_user_message = text.strip()
                        
                        # Phase 3: mem0 + RAGFlow Integration
                        user_id = session_id # Fallback to session_id as user_id
                        
                        # 1. Retrieve relevant memories
                        from memory.mem0_adapter import mem0_memory
                        memories = mem0_memory.search(text, user_id=user_id, limit=5)
                        memory_context = mem0_memory.format_context(memories)

                        # 2. Retrieve RAGFlow document context
                        from tools.ragflow_tool import ragflow_search, format_rag_context
                        rag_result = await ragflow_search(text, top_k=5)
                        rag_context = format_rag_context(rag_result.get("chunks", []))

                        # Build enhanced system prompt
                        system_prompt = "You are JARVIS, your AI assistant. Be concise."
                        if memory_context:
                            system_prompt = memory_context + "\n\n" + system_prompt
                        if rag_context:
                            system_prompt = rag_context + "\n\n" + system_prompt

                        model, tier, processed_query = route_request(text)

                        # Use same LLM-based intent + action pipeline as REST API
                        intent_data = await extract_intent(processed_query)
                        action_result = await execute_action(intent_data, message=text)
                        current_intent = intent_data.get("intent", "chat")

                        non_chat_intents = ("build", "pc_control", "open_url", "play_media",
                                            "reminder", "weather", "news", "stocks", "sports", "time", "web_search", "search")
                        ws_provenance = {"source": "inference", "confidence": 0.5, "url": None}
                        ws_source_intents = {"web_search": "web_search", "search": "web_search", "news": "tool_result", "weather": "tool_result", "stocks": "tool_result", "time": "tool_result", "sports": "tool_result"}
                        ws_detected = ws_source_intents.get(current_intent)
                        if ws_detected:
                            ws_provenance["source"] = ws_detected
                            ws_provenance["confidence"] = 0.9
                        if current_intent in non_chat_intents and action_result.get("executed") and not action_result.get("error"):
                            response_text = action_result.get("action", f"{current_intent} completed")
                        else:
                            try:
                                _vision_kw = ["screen", "screenshot", "see", "look", "what is on", "what's on", "what do you see", "what am i looking"]
                                _is_vision = any(kw in text.lower() for kw in _vision_kw)
                                if _is_vision or current_intent == "vision":
                                    from core.llm_router import complete_vision
                                    try:
                                        from core.vision_agent import VisionAgent
                                        agent = VisionAgent()
                                        state = await agent._capture()
                                        screen_desc = await agent._describe(state)
                                        text += f"\n[SCREEN CAPTURE: {screen_desc}]"
                                    except Exception as e:
                                        logger.exception("[WS] Vision capture failed: %s", e)
                                    vision_result = await complete_vision([
                                        {"role": "system", "content": system_prompt},
                                        {"role": "user", "content": processed_query}], timeout=60)
                                    resp_text = vision_result.unwrap_or("")
                                    response_text = epistemic_tagger.tag_response(resp_text, ws_provenance)
                                else:
                                    model_group = "cloud" if model == "cloud" else get_router_model(current_intent)
                                    try:
                                        resp = await get_router().acompletion(
                                            model=model_group,
                                            messages=[{"role": "system", "content": system_prompt},
                                                      {"role": "user", "content": processed_query}],
                                            timeout=60,
                                        )
                                        response_text = epistemic_tagger.tag_response(resp.choices[0].message.content, ws_provenance)
                                    except Exception as e:
                                        logger.exception("[WS] LiteLLM fallback to Ollama: %s", e)
                                        from core.model_router import model_for_role, get_ollama_url
                                        model_obj = model_for_role(current_intent)
                                        direct_url = get_ollama_url(model_obj)
                                        import httpx
                                        async with httpx.AsyncClient(timeout=60) as client:
                                            r = await client.post(f"{direct_url}/api/chat", json={
                                                "model": model_obj,
                                                "messages": [{"role": "system", "content": system_prompt},
                                                             {"role": "user", "content": processed_query}],
                                                "stream": False,
                                                "options": {"num_predict": 1024, "temperature": 0.7, "num_gpu": 99}})
                                            resp_text = r.json().get("message", {}).get("content", "")
                                        response_text = epistemic_tagger.tag_response(resp_text, ws_provenance)
                            except Exception as e:
                                logger.exception("[WS] All LLM fallbacks failed: %s", e)
                                response_text = "I had a temporary issue processing that request."

                        # Store the exchange in persistent memory
                        mem0_memory.add(
                            [{"role": "user", "content": text}, {"role": "assistant", "content": response_text}],
                            user_id=user_id,
                        )

                        for _, result in await plugin_registry.run_hook("before_agent_reply", reply=response_text):
                            if isinstance(result, str) and result:
                                response_text = result

                        reply_payload = {
                            'type': 'stream_tokens',
                            'tokens': response_text.split(),
                            'privacy_tier': tier.value,
                            'model': model,
                            'intent': current_intent,
                        }
                        for _, result in await plugin_registry.run_hook("reply_payload_sending", payload=reply_payload):
                            if isinstance(result, dict):
                                reply_payload = result

                        words = reply_payload.get("tokens", response_text.split())
                        for i, word in enumerate(words):
                            await ws.send_json({
                                'type': 'stream_token',
                                'token': word + ' ',
                                'complete': i == len(words) - 1,
                                'privacy_tier': reply_payload.get("privacy_tier", tier.value),
                                'model': reply_payload.get("model", model),
                                'intent': reply_payload.get("intent", current_intent),
                            })

                        await ws.send_json({
                            'type': 'tier_status',
                            'tier': f'Tier {reply_payload.get("privacy_tier", tier.value)}',
                            'status': 'completed'
                        })

                        await plugin_registry.run_hook("message_sent", message={"id": session_id, "text": response_text, "type": "response"})
                    elif msg_type == 'ping':
                        await ws.send_json({'type': 'pong'})
    except WebSocketDisconnect:
        await plugin_registry.run_hook("session_end", session_id=session_id, summary={"disconnect": "websocket_disconnect"})
        pass
    except Exception as e:
        logger.error('[WS Chat] Error: %s', e)
        await plugin_registry.run_hook("session_end", session_id=session_id, summary={"error": str(e)})
        try:
            await ws.close()
        except Exception:
            pass  # cleanup, ignore close failures
    else:
        await plugin_registry.run_hook("session_end", session_id=session_id, summary={"status": "closed"})


# ==============================================
#  ROUTES â€” WEB INTELLIGENCE
# ==============================================
@app.post("/search")
async def search_route(req: dict, user: User = Depends(verify_token)):
    from tools.search_tool import decision_gate
    from tools.search_fallback import search, format_results
    query = req.get("query", "")
    if not query:
        raise HTTPException(400, "Query is required")
    
    # Check decision gate
    should_search = decision_gate.should_search(query, req.get("confidence", 1.0))
    if not should_search and not req.get("force", False):
        return {"searched": False, "reason": "Decision gate rejected search"}
    
    results = search(query, max_results=req.get("max_results", 5))
    scraped = "\n".join(r.get("content", "") for r in results)
    
    return {
        "searched": True,
        "results": results,
        "context": scraped,
        "formatted": format_results(results),
    }

class BrowseRequest(BaseModel):
    instruction: str = ""
    task: str = ""

@app.post("/browse")
async def browser_agent(req: BrowseRequest, user: User = Depends(verify_token)):
    instruction = req.instruction or req.task
    if not instruction:
        raise HTTPException(400, "instruction is required")
    
    from core.ssrf import assert_safe_url
    from core.audit_log import audit_log
    if instruction.startswith("http"):
        try:
            assert_safe_url(instruction)
        except ValueError as e:
            audit_log.log("ssrf_blocked", user_id=user.uid, path="/browse", method="POST", request_body={"instruction": instruction})
            raise HTTPException(400, str(e))
    
    from tools.browser_tool import JarvisBrowser
    browser = JarvisBrowser()
    
    result = await browser.execute(instruction)
    audit_log.log("browse", user_id=user.uid, path="/browse", method="POST", status=200, request_body={"instruction": instruction})
    return result


# ==============================================
#  ROUTES â€” COMPUTER CONTROL
# ==============================================
class ComputerControlRequest(BaseModel):
    instruction: str = ""
    confirm: bool = True

@app.post("/computer")
async def computer_control(req: ComputerControlRequest, user: User = Depends(verify_token)):
    from pc_agent.computer_agent import computer_agent
    if not req.instruction:
        raise HTTPException(400, "Instruction is required")
    result = await computer_agent.execute_natural_language(req.instruction, confirm=req.confirm)
    return result

# ==============================================
#  ROUTES â€” EXECUTIONS
# ==============================================
# ==============================================
#  ROUTES â€” MEMORY SEARCH
# ==============================================
@app.get("/api/memory/search")
async def memory_search(
    q: str = Query("", description="Search query"),
    limit: int = Query(5, ge=1, le=50),
    user: User = Depends(verify_token),
):
    """Search JARVIS's tiered memory (hot/warm/cold)."""
    if not q:
        return {"results": []}
    from memory.tiered_memory import tiered_memory
    results = tiered_memory.recall(q, limit=limit)
    return {"query": q, "results": results[:limit]}

# ==============================================
#  ROUTES â€” CODE REVIEW
# ==============================================
@app.post("/api/code/review")
async def code_review(
    req: CodeReviewRequest,
    user: User = Depends(verify_token),
):
    """Review code for bugs, security issues, and style problems."""
    from core.llm_router import complete as llm_complete, health_check
    if not await health_check():
        return JSONResponse(status_code=503, content={"error": "Ollama is offline", "language": req.language})
    prompt = (
        f"Review this {req.language} code for:\n"
        f"1. Bugs and logic errors\n"
        f"2. Security vulnerabilities\n"
        f"3. Performance issues\n"
        f"4. Code style improvements\n\n"
        f"Context: {req.context or 'N/A'}\n\n"
        f"```{req.language}\n{req.code}\n```\n\n"
        f"Format: For each issue found, state: SEVERITY (critical/major/minor), what, where, fix."
    )
    try:
        review = (await llm_complete("code", [{"role": "user", "content": prompt}])).unwrap_or("")
        return {"review": review, "language": req.language}
    except Exception as e:
        return {"error": str(e), "language": req.language}


# ==============================================
#  ROUTES â€” QUALITY
# ==============================================
@app.post("/api/quality/grade")
async def quality_grade(
    req: QualityGradeRequest,
    user: User = Depends(verify_token),
):
    from core.llm_router import complete as llm_complete, health_check
    import core.llm_router
    from core.quality_grader import QualityGrader

    if not await health_check():
        return JSONResponse(status_code=503, content={"error": "Ollama is offline"})

    try:
        grader = QualityGrader(
            constitution_path="config/quality_constitution.json",
            llm_router=core.llm_router,
        )
        grade = await grader.grade(req.type, req.content)
        return {
            "aggregate_score": grade.aggregate_score,
            "passed": grade.passed,
            "criteria": [
                {
                    "id": c.id,
                    "description": c.description,
                    "passed": c.passed,
                    "score": c.score,
                    "evidence": c.evidence,
                }
                for c in grade.criteria
            ],
        }
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


try:
    from core.routes.vision import router as vision_router
    app.include_router(vision_router)
    logger.info("[Router] Vision routes loaded [OK]")
except Exception as e:
    logger.warning("[Router] Vision routes not loaded: %s", e)


# ==============================================
#  ROUTES â€” PHASE 9: HORIZON PLANNER + TEST ALERT
# ==============================================
try:
    from core.routes.admin import router as admin_router
    app.include_router(admin_router)
    logger.info("[Router] Admin routes (horizon, prompts, quality, docs) loaded [OK]")
except Exception as e:
    logger.warning("[Router] Admin routes not loaded: %s", e)


# ==============================================
#  RUN
# ==============================================
# ==============================================
#  GLOBAL ERROR HANDLERS
# ==============================================

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
            "message": str(exc),
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
    uvicorn.run("core.main:app", host=HOST, port=PORT, reload=True, log_level="info")
