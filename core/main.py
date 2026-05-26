"""
core/main.py — JARVIS FastAPI server: all routes + WebSocket + startup
"""
import os
import sys
import io
import logging
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

logger = logging.getLogger("jarvis")
logger.setLevel(logging.DEBUG)
if not logger.handlers:
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.DEBUG)
    logger.addHandler(ch)

import asyncio
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional, List, Literal

from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect, UploadFile, File, Form, Query
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
import numpy as np
import cv2
import instructor
from openai import OpenAI
from smolagents import ToolCallingAgent, tool, LiteLLMModel

from brain.epistemic_tagger import epistemic_tagger
from .composio_tools import COMPOSIO_TOOLS
from .config import HOST, PORT, ALLOWED_ORIGINS
from .database import get_db, init_db, User
from .auth import verify_token, init_firebase
from .config import SUPABASE_URL, SUPABASE_SERVICE_KEY

startup_status = {
    "autonomy": False,
    "hybrid": False,
    "warnings": [],
}


def _warmup_ollama_models():
    """Verify Ollama is reachable and models are available (no pre-loading to save GPU memory)."""
    try:
        from core.model_router import ROLE_MODELS, resolve_model
    except ImportError:
        return

    ollama_url = "http://localhost:11434"

    try:
        import json
        from urllib.request import urlopen
        from urllib.error import URLError
        with urlopen(f"{ollama_url}/api/tags", timeout=2) as resp:
            data = json.loads(resp.read().decode())
            # Normalize model names (handle :latest tag)
            available_models = set()
            for m in data.get("models", []):
                name = m.get("name", "")
                available_models.add(name)
                # Also add version without :latest
                if name.endswith(":latest"):
                    available_models.add(name[:-7])  # Remove ":latest"
    except Exception:
        print("  [OLLAMA] Not reachable, skipping model check")
        return

    # Just verify configured models exist, don't pre-load them (saves GPU memory)
    required_models = sorted({resolve_model(m) for m in ROLE_MODELS.values()})
    missing = [m for m in required_models if m not in available_models]

    if missing:
        print(f"  [OLLAMA] {len(missing)} model(s) not installed: {', '.join(missing[:3])}...")
        startup_status["warnings"].append(f"ollama: {len(missing)} model(s) missing")
    else:
        print(f"  [OLLAMA] All {len(required_models)} models verified installed [OK]")


# ==============================================
#  STARTUP / SHUTDOWN
# ==============================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("=" * 50)
    print("  JARVIS — Starting up...")
    print("=" * 50)

    # Init DB
    await init_db()

    # Init Firebase
    init_firebase()

    # Load pending reminders
    from reminders.manager import reminder_manager
    await reminder_manager.load_and_schedule_all()

    # Inject TTS into reminder manager
    from assistant.engine import jarvis
    reminder_manager.inject_tts(jarvis.tts)

    # Initialize 4-layer autonomous intelligence system (L1-L4)
    try:
        import autonomy
        await autonomy.initialize_autonomous_stack()
        startup_status["autonomy"] = True
        print("  [AUTONOMY] Autonomous stack initialized [OK]")
    except Exception as e:
        startup_status["warnings"].append(f"autonomy: {e}")
        print(f"  [WARNING] Autonomous system init failed: {e}")

    try:
        if startup_status["autonomy"]:
            print("  [HYBRID] Initializing research-grade automation system...")
            from orchestrator.hybrid_orchestrator import hybrid_orchestrator
            from models.hybrid_models import hybrid_manager
            from tools.executor import open_claw_executor

            await hybrid_manager._init_clients()
            startup_status["hybrid"] = True
            print("  [HYBRID] Model fallback system ready [OK]")

            _warmup = asyncio.ensure_future(hybrid_manager._warmup_models())
            _warmup.add_done_callback(lambda t: print(f"  [HYBRID] Warmup {'OK' if not t.exception() else 'FAILED: '+str(t.exception())}"))
            print("  [HYBRID] Hybrid Automation System ready [OK]")
        else:
            print("  [HYBRID] Skipping hybrid automation init because autonomy layer failed.")
    except Exception as e:
        startup_status["warnings"].append(f"hybrid: {e}")
        print(f"  [WARNING] Hybrid automation init failed: {e}")

    # Check + auto-install coding agents
    try:
        from core.agent_registry import (
            check_available_agents, check_missing_agents, check_unconfigured_agents,
            auto_install_missing, get_config_report, write_env_file,
        )
        available = check_available_agents()
        missing = check_missing_agents()
        unconfigured = check_unconfigured_agents()

        print(f"  [AGENTS] Available: {', '.join(sorted(available)) or 'none'}")

        # Auto-install missing agents
        if missing:
            print(f"  [AGENTS] Auto-installing missing: {', '.join(missing)}...")
            installed = await auto_install_missing()
            if installed:
                print(f"  [AGENTS] Installed: {', '.join(installed)}")
            still_missing = [m for m in missing if m not in installed]
            if still_missing:
                print(f"  [AGENTS] Could not install: {', '.join(still_missing)} — install manually")

        if unconfigured:
            report = get_config_report()
            for name in unconfigured:
                print(f"  [AGENTS] ⚠️  {report[name]['label']}: {report[name]['config_help']}")
            env_tips = write_env_file(
                sum([report[n]['missing_keys'] for n in unconfigured], [])
            )
            if env_tips:
                print(f"  [AGENTS] Add to .env:\n{env_tips}")
    except Exception as e:
        print(f"  [AGENTS] Setup failed: {e}")

    # Verify Ollama models (wait for Ollama to be ready first)
    try:
        # Wait for Ollama to be ready (up to 30 seconds)
        for _ in range(30):
            try:
                from urllib.request import urlopen
                with urlopen("http://localhost:11434/api/tags", timeout=1) as resp:
                    if resp.status == 200:
                        break
            except Exception:
                await asyncio.sleep(1)
        # Now check models
        _warmup_ollama_models()
    except Exception as e:
        startup_status["warnings"].append(f"ollama_check: {e}")

    # Start WakeWordDetector + VoiceLoop
    try:
        from assistant.voice_pipeline import get_pipeline, VoiceLoop
        _voice_loop = VoiceLoop()
        app.state.voice_loop = _voice_loop
        _voice_loop.start()
        print("  [VOICE] Wake word + voice loop started [OK]")
    except Exception as e:
        print(f"  [WARNING] Wake word/voice loop: {e}")

    # Start Supabase Gateway (remote mobile connectivity)
    try:
        if SUPABASE_URL and SUPABASE_SERVICE_KEY:
            from .supabase_gateway import SupabaseGateway
            from .model_router import route_request
            from .llm_router import router as llm_router

            # ── Goal handler for agent orchestration ──
            async def _supabase_goal(content: str, user_id: str):
                from .plan_routes import plan_manager
                plan = await plan_manager.create_plan(content)
                plan_data = {
                    "plan_id": plan["id"],
                    "goal": plan["goal"],
                    "steps": plan.get("steps", []),
                    "status": plan["status"],
                }
                text_lines = [f"📋 Plan for: {plan['goal']}"]
                for s in plan.get("steps", []):
                    text_lines.append(f"  Step {s['id']}: [{s['agent']}] {s.get('prompt', '')[:80]}")
                text_lines.append("\nReply with: approve <plan_id> / modify <plan_id> / reject <plan_id>")
                return {"text": "\n".join(text_lines), "plan": plan_data}

            # ── Plan status handler ──
            async def _supabase_plan_status(content: str, user_id: str):
                from .plan_routes import plan_manager
                msg = content.lower().strip()
                parts = msg.split()
                if len(parts) >= 2 and parts[0] in ("approve", "reject", "modify"):
                    plan_id = parts[1]
                    if parts[0] == "approve":
                        plan = plan_manager.approve_plan(plan_id)
                        if plan:
                            import asyncio
                            asyncio.create_task(plan_manager.execute_plan(plan_id))
                            return {"text": f"✅ Plan {plan_id} approved — execution started!", "progress": {"plan_id": plan_id, "status": "executing"}}
                    elif parts[0] == "reject":
                        plan = plan_manager.reject_plan(plan_id)
                        if plan:
                            return {"text": f"❌ Plan {plan_id} rejected"}
                    return {"text": f"Plan {plan_id} not found"}
                if "status" in msg or "how" in msg:
                    plans = plan_manager.list_plans()
                    if not plans:
                        return {"text": "No active plans"}
                    lines = ["Active plans:"]
                    for p in plans:
                        status = plan_manager.get_status(p["id"])
                        lines.append(f"  {p['id']}: {status['status']} — {p['goal'][:50]}")
                    return {"text": "\n".join(lines)}
                return {"text": "Usage: approve <plan_id> | reject <plan_id> | status"}

            # ── Normal chat / file request handler ──
            async def _supabase_process(content: str, user_id: str):
                model_name, privacy_tier, sanitized = route_request(content)
                model_group = "cloud" if model_name == "cloud" else "chat"

                try:
                    # Check if this is a file request
                    from tools.file_search import find_files, find_by_type
                    msg_lower = content.lower()
                    file_keywords = ["send me", "find me", "get my", "share", "send my", "send the", "find the",
                                     "i need my", "i need the", "upload", "file", "document", "photo", "image",
                                     "screenshot", "pdf", "resume"]
                    is_file_request = any(kw in msg_lower for kw in file_keywords)

                    if is_file_request:
                        files = []
                        file_type_phrases = {"image": ["image", "photo", "picture", "screenshot", "img"],
                                             "document": ["document", "pdf", "doc", "resume", "cv", "letter"]}
                        for ftype, phrases in file_type_phrases.items():
                            if any(p in msg_lower for p in phrases):
                                files = find_by_type(ftype, max_results=3)
                                break
                        if not files:
                            query = content.replace("send", "").replace("find", "").replace("get", "").replace("share", "").replace("my", "").replace("the", "").replace("i need", "").replace("please", "").replace("me", "").strip().strip(".,!?")
                            if query:
                                files = find_files(query, max_results=3)

                        if files:
                            uploaded = []
                            for f in files:
                                file_info = await gateway.upload_file(f["path"], user_id)
                                if file_info:
                                    uploaded.append(file_info)

                            if uploaded:
                                names = ", ".join(f["name"] for f in uploaded)
                                file_info = uploaded[0]
                                return {
                                    "text": f"Found and sent {len(uploaded)} file(s): {names}",
                                    "file": uploaded[0] if len(uploaded) == 1 else uploaded,
                                }

                    # Normal LLM response
                    resp = await llm_router.acompletion(
                        model=model_group,
                        messages=[{"role": "user", "content": sanitized}],
                        timeout=60,
                    )
                    return resp.choices[0].message.content
                except Exception as e:
                    return f"Error processing request: {e}"

            gateway = SupabaseGateway(SUPABASE_URL, SUPABASE_SERVICE_KEY)
            app.state.supabase_gateway = gateway
            app.state.supabase_gateway_ref = gateway
            await gateway.start(_supabase_process, _supabase_goal, _supabase_plan_status)
            print("  [SUPABASE] Remote mobile gateway started [OK]")
        else:
            print("  [SUPABASE] Skipped — SUPABASE_URL not configured")
    except Exception as e:
        print(f"  [WARNING] Supabase gateway init failed: {e}")

    # Start Cowork Scheduler
    try:
        from .scheduler import scheduler as cowork_scheduler
        from .morning_digest import generate_morning_digest

        async def _morning_digest_handler(params: dict):
            digest = await generate_morning_digest(params.get("user_id", "default"))
            print(f"[COWORK] Morning digest generated ({len(digest)} chars)")
            return digest

        cowork_scheduler.register_handler("morning_digest", _morning_digest_handler)
        cowork_scheduler.add_task(
            "morning_digest",
            "daily@09:00",
            {"type": "morning_digest", "params": {"user_id": "default"}},
        )
        await cowork_scheduler.start()
        app.state.cowork_scheduler = cowork_scheduler
        print("  [COWORK] Scheduler started — morning digest daily@09:00 [OK]")
    except Exception as e:
        print(f"  [WARNING] Cowork scheduler init failed: {e}")

    # Start AutoDream DreamingLoop (nightly review at 2am)
    try:
        from .dreaming import DreamingLoop
        app.state.dreaming = DreamingLoop(
            supabase_url=SUPABASE_URL or "",
            supabase_key=SUPABASE_SERVICE_KEY or "",
        )

        async def dreaming_scheduler():
            last_run = ""
            while True:
                now = datetime.now()
                if now.hour == 2 and last_run != now.strftime("%Y-%m-%d"):
                    await app.state.dreaming.run_nightly_review()
                    last_run = now.strftime("%Y-%m-%d")
                await asyncio.sleep(3600)

        app.state.dreaming_task = asyncio.create_task(dreaming_scheduler())
        print("  [DREAMING] AutoDream nightly review scheduler started [OK]")
    except Exception as e:
        print(f"  [WARNING] AutoDream init failed: {e}")

    # Start Self-Healing + Learning Loop
    try:
        from .self_healing import self_healing, learning_loop
        app.state.self_healing = self_healing
        app.state.learning_loop = learning_loop
        print("  [SELF-HEAL] Self-healing framework online [OK]")
        print("  [LEARN] Continuous learning loop active [OK]")
    except Exception as e:
        print(f"  [WARNING] Self-healing/learning init failed: {e}")

    if startup_status["warnings"]:
        print("[JARVIS] Startup completed with warnings:")
        for warning in startup_status["warnings"]:
            print(f"  - {warning}")
    else:
        print("[JARVIS] All systems online [OK]")
    yield

    # Shutdown
    from automation.messaging import messaging
    messaging.shutdown()
    if hasattr(app.state, "voice_loop"):
        app.state.voice_loop.stop()
        print("  [VOICE] Voice loop stopped")
    if hasattr(app.state, "supabase_gateway"):
        await app.state.supabase_gateway.stop()
        print("  [SUPABASE] Gateway stopped")
    if hasattr(app.state, "dreaming_task"):
        app.state.dreaming_task.cancel()
        print("  [DREAMING] DreamingLoop scheduler stopped")
    if hasattr(app.state, "cowork_scheduler"):
        await app.state.cowork_scheduler.stop()
        print("  [COWORK] Scheduler stopped")
    print("[JARVIS] Shutdown complete.")


# ==============================================
#  APP
# ==============================================
app = FastAPI(
    title="JARVIS API",
    description="Personal AI Life Operating System",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Optional routers (kept separate so missing optional deps don't break startup)
try:
    from api.agi_routes import router as agi_router
    app.include_router(agi_router)
except Exception as e:
    print(f"[Router] AGI routes not loaded: {e}")

try:
    from api.vision_routes import router as vision_router
    app.include_router(vision_router)
except Exception as e:
    print(f"[Router] Vision routes not loaded: {e}")

try:
    from api.server import router as brain_router
    app.include_router(brain_router)
except Exception as e:
    print(f"[Router] Brain routes not loaded: {e}")

try:
    from api.os_routes import router as os_router
    app.include_router(os_router)
    print("[Router] AI OS routes loaded")
except Exception as e:
    print(f"[Router] AI OS routes not loaded: {e}")

try:
    from api.ai_os_routes import router as ai_os_router
    app.include_router(ai_os_router)
    print("[Router] AI OS CUSTOM routes loaded")
except Exception as e:
    print(f"[Router] AI OS CUSTOM routes not loaded: {e}")

try:
    from automation.routes import router as automation_router
    app.include_router(automation_router)
except Exception as e:
    print(f"[Router] Automation routes not loaded: {e}")

try:
    from automation.call_sync_server import get_fastapi_router
    app.include_router(get_fastapi_router())
except Exception as e:
    print(f"[Router] Call sync routes not loaded: {e}")

try:
    from api.hybrid_integration import setup_hybrid_routes
    setup_hybrid_routes(app)
    print("[Router] Hybrid Automation routes loaded [OK]")
except Exception as e:
    print(f"[Router] Hybrid Automation routes not loaded: {e}")

# Autonomous Intelligence Layers (L1-L4) — integrated into main system
try:
    import autonomy
    router = autonomy.get_router()
    if router:
        # Mount autonomous API under /autonomy for namespacing
        app.include_router(router, prefix="/autonomy", tags=["Autonomous"])
        # Also mount at root for backward compat (CLI + legacy calls)
        app.include_router(router)
        print("[Router] Autonomous layers routes loaded")
except Exception as e:
    print(f"[Router] Autonomous routes not loaded: {e}")

# Student AGI System — optional separate service
# Runs as: python learning/student_agi/student_agi_main.py
# Can be called via /student-agi/... endpoints when available
try:
    from learning.student_agi.api.student_routes import router as student_router
    app.include_router(student_router, prefix="/student-agi", tags=["Student AGI"])
    print("[Router] Student AGI routes loaded")
except Exception as e:
    print(f"[Router] Student AGI routes not loaded (service may not be started): {e}")

# Agent Orchestrator — goal/plan/execution routes
try:
    from core.plan_routes import router as plan_router
    app.include_router(plan_router)
    print("[Router] Agent Orchestrator routes loaded [OK]")
except Exception as e:
    print(f"[Router] Agent Orchestrator routes not loaded: {e}")

# Cowork Mode routes — files, skills, builds
try:
    from fastapi import APIRouter
    cowork = APIRouter(prefix="/cowork", tags=["Cowork"])

    # ── File Agent routes ──────────────────────────────────────
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

    # ── Skills routes ──────────────────────────────────────────
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
        output = await llm_complete("creative", [{"role": "user", "content": filled}])
        return {"skill": skill_name, "input": filled, "output": output.strip()}

    # ── Overnight Builder route ────────────────────────────────
    class BuildRequest(BaseModel):
        goal: str
        output_dir: str = "."

    @cowork.post("/build/overnight")
    async def cowork_overnight_build(req: BuildRequest):
        from .agent_executor import run_overnight_build
        task = asyncio.create_task(run_overnight_build(req.goal, req.output_dir))
        return {"status": "started", "goal": req.goal, "output_dir": req.output_dir, "message": "Overnight build running in background"}

    # ── Morning Digest route ───────────────────────────────────
    @cowork.get("/digest")
    async def cowork_digest(user_id: str = "default"):
        from .morning_digest import generate_morning_digest
        digest = await generate_morning_digest(user_id)
        return {"digest": digest}

    # ── Scheduler management routes ────────────────────────────
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
    print("[Router] Cowork Mode routes loaded [OK]")
except Exception as e:
    import traceback
    print(f"[Router] Cowork Mode routes not loaded: {e}")
    traceback.print_exc()


# ==============================================
#  PYDANTIC SCHEMAS
# ==============================================
class ChatRequest(BaseModel):
    message: str
    context: Optional[str] = ""
    tier: Optional[str] = None  # "local", "cloud", or None for default
    session_id: Optional[str] = None

class ReminderCreate(BaseModel):
    title: str
    remind_at: datetime
    description: Optional[str] = ""
    repeat: Optional[str] = "none"

class NoteCreate(BaseModel):
    title: str
    content: str
    tags: Optional[str] = ""

class NoteUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None

class MessageRequest(BaseModel):
    platform: str        # whatsapp | instagram
    recipient: str       # contact name or @username
    message: str

class FaceRegisterRequest(BaseModel):
    person_name: str
    relation: Optional[str] = "unknown"
    info: Optional[str] = ""
    access_level: Optional[str] = "visitor"


# ==============================================
#  ROUTES — HEALTH
# ==============================================
@app.get("/")
async def root():
    return FileResponse("static/index.html")

# ==============================================
#  ROUTES — SHOWCASE (3rd Particle UI)
# ==============================================
import calendar as _cal

@app.get("/showcase")
async def showcase():
    return FileResponse("jarvis_showcase.html")

@app.get("/api/monthly-highlights")
async def monthly_highlights():
    now = datetime.now()
    month_name = now.strftime("%B %Y")
    from core.database import get_db
    conversations = 0
    reminders = 0
    try:
        async for session in get_db():
            from reminders.manager import count_reminders
            reminders = await count_reminders(session)
    except Exception:
        pass
    return {
        "month": month_name,
        "conversations": conversations,
        "commands_executed": 0,
        "searches": 3,
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
            "100% local privacy — zero cloud dependency"
        ]
    }

app.mount("/assets", StaticFiles(directory="static/assets"), name="assets")
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/health")
async def health():
    from assistant.stt import get_stt
    from assistant.tts import get_tts
    from core.database import get_db
    
    stt_loaded = False
    try:
        stt = get_stt()
        stt._ensure_model()
        stt_loaded = stt.model is not None
    except Exception as e:
        print(f'[Health] STT check: {e}')
    
    tts_loaded = False
    try:
        tts = get_tts()
        tts._ensure_model()
        tts_loaded = tts.pipeline is not None
    except Exception as e:
        print(f'[Health] TTS check: {e}')
    
    ollama_ready = False
    try:
        import requests
        resp = requests.get("http://localhost:11434/api/tags", timeout=2)
        ollama_ready = resp.status_code == 200
    except Exception as e:
        logger.debug(f"[Health] Ollama check: {e}")

    db_connected = False
    try:
        import os
        db_connected = os.path.exists("data/jarvis.db")
    except Exception as e:
        logger.debug(f"[Health] DB check: {e}")

    sh = getattr(app.state, "self_healing", None)
    sh_status = sh.get_status() if sh else {}

    return {
        "ollama": ollama_ready,
        "stt_loaded": stt_loaded,
        "tts_loaded": tts_loaded,
        "db_connected": db_connected,
        "self_healing": sh_status,
        "timestamp": datetime.utcnow().isoformat()
    }


@app.post("/feedback")
async def feedback(req: dict):
    """Receive accept/reject feedback from CLI or users."""
    message = req.get("message", "")
    response = req.get("response", "")
    accepted = req.get("accepted", True)
    reason = req.get("reason", "")
    ll = getattr(app.state, "learning_loop", None)
    if ll:
        ll.record_feedback(message, response, accepted, reason)
        ll.save()
        return {"status": "ok", "learnings": len(ll.learnings), "rules": len(ll.rules)}
    return {"status": "error", "detail": "learning loop not initialized"}


# ==============================================
#  LLM INTENT EXTRACTION + ACTION EXECUTOR
# ==============================================

class IntentResult(BaseModel):
    intent: Literal[
        "play_media", "open_url", "open_app",
        "web_search", "reminder", "pc_control", "browser_task", "message",
        "weather", "news", "stocks", "sports", "time",
        "build", "chat"
    ]
    target: str = ""
    parameters: dict = {}


_STRICT_EXAMPLES = """
Examples:
User: play cry for me on youtube
Intent: play_media

User: open youtube
Intent: open_url

User: search latest AI news
Intent: web_search

User: open notepad
Intent: pc_control

User: remind me to drink water in 1 minute
Intent: reminder

User: what is python
Intent: chat

User: launch chrome
Intent: pc_control

User: go to github
Intent: open_url

User: open github
Intent: open_url

User: open github and complete sign up
Intent: browser_task

User: go to amazon and add a monitor to cart
Intent: browser_task

User: login to gmail and send an email
Intent: browser_task

User: send an email to john@example.com with subject hello saying hi
Intent: message

User: send a slack message to general
Intent: message

User: create a github issue in my repo
Intent: message

User: browse amazon for laptops
Intent: browser_task

User: sign up for a new account on any site
Intent: browser_task

User: register for github with google
Intent: browser_task

User: open spotify
Intent: open_url

User: go to youtube and search for music
Intent: browser_task

User: fill out the contact form
Intent: browser_task

User: what's the weather in London
Intent: weather

User: temperature in New York
Intent: weather

User: latest technology news
Intent: news

User: what's happening in the world
Intent: news

User: AAPL stock price
Intent: stocks

User: how is the stock market doing
Intent: stocks

User: NBA scores
Intent: sports

User: who won the game yesterday
Intent: sports

User: what time is it in Tokyo
Intent: time

User: build a portfolio page with animations
Intent: build

User: create a todo app
Intent: build

User: make a website for my business
Intent: build

User: generate a html resume page
Intent: build

User: open chrome to google.com
Intent: pc_control

User: open chrome and go to youtube
Intent: pc_control

User: play havana on youtube
Intent: play_media

User: play despacito
Intent: play_media
"""


_INTENT_CLIENT = None


def _get_intent_client():
    global _INTENT_CLIENT
    if _INTENT_CLIENT is None:
        _INTENT_CLIENT = instructor.from_openai(
            OpenAI(base_url="http://localhost:11434/v1", api_key="ollama"),
            mode=instructor.Mode.JSON,
        )
    return _INTENT_CLIENT


async def extract_intent(message: str) -> dict:
    try:
        client = _get_intent_client()
        result = client.chat.completions.create(
            model="qwen2.5:7b",
            response_model=IntentResult,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an intent classifier. Output ONLY the intent, target, and parameters.\n\n"
                        "Intents:\n"
                        "- play_media: user wants to play music/video/media\n"
                        "- open_url: ONLY when the user simply wants to navigate to a URL with no further action. Single verb like 'open youtube', 'go to github'.\n"
                        "- web_search: user explicitly says 'search for', 'look up', or wants current/live information from the web\n"
                        "- reminder: user wants to set a reminder/alarm\n"
                        "- pc_control: user wants to open a desktop app (notepad, vscode, chrome, etc.)\n"
                        "- browser_task: ANY multi-step browser operation — signup, login, form filling, shopping, booking, clicking, scrolling, filling fields, submitting forms, OR when the user says 'open X and Y' where Y is an action beyond just opening. This includes any mention of: sign up, sign in, register, create account, login, fill, submit, search for (on a site), add to cart, purchase, book, order.\n"
                        "- message: user wants to send an email, Slack message, or any electronic message. Examples: 'send an email', 'send a message', 'send email to', 'send slack message', 'create a github issue', 'create an issue'.\n"
                        "- weather: user asks about weather, temperature, forecast. Keywords: weather, temperature, rain, sunny, forecast.\n"
                        "- news: user asks for latest news, headlines, current events. Keywords: news, headline, what's happening.\n"
                        "- stocks: user asks about stock prices, market. Keywords: stock price, market, ticker, share price.\n"
                        "- sports: user asks about sports scores, games, matches. Keywords: score, game, match, who won, sports.\n"
                        "- time: user asks for current time in a location or timezone.\n"
                        "- build: user wants to create, build, generate, or make something (website, app, page, document, project). Keywords: build, create, make, generate, construct, develop.\n"
                        "- code_task: user wants code-related work like refactoring, debugging, adding features, writing tests, code review. Keywords: refactor, rewrite, fix bug, add test, code review, implement feature, optimize code, restructure.\n"
                        "- chat: general knowledge questions ('what is X', 'who is Y', 'how does Z work'), greetings, conversation, stories, jokes, opinions, advice, explanations. CRITICAL: 'what is X', 'who is Y', 'how does Z work', 'tell me about X' are ALWAYS chat, NOT web_search.\n\n"
                        "CRITICAL RULE: if the user wants to do ANYTHING beyond just navigating to a URL (like sign up, login, search on a site, fill a form, buy something), use browser_task — NOT open_url.\n"
                        "CRITICAL RULE: 'remember that' or 'remember my' is chat (storing info), NOT reminder.\n"
                        f"{_STRICT_EXAMPLES}"
                    ),
                },
                {"role": "user", "content": message},
            ],
            max_retries=3,
        )
        intent_data = result.model_dump()
    except Exception:
        intent_data = {"intent": "chat", "target": message, "parameters": {}}

    # Rule-based overrides for common misclassifications
    msg_lower = message.lower().strip()

    # "open [app]" → pc_control if app is a known desktop app
    if msg_lower.startswith("open "):
        app_name = msg_lower.replace("open ", "", 1).strip()
        if app_name in ("notepad", "calculator", "cmd", "terminal", "vscode", "code", "chrome", "edge", "firefox", "explorer", "settings"):
            if intent_data.get("intent") not in ("pc_control",):
                intent_data["intent"] = "pc_control"
                intent_data["target"] = app_name

    # "what is X", "who is Y" → chat (not web_search), but allow weather/time queries
    if msg_lower.startswith(("what is ", "what are ", "who is ", "who's ",
                              "how does ", "how do ", "how can ", "how to ",
                              "tell me about ", "explain ")):
        if intent_data.get("intent") == "web_search":
            intent_data["intent"] = "chat"

    # "what's the weather/temperature" → force weather intent
    if any(p in msg_lower for p in ("weather", "temperature", "forecast", "rain", "sunny", "humidity")):
        if msg_lower.startswith(("what's", "what is", "tell me", "how's")):
            intent_data["intent"] = "weather"

    # "news", "headlines" → force news intent
    if any(p in msg_lower for p in ("headlines", "what's happening", "whats happening")) and "news" in msg_lower:
        if intent_data.get("intent") == "chat":
            intent_data["intent"] = "news"

    # Stock ticker query → force stocks
    stock_patterns = ("stock price", "share price", "market today", "stock market")
    if any(p in msg_lower for p in stock_patterns):
        if intent_data.get("intent") == "chat":
            intent_data["intent"] = "stocks"

    # "what's" without weather → keep as chat if LLM said so
    if msg_lower.startswith("what's "):
        rest = msg_lower[6:]
        if not any(w in rest for w in ("weather", "temperature", "forecast", "stock")):
            if intent_data.get("intent") == "web_search":
                intent_data["intent"] = "chat"

    # "remember that" or "remember my" → chat (not reminder)
    if msg_lower.startswith("remember"):
        if intent_data.get("intent") == "reminder":
            intent_data["intent"] = "chat"
            intent_data["target"] = message

    # "create a github issue" or "create issue" → message (not browser_task)
    if any(p in msg_lower for p in ["create a github", "create an issue", "create issue",
                                      "send an email", "send email", "send a message"]):
        if intent_data.get("intent") in ("browser_task", "open_url"):
            intent_data["intent"] = "message"

    # "play [song]" without "search" → play_media (not web_search)
    if msg_lower.startswith("play ") and "search" not in msg_lower:
        if intent_data.get("intent") == "web_search":
            intent_data["intent"] = "play_media"

    # "open X and play Y" → play_media (always override)
    if msg_lower.startswith("open ") and "play " in msg_lower:
        intent_data["intent"] = "play_media"
        intent_data["target"] = msg_lower.split("play ", 1)[1].strip()

    # Build fallback: if LLM misclassifies "build/create/make/generate" → override to build
    build_triggers = ("build ", "create ", "make ", "generate ")
    if any(msg_lower.startswith(t) for t in build_triggers):
        if intent_data.get("intent") != "build":
            intent_data["intent"] = "build"
            intent_data["target"] = message

    return intent_data


# ══════════════════════════════════════════════
#  SMOLAGENTS TOOL FUNCTIONS
# ══════════════════════════════════════════════

@tool
def open_website(name: str) -> str:
    """Opens a website or web app in the browser.
    Use for: youtube, google, whatsapp, gmail, github, amazon, netflix, spotify, twitter, instagram, facebook, reddit, linkedin.
    Args:
        name: The name of the website to open (e.g., youtube, google, gmail, github, amazon)
    """
    sites = {
        "youtube": "https://youtube.com", "google": "https://google.com",
        "whatsapp": "https://web.whatsapp.com", "gmail": "https://gmail.com",
        "github": "https://github.com", "amazon": "https://amazon.com",
        "netflix": "https://netflix.com", "spotify": "https://open.spotify.com",
        "twitter": "https://twitter.com", "instagram": "https://instagram.com",
        "facebook": "https://facebook.com", "reddit": "https://reddit.com",
        "linkedin": "https://linkedin.com",
    }
    for key, url in sites.items():
        if key in name.lower():
            webbrowser.open(url)
            return f"Opened {key}"
    webbrowser.open(f"https://google.com/search?q={urllib.parse.quote(name)}")
    return f"Searched google for {name}"


@tool
def launch_app(name: str) -> str:
    """Launches a desktop application on the computer.
    Use for: notepad, calculator, vscode, cmd, terminal, chrome, edge, firefox, explorer, folder, settings.
    Args:
        name: The application name (e.g., notepad, vscode, chrome, cmd, explorer)
    """
    apps = {
        "notepad": "notepad.exe", "calculator": "calc.exe",
        "vscode": "code", "code": "code",
        "cmd": "cmd.exe", "terminal": "cmd.exe",
        "chrome": "chrome.exe", "edge": "msedge.exe",
        "firefox": "firefox.exe", "explorer": "explorer.exe",
        "folder": "explorer.exe",
    }
    for key, exe in apps.items():
        if key in name.lower():
            try:
                subprocess.Popen([exe])
                return f"Launched {key}"
            except Exception as e:
                return f"Failed to launch {key}: {e}"
    return f"Unknown app: {name}"


@tool
def play_media(query: str) -> str:
    """Plays music, video, or media from YouTube.
    Use when the user asks to play a song, video, music, or any media.
    Args:
        query: The song or video name to search and play
    """
    q = urllib.parse.quote(query)
    search_url = f"https://www.youtube.com/results?search_query={q}"
    try:
        r = httpx.get(search_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        match = re.search(r"/watch\?v=([a-zA-Z0-9_-]{11})", r.text)
        if match:
            video_url = f"https://www.youtube.com/watch?v={match.group(1)}"
            webbrowser.open(video_url)
            return f"Playing {query}"
    except Exception:
        pass
    webbrowser.open(search_url)
    return f"Searching YouTube for {query}"


@tool
def web_search(query: str) -> str:
    """Searches the web for information.
    Use when the user wants to search for news, facts, information, or anything online.
    Args:
        query: The search query
    """
    from tools.search_fallback import search as search_web, format_results
    results = search_web(query, max_results=5)
    if results:
        return "Search results:\n" + format_results(results, max_len=300)
    return f"No search results found for: {query}"


_KNOWN_SITES = {
    "github": "https://github.com",
    "google": "https://google.com",
    "youtube": "https://youtube.com",
    "gmail": "https://gmail.com",
    "amazon": "https://amazon.com",
    "netflix": "https://netflix.com",
    "spotify": "https://open.spotify.com",
    "twitter": "https://twitter.com",
    "instagram": "https://instagram.com",
    "facebook": "https://facebook.com",
    "reddit": "https://reddit.com",
    "linkedin": "https://linkedin.com",
    "whatsapp": "https://web.whatsapp.com",
}


def _extract_url(task: str) -> str:
    """Extract a URL from a task description."""
    url = task.strip()
    if not url.startswith("http"):
        for site, site_url in _KNOWN_SITES.items():
            if site in url.lower():
                url = site_url
                if "play " in task.lower():
                    song_match = re.search(r'play\s+(.+?)(?:\s+on\s+|\s*$)', task.lower())
                    if song_match:
                        song = song_match.group(1).strip()
                        if site in ("youtube",):
                            url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote(song)
                        else:
                            url = site_url
                break
        else:
            m = re.search(r'(?:https?://\S+)', url)
            if m:
                url = m.group(0)
            else:
                url = "https://google.com/search?q=" + urllib.parse.quote(task)
    return url


async def _browser_automation(task: str) -> str:
    """Core async Playwright browser.
    Extracts a URL from the task description and navigates to it.
    Fresh Playwright context per call — avoids stale browser crashes.
    """
    try:
        url = _extract_url(task)
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled"]
            )
            page = await browser.new_page()
            await page.goto(url, timeout=60000, wait_until="domcontentloaded")
            title = await page.title()
            await browser.close()
            return f"Navigated to {url}: {title}"
    except Exception as e:
        return f"Browser error: {e}"


def _browser_automation_sync(task: str) -> str:
    """Synchronous wrapper: runs Playwright in a dedicated event loop
    (avoids Windows event loop conflicts when called from FastAPI routes)."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_browser_automation(task))
    finally:
        loop.close()


@tool
def browser_automation(task: str) -> str:
    """Opens a URL in the browser using Playwright.
    Use for: navigating to a specific webpage to see its content or interact with it.
    Args:
        task: A URL or description starting with 'go to', 'open', or a direct URL
    """
    return _browser_automation_sync(task)


# ══════════════════════════════════════════════
#  REAL-TIME DATA TOOL FUNCTIONS
# ══════════════════════════════════════════════

@tool
def get_weather(location: str) -> str:
    """Gets current weather for a city or location.
    Use when the user asks about weather, temperature, forecast, rain, sunny.
    Args:
        location: City name (e.g., 'London', 'New York', 'Tokyo')
    """
    from core.integrations import get_weather as _get_weather
    return _get_weather(location)


@tool
def get_news(topic: str) -> str:
    """Gets latest news headlines for a topic.
    Use when the user asks for news, headlines, current events, what's happening.
    Args:
        topic: News topic (e.g., 'technology', 'world', 'sports', 'AI')
    """
    from core.integrations import get_news as _get_news
    return _get_news(topic)


@tool
def get_stock_price(symbol: str) -> str:
    """Gets current stock price for a ticker symbol.
    Use when the user asks about stock price, market, ticker, share price.
    Args:
        symbol: Stock ticker (e.g., 'AAPL', 'GOOGL', 'TSLA', 'MSFT')
    """
    from core.integrations import get_stock_price as _get_stock
    return _get_stock(symbol)


@tool
def get_sports_scores(league: str) -> str:
    """Gets latest sports scores for a league.
    Use when the user asks about scores, games, matches, who won.
    Args:
        league: Sports league (e.g., 'nfl', 'nba', 'mlb', 'nhl', 'soccer')
    """
    from core.integrations import get_sports_scores as _get_scores
    return _get_scores(league)


@tool
def get_time(location: str) -> str:
    """Gets current time for a city or timezone.
    Use when the user asks what time it is, current time, time in a location.
    Args:
        location: City or timezone (e.g., 'Tokyo', 'London', 'America/New_York') or empty for local time
    """
    from core.integrations.timezone import get_time_info
    return get_time_info(location)


_ACTION_AGENT = None


def _get_action_agent():
    global _ACTION_AGENT
    if _ACTION_AGENT is None:
        # Gather the same tool list that was previously passed to ToolCallingAgent
        tools = [play_media, open_website, web_search, launch_app, browser_automation,
                 get_weather, get_news, get_stock_price, get_sports_scores, get_time] + COMPOSIO_TOOLS
        # Use the new CoworkOrchestrator which will try to employ CrewAI (or LangGraph)
        # and fall back to the original ToolCallingAgent when those libraries are not present.
        from orchestration.cowork_agent import CoworkOrchestrator
        _ACTION_AGENT = CoworkOrchestrator(tools=tools)
    return _ACTION_AGENT


def _build_html_page(target_text: str) -> dict:
    """Standalone HTML page builder — generates any webpage via LLM, saves to Desktop, opens in Chrome."""
    try:
        now_dt = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = re.sub(r'[^a-zA-Z0-9_]+', '_', target_text.strip())[:20] or "page"
        filename = f"{safe_name}_{now_dt}.html"
        filepath = os.path.join(os.path.expanduser("~/Desktop"), filename)

        prompt = (
            "Generate a complete, beautiful single HTML page for: " + target_text + "\n"
            "Requirements:\n"
            "- Single self-contained HTML file (CSS + JS inline)\n"
            "- Modern, professional design with gradients, animations, responsive layout\n"
            "- NO markdown, NO code fences, NO backticks - output ONLY raw HTML starting with <!DOCTYPE html>\n"
            "- Include relevant content sections based on the request\n"
            "- Use gradient colors, card layouts, hover effects\n"
            "- Make it look like a professional production website\n"
        )

        try:
            resp = httpx.post(
                "http://localhost:11434/api/generate",
                json={"model": "llama3.1:8b", "prompt": prompt, "stream": False,
                       "options": {"temperature": 0.7, "num_predict": 4096}},
                timeout=120,
            )
            data = resp.json()
            raw = data.get("response", "")
        except Exception:
            raw = ""

        html = ""
        if raw:
            start = raw.find("<!DOCTYPE")
            if start >= 0:
                raw = raw[start:]
            end = raw.rfind("</html>")
            if end >= 0:
                raw = raw[:end + 7]
            if len(raw) > 100:
                html = raw

        if not html:
            page_name = safe_name.replace("_", " ").title()
            html = (
                '<!DOCTYPE html>\n<html lang="en"><head><meta charset="UTF-8">'
                '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
                f'<title>{page_name}</title><style>\n'
                '* { margin:0; padding:0; box-sizing:border-box; }\n'
                'body { font-family:Segoe UI,sans-serif; background:linear-gradient(135deg,#0f0c29,#302b63,#24243e); '
                'min-height:100vh; color:#fff; display:flex; align-items:center; justify-content:center; }\n'
                '.container { text-align:center; padding:2rem; }\n'
                'h1 { font-size:3rem; background:linear-gradient(45deg,#f093fb,#f5576c); '
                '-webkit-background-clip:text; -webkit-text-fill-color:transparent; }\n'
                'p { color:#ccc; margin-top:1rem; }\n'
                '</style></head><body><div class="container">'
                f'<h1>{page_name}</h1><p>Generated by JARVIS</p>'
                '</div></body></html>'
            )

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html)

        import webbrowser
        chrome_path = None
        for path in [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expanduser("~\\AppData\\Local\\Google\\Chrome\\Application\\chrome.exe"),
        ]:
            if os.path.isfile(path):
                chrome_path = path
                break
        if chrome_path:
            webbrowser.register("chrome", None, webbrowser.BackgroundBrowser(chrome_path))
            webbrowser.get("chrome").open("file://" + filepath)
        else:
            webbrowser.open("file://" + filepath)

        return {"executed": True, "action": f"Webpage built and opened in Chrome \u2014 {filename}"}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"executed": False, "error": f"Build failed: {e}"}


async def execute_action(intent_data: dict, message: str = "", db=None, user=None) -> dict:
    intent = intent_data.get("intent", "chat")

    # Handle reminders via old path (needs db+user)
    if intent in ("reminder", "set_reminder"):
        target = intent_data.get("target", "")
        if db is not None and user is not None:
            try:
                from reminders.manager import create_reminder
                params = intent_data.get("parameters", {})
                time_str = params.get("time", "")
                remind_at = parse_time_relative(time_str)
                r = await create_reminder(db, user, target, remind_at, f"Reminder: {target}")
                return {"executed": True, "action": "reminder_created", "title": target, "remind_at": remind_at.isoformat(), "id": r.id}
            except Exception as e:
                return {"executed": False, "error": f"Failed to create reminder: {e}"}
        return {"executed": True, "action": f"Reminder noted: {target}"}

    # Browser task → use synchronous wrapper (avoids Windows event loop conflict with Playwright)
    if intent == "browser_task":
        target = intent_data.get("target") or message or ""
        if target:
            result = await asyncio.to_thread(_browser_automation_sync, target)
            if "error" in result.lower() or "failed" in result.lower() or "can't" in result.lower():
                return {"executed": True, "error": result}
            return {"executed": True, "action": result}
        return {"executed": False, "error": "no browser task target"}

    # Open URL → direct webbrowser open (avoids agent model failures)
    if intent == "open_url":
        target = intent_data.get("target") or message or ""
        if not target:
            # Try to extract a URL/name from the message
            for site, url in _KNOWN_SITES.items():
                if site in message.lower():
                    target = site
                    break
        if target:
            site_url = _KNOWN_SITES.get(target.lower(), "")
            if site_url:
                webbrowser.open(site_url)
                return {"executed": True, "action": f"Opened {target}"}
            # Treat as direct URL
            if not target.startswith("http"):
                target = "https://" + target
            webbrowser.open(target)
            return {"executed": True, "action": f"Navigated to {target}"}
        return {"executed": False, "error": "no URL target"}

    # Play media → direct YouTube search + open (avoids agent model failures)
    if intent == "play_media":
        target = intent_data.get("target") or message or ""
        if not target:
            return {"executed": False, "error": "no media target"}
        try:
            q = urllib.parse.quote(target)
            # YouTube search limited to video results only (sp=EgIQAQ%3D%3D)
            search_url = f"https://www.youtube.com/results?search_query={q}&sp=EgIQAQ%253D%253D"
            r = httpx.get(search_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
            # Find first video ID in the results page
            match = re.search(r"/watch\?v=([a-zA-Z0-9_-]{11})", r.text)
            if match:
                video_url = f"https://www.youtube.com/watch?v={match.group(1)}"
                webbrowser.open(video_url)
                return {"executed": True, "action": f"Playing {target} on YouTube"}
            # Fallback – open the search page so user can pick manually
            webbrowser.open(search_url)
            return {"executed": True, "action": f"Searching YouTube for {target}"}
        except Exception as e:
            fallback_url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(target)}"
            webbrowser.open(fallback_url)
            return {"executed": True, "action": f"Searching YouTube for {target}"}

    # Real-time data intents → direct API calls
    if intent == "weather":
        location = intent_data.get("target") or message.replace("weather in", "").replace("temperature in", "").replace("weather", "").replace("temperature", "").strip() or "local"
        result = get_weather(location)
        return {"executed": True, "action": result}

    if intent == "news":
        topic = intent_data.get("target") or message.replace("news", "").replace("latest", "").replace("headlines", "").strip() or "latest"
        result = get_news(topic)
        return {"executed": True, "action": result}

    if intent == "stocks":
        symbol = intent_data.get("target") or "AAPL"
        result = get_stock_price(symbol)
        return {"executed": True, "action": result}

    if intent == "sports":
        league = intent_data.get("target") or "nfl"
        result = get_sports_scores(league)
        return {"executed": True, "action": result}

    if intent == "time":
        location = intent_data.get("target") or message.replace("time in", "").replace("time at", "").replace("current time", "").strip() or ""
        result = get_time(location)
        return {"executed": True, "action": result}

    # Web search → uses search_fallback (SearXNG → DDGS → Google URL)
    if intent in ("web_search", "search"):
        query = intent_data.get("target") or message or ""
        if not query:
            return {"executed": False, "error": "no search query"}
        from tools.search_fallback import search as search_web, format_results
        results = search_web(query, max_results=5)
        if results:
            formatted = format_results(results, max_len=300)
            return {"executed": True, "action": f"Search results:\n{formatted}"}
        google_url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
        return {"executed": True, "action": f"No search results found. Opened Google search: {google_url}"}

    # PC Control → launch desktop apps, including chrome with URL
    if intent == "pc_control":
        target = intent_data.get("target") or message or ""
        # Extract URL if present in message
        url_match = re.search(r'(https?://[^\s]+)', target)
        if url_match or ("chrome" in target.lower() and "://" in target):
            url = url_match.group(1) if url_match else target.split(" ", 1)[1] if " " in target else ""
            if url and "chrome" in target.lower() and url != "chrome":

                if not url.startswith("http"):
                    url = "https://" + url
                webbrowser.open(url)
                return {"executed": True, "action": f"Opened {url} in Chrome"}
        # Direct app launching
        KNOWN_APPS = {
            "notepad": ("notepad.exe", None),
            "calculator": ("calc.exe", None),
            "cmd": ("cmd.exe", None),
            "terminal": ("cmd.exe", None),
            "explorer": ("explorer.exe", None),
            "chrome": ("C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe", "chrome"),
            "edge": ("msedge.exe", "microsoft-edge:"),
            "firefox": ("firefox.exe", None),
            "vscode": ("code", None),
            "code": ("code", None),
            "spotify": ("spotify.exe", None),
        }
        target_lower = target.lower().strip()
        if target_lower in KNOWN_APPS:
            exe, prefix = KNOWN_APPS[target_lower]
            try:
                subprocess.Popen([exe])
                return {"executed": True, "action": f"Launched {target_lower}"}
            except Exception as e:
                return {"executed": False, "error": f"Failed to launch {target_lower}: {e}"}
        # Try partial match against known apps
        for name, (exe, _) in KNOWN_APPS.items():
            if name in target_lower:
                try:
                    subprocess.Popen([exe])
                    return {"executed": True, "action": f"Launched {name}"}
                except Exception as e:
                    return {"executed": False, "error": f"Failed to launch {name}: {e}"}
        # Try as direct executable name
        try:
            subprocess.Popen([target_lower])
            return {"executed": True, "action": f"Launched {target_lower}"}
        except Exception:
            pass

    # Build intent → call standalone builder
    if intent == "build":
        try:
            target = intent_data.get("target") or message or ""
            return _build_html_page(target)
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {"executed": False, "error": f"Build failed: {e}"}

    # Code task → delegate to opencode
    if intent == "code_task":
        from core.opencode_delegate import delegate_to_opencode, is_opencode_task
        if is_opencode_task(message or intent_data.get("target", "")):
            from core.context_hub import ContextHub
            hub = ContextHub()
            ctx = await hub.gather(task_type="code", prompt=message)
            result = await delegate_to_opencode(
                task=message,
                context={"context_hub": hub, "extra_context": hub.format_for_prompt(ctx)},
                timeout=300,
            )
            if result.get("success"):
                return {"executed": True, "action": f"OpenCode completed:\n{result['stdout'][:2000]}"}
            else:
                return {"executed": False, "error": result.get("error", "OpenCode failed"), "action": result.get("stdout", "")[:1000]}
        return {"executed": False, "action": "code_task_passthrough"}

    # Chat intent → no action
    if intent == "chat":
        return {"executed": False, "action": "chat_only"}

    # Everything else → smolagens agent decides tools and handles multi-step
    try:
        agent = _get_action_agent()
        msg = message or intent_data.get("target", "")
        if not msg:
            return {"executed": False, "error": "no message to act on"}
        loop = asyncio.get_event_loop()
        future = loop.run_in_executor(None, agent.run, msg)
        result = await asyncio.wait_for(future, timeout=90)
        return {"executed": True, "action": str(result)}
    except asyncio.TimeoutError:
        return {"executed": False, "error": "Agent timed out after 90s"}
    except Exception as e:
        return {"executed": False, "error": str(e)}


def parse_time_relative(time_str: str):
    from datetime import datetime, timedelta
    now = datetime.utcnow()
    if not time_str:
        return now + timedelta(hours=1)
    tl = time_str.lower()
    if "minute" in tl:
        nums = re.findall(r'\d+', tl)
        minutes = int(nums[0]) if nums else 1
        return now + timedelta(minutes=minutes)
    if "hour" in tl:
        nums = re.findall(r'\d+', tl)
        hours = int(nums[0]) if nums else 1
        return now + timedelta(hours=hours)
    if "tomorrow" in tl:
        nums = re.findall(r'\d+', tl)
        if nums:
            return now + timedelta(days=1, hours=int(nums[0]) % 24)
        return now + timedelta(days=1)
    if "today" in tl or "now" in tl:
        nums = re.findall(r'\d+', tl)
        if nums:
            return now.replace(hour=int(nums[0]) % 24, minute=0, second=0)
        return now + timedelta(minutes=1)
    return now + timedelta(hours=1)


# ==============================================
#  ROUTES — ASSISTANT
# ==============================================
@app.post("/api/chat")
async def chat(
    req: ChatRequest,
    debug: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_token)
):
    from core.database import ChatHistory
    from core.model_router import route_request, get_router_model
    from core.llm_router import router as llm_router, health_check

    # Step 1: Check LLM connectivity
    if not await health_check():
        # fallback: direct Ollama ping
        try:
            ollama_check = httpx.get("http://localhost:11434/api/tags", timeout=2)
            if ollama_check.status_code != 200:
                return JSONResponse(
                    status_code=503,
                    content={"response": "Ollama is offline. Run: ollama serve", "intent": {"intent": "chat"}, "action": {"executed": False}}
                )
        except (httpx.ConnectError, httpx.TimeoutException):
            return JSONResponse(
                status_code=503,
                content={"response": "Ollama is offline. Run: ollama serve", "intent": {"intent": "chat"}, "action": {"executed": False}}
            )

    # Step 2: Privacy routing (tier-based model selection + PII sanitization)
    model_name, privacy_tier, sanitized_message = route_request(req.message, force_tier=req.tier)

    # Step 2.5: Presentation mode — /p prefix triggers deterministic slides
    is_presentation = sanitized_message.startswith("/p ") or sanitized_message.startswith("/P ")
    if is_presentation:
        presentation_prompt = sanitized_message[3:].strip()
        import re as _re, json as _json

        # Step A: Get narrative response
        try:
            pmsg = [
                {"role": "system", "content": "You are JARVIS giving a live presentation. Speak naturally. Be concise (2-4 sentences)."},
                {"role": "user", "content": presentation_prompt}
            ]
            pres_reply = await llm_router.acompletion(model="automation", messages=pmsg, timeout=120)
            clean_response = _re.sub(r'<think>.*?</think>', '', pres_reply.choices[0].message.content, flags=_re.DOTALL).strip()
        except Exception:
            clean_response = f"Let me present: {presentation_prompt}"

        # Step B: Build slides DETERMINISTICALLY from prompt keywords
        p_lower = presentation_prompt.lower()
        slides = []

        # Debug: log that we reached slide building
        with open("C:\\Users\\peter\\AppData\\Local\\Temp\\jarvis_debug.txt", "a") as _df:
            _df.write(f"p_lower={p_lower} keywords={[w for w in ['you','yourself','creator','pavan','introduce','who'] if w in p_lower]}\n")

        # Add creator card if talking about self/creator/pavan
        if any(w in p_lower for w in ["you", "yourself", "creator", "pavan", "introduce", "who"]):
            slides.append({
                "view": "card", "type": "creator", "image": "pavan.jpg",
                "title": "CREATOR", "text": "Pavan Kumar — diploma student from Gudlavalleru. Built JARVIS from scratch as proof that local AI can match the giants.",
                "duration": 5000, "privacy": "LOCAL", "orb": 0.7, "keyword": "pavan"
            })
            with open("C:\\Users\\peter\\AppData\\Local\\Temp\\jarvis_debug.txt", "a") as _df:
                _df.write(f"added creator slide, total={len(slides)}\n")

        # Add capability cards
        if any(w in p_lower for w in ["capabilit", "feature", "can do", "what", "automation"]):
            slides.append({
                "view": "cards", "cards": [
                    {"type": "insight", "title": "VOICE", "text": "STT via faster-whisper. TTS via Kokoro. Wake word detection. Full duplex voice pipeline."},
                    {"type": "insight", "title": "AUTOMATION", "text": "n8n workflows, PC control, web search via SearXNG, browser automation via Playwright."},
                    {"type": "insight", "title": "MEMORY", "text": "Semantic tiered memory with epistemological tagging: every answer is [VERIFIED] or [ASSUMED]."},
                ], "duration": 6000, "privacy": "LOCAL"
            })

        # Add architecture graph
        if any(w in p_lower for w in ["architectur", "structure", "system", "pipeline", "how"]):
            slides.append({
                "view": "graph",
                "nodes": [
                    {"id": "a", "label": "User Input", "type": "concept"},
                    {"id": "b", "label": "Intent Classifier", "type": "action"},
                    {"id": "c", "label": "LLM (qwen3:4b)", "type": "data"},
                    {"id": "d", "label": "Action Executor", "type": "action"},
                    {"id": "e", "label": "OS / Web / Apps", "type": "person"},
                ],
                "edges": [
                    {"from": "a", "to": "b", "label": "message"},
                    {"from": "b", "to": "c", "label": "intent"},
                    {"from": "c", "to": "d", "label": "tool call"},
                    {"from": "d", "to": "e", "label": "execute"},
                    {"from": "e", "to": "c", "label": "result"},
                ],
                "duration": 7000, "privacy": "HYBRID", "orb": 0.6
            })

        # Add agents comparison
        if any(w in p_lower for w in ["agent", "tool", "cli", "command", "sub"]):
            slides.append({
                "view": "compare",
                "a": {"name": "JARVIS 6 AGENTS", "rows": [
                    {"key": "Codex CLI", "value": "Scaffold projects", "winner": "a"},
                    {"key": "Aider", "value": "Modify existing code", "winner": "a"},
                    {"key": "Gemini CLI", "value": "Research + tests", "winner": "a"},
                    {"key": "OpenCode", "value": "Multi-step tasks", "winner": "a"},
                ]},
                "b": {"name": "MANUAL", "rows": [
                    {"key": "Codex CLI", "value": "Manual project setup"},
                    {"key": "Aider", "value": "Manual code editing"},
                    {"key": "Gemini CLI", "value": "Manual research"},
                    {"key": "OpenCode", "value": "Manual execution"},
                ]},
                "duration": 7000, "privacy": "LOCAL"
            })

        # Add data/stats slide
        slides.append({
            "view": "data", "stats": [
                {"val": "13", "label": "AI MODELS"},
                {"val": "6", "label": "AGENTS"},
                {"val": "54K", "label": "LINES OF CODE"},
                {"val": "1", "label": "CREATOR"},
            ], "bars": [
                {"label": "Local Speed", "value": 92, "max": 100},
                {"label": "Privacy", "value": 100, "max": 100},
                {"label": "Automation", "value": 85, "max": 100},
            ], "duration": 5000, "privacy": "LOCAL"
        })

        # Add closing action toast
        slides.append({
            "view": "action", "toast": "Presentation complete", "duration": 2000
        })

        result = {
            "response": clean_response,
            "intent": {"intent": "chat", "action": "presentation", "target": presentation_prompt},
            "action": {"executed": False},
            "model": model_name,
            "privacy_tier": "LOCAL",
            "presentation": slides,
            "show_ambassador": True,
        }
        db.add(ChatHistory(user_id=user.id, role="user", message=sanitized_message, intent="presentation", session_id=req.session_id))
        db.add(ChatHistory(user_id=user.id, role="assistant", message=result["response"], intent="presentation", session_id=req.session_id))
        await db.commit()
        return result

    # Duplicate user message detection – avoid repeating identical queries
    from sqlalchemy import select
    user_msg_q = select(ChatHistory).where(ChatHistory.user_id == user.id).where(ChatHistory.role == "user")
    if req.session_id:
        user_msg_q = user_msg_q.where(ChatHistory.session_id == req.session_id)
    last_user_msg_res = await db.execute(user_msg_q.order_by(ChatHistory.timestamp.desc()).limit(1))
    last_user_entry = last_user_msg_res.scalars().first()
    if last_user_entry and last_user_entry.message.strip() == sanitized_message.strip():
        assist_q = select(ChatHistory).where(ChatHistory.user_id == user.id).where(ChatHistory.role == "assistant")
        if req.session_id:
            assist_q = assist_q.where(ChatHistory.session_id == req.session_id)
        last_assist_res = await db.execute(assist_q.order_by(ChatHistory.timestamp.desc()).limit(1))
        last_assist_entry = last_assist_res.scalars().first()
        response_text = last_assist_entry.message if last_assist_entry else "I already answered that."
        return {"response": response_text, "intent": {"intent": "chat"}, "action": {"executed": False}, "model": model_name, "privacy_tier": privacy_tier.value if privacy_tier else "LOCAL"}
    # Step 3: Extract intent using LLM
    intent_data = await extract_intent(sanitized_message)

    # Step 4: Execute real action if needed
    action_result = await execute_action(intent_data, message=req.message, db=db, user=user)

    # Step 4: Determine current intent for history scoping
    current_intent = intent_data.get("intent", "chat")

    # Step 5: If action failed, respond directly without LLM (avoid hallucination)
    if action_result.get("executed") and action_result.get("error"):
        reply = f"I tried but couldn't complete that: {action_result['error']}"
        result = {
            "response": reply,
            "intent": intent_data,
            "action": action_result,
            "model": model_name,
            "privacy_tier": privacy_tier.value if privacy_tier else "LOCAL",
        }
        db.add(ChatHistory(user_id=user.id, role="user", message=sanitized_message, intent=current_intent, session_id=req.session_id))
        db.add(ChatHistory(user_id=user.id, role="assistant", message=result["response"], intent=current_intent, session_id=req.session_id))
        await db.commit()
        from notes.activity_tracker import activity_tracker
        await activity_tracker.log(db, user.id, "voice_command", f"Chat: {sanitized_message[:100]}")
        return result

    # Build action context: include last action done by user for recall
    action_context = ""
    if action_result.get("executed") and not action_result.get("error") and current_intent != "chat":
        action_context = f"\n[SYSTEM: Action executed: {json.dumps(action_result)}]"

    # Check if user is asking about previous actions ("what did you do")
    asking_about_actions = any(phrase in req.message.lower() for phrase in
        ["what did you do", "what you did", "what have you done", "what happened", "what did i ask"])

    if asking_about_actions:
        # Fetch last 5 actions across any intent for recall
        try:
            from datetime import datetime, timedelta
            from sqlalchemy import select
            from core.database import ChatHistory
            cutoff = datetime.utcnow() - timedelta(minutes=30)
            action_q = select(ChatHistory).where(ChatHistory.user_id == user.id).where(ChatHistory.timestamp >= cutoff).where(ChatHistory.intent != "chat")
            if req.session_id:
                action_q = action_q.where(ChatHistory.session_id == req.session_id)
            action_result_db = await db.execute(
                action_q.order_by(ChatHistory.timestamp.desc()).limit(5)
            )
            recent_actions = list(action_result_db.scalars().all())
            if recent_actions:
                action_lines = []
                for a in reversed(recent_actions):
                    action_lines.append(f"[{a.timestamp.strftime('%H:%M')}] {a.role}: {a.message[:200]}")
                action_context += "\n[SYSTEM: Recent non-chat history:\n" + "\n".join(action_lines) + "\n]"
        except Exception:
            pass

        # Auto-capture personal contact info in a note
        personal_info_pattern = re.compile(r'(name\s*[:\-]?\s*\w+|age\s*[:\-]?\s*\d+|[0-9]{10}|mail\w*)', re.IGNORECASE)
        if personal_info_pattern.search(sanitized_message):
            from notes.activity_tracker import notes_manager
            name_match = re.search(r'name\s*[:\-]?\s*([\w\s]+)', sanitized_message, re.IGNORECASE)
            title = f"Contact info for {name_match.group(1).strip()}" if name_match else "Contact info"
            await notes_manager.create(db, user, title, sanitized_message, tags="contact")

        # Step 6: Build conversation history context (full history, all intents)
    history_limit = 15
    from prompts import build_prompt
    prompt_context = {"action_result": action_context} if action_context else {}
    system_content = build_prompt("chat", prompt_context)
    messages = [
        {"role": "system", "content": system_content},
    ]
    try:
        from sqlalchemy import select
        from core.database import ChatHistory
        hist_q = select(ChatHistory).where(ChatHistory.user_id == user.id)
        if req.session_id:
            hist_q = hist_q.where(ChatHistory.session_id == req.session_id)
        result = await db.execute(
            hist_q.order_by(ChatHistory.timestamp.desc()).limit(history_limit)
        )
        recent = list(result.scalars().all())
        history_count = len(recent)
        recent.reverse()
        # Summarize if history exceeds threshold
        if len(recent) > 25:
            oldest = recent[:-20]
            newest = recent[-20:]
            summary_text = "; ".join(epistemic_tagger.strip_tags(f"{t.role}: {t.message[:100]}") for t in oldest)
            messages.append({"role": "system", "content": f"Earlier conversation summary: {summary_text}"})
            for turn in newest:
                messages.append({"role": turn.role, "content": epistemic_tagger.strip_tags(turn.message)})
        else:
            for turn in recent:
                messages.append({"role": turn.role, "content": epistemic_tagger.strip_tags(turn.message)})
    except Exception:
        history_count = 0
        pass
    messages.append({"role": "user", "content": sanitized_message})

    # Step 6: Get LLM response — skip for non-chat action intents
    non_chat_intents = ("build", "pc_control", "open_url", "play_media",
                        "reminder", "weather", "news", "stocks", "sports", "time", "web_search", "search", "code_task")
    if current_intent in non_chat_intents and action_result.get("executed") and not action_result.get("error"):
        reply = action_result.get("action", f"{current_intent} completed")
    else:
        try:
            model_group = "cloud" if model_name == "cloud" else get_router_model(intent_data.get("intent", "chat"))
            reply = await llm_router.acompletion(
                model=model_group,
                messages=messages,
                timeout=120,
            )
            reply = reply.choices[0].message.content
            reply = epistemic_tagger.strip_tags(reply)
        except Exception as e:
            reply = ""
            if action_result.get("executed"):
                reply = f"Action completed: {action_result.get('action', '')}"
            else:
                reply = "I had a temporary issue processing that request."

    # Step 7: Build response with privacy metadata
    result = {
        "response": reply,
        "intent": intent_data,
        "action": action_result,
        "model": model_name,
        "privacy_tier": privacy_tier.value if privacy_tier else "LOCAL",
        "epistemic_tags": [],
    }

    db.add(ChatHistory(user_id=user.id, role="user", message=sanitized_message, intent=current_intent, session_id=req.session_id))
    db.add(ChatHistory(user_id=user.id, role="assistant", message=result["response"], intent=current_intent, session_id=req.session_id))
    await db.commit()

    from notes.activity_tracker import activity_tracker
    await activity_tracker.log(db, user.id, "voice_command", f"Chat: {sanitized_message[:100]}")

    # Debug dump: return raw LLM context + response when debug=true
    if debug:
        result["_debug"] = {
            "session_id": req.session_id,
            "messages_sent": [{"role": m["role"], "content_preview": m["content"][:200]} for m in messages],
            "raw_response": reply,
            "model": model_name,
            "history_count": history_count,
        }

    # Self-healing check: detect LLM failures
    if hasattr(app.state, "self_healing"):
        await app.state.self_healing.check(
            "llm_response",
            healthy=bool(reply and len(reply) > 10),
            detail=f"response_len={len(reply or '')} intent={current_intent}"
        )
        app.state.self_healing.save()

    return result


@app.post("/api/generate-ui")
async def generate_ui(
    req: ChatRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_token),
):
    from core.file_agent import file_agent
    from prompts import UI_SYSTEM_PROMPT

    framework = req.context or "html"

    system_msg = UI_SYSTEM_PROMPT + f"\n\nTarget framework: {framework}\n\nGenerate the complete file now. Output ONLY the file content (no markdown fences)."
    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": req.message},
    ]

    model_group = "code"
    from core.llm_router import router as ui_llm_router
    try:
        response = await ui_llm_router.acompletion(
            model=model_group,
            messages=messages,
            timeout=180,
        )
        code = response.choices[0].message.content
    except Exception as e:
        return {"error": str(e), "code": None}

    code = code.strip()
    if code.startswith("```"):
        code = code.split("\n", 1)[1] if "\n" in code else code[3:]
        if code.endswith("```"):
            code = code[:-3].strip()

    file_path = None
    if framework == "html":
        file_path = str(Path.home() / ".jarvis" / "generated_ui" / f"ui_{uuid.uuid4().hex[:8]}.html")
    elif framework == "flutter":
        file_path = str(Path.home() / ".jarvis" / "generated_ui" / f"ui_{uuid.uuid4().hex[:8]}.dart")
    else:
        ext = framework.split(".")[-1] if "." in framework else "txt"
        file_path = str(Path.home() / ".jarvis" / "generated_ui" / f"ui_{uuid.uuid4().hex[:8]}.{ext}")

    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    try:
        import aiofiles
        async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
            await f.write(code)
    except ImportError:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(code)

    return {
        "code": code,
        "file_path": file_path,
        "framework": framework,
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
#  ROUTES — REMINDERS
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
#  ROUTES — NOTES
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
#  ROUTES — ACTIVITY & SUMMARY
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
#  ROUTES — MESSAGING AUTOMATION
# ==============================================
@app.post("/api/message/send")
async def send_message(
    req: MessageRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_token)
):
    from automation.messaging import messaging
    from notes.activity_tracker import activity_tracker

    if req.platform == "whatsapp":
        success = messaging.send_whatsapp(req.recipient, req.message)
    elif req.platform == "instagram":
        success = messaging.send_instagram_dm(req.recipient, req.message)
    else:
        raise HTTPException(400, "Platform must be 'whatsapp' or 'instagram'")

    await activity_tracker.log(
        db, user.id, "message_sent",
        f"Sent {req.platform} message to {req.recipient}"
    )
    return {"success": success, "platform": req.platform, "recipient": req.recipient}


# ==============================================
#  ROUTES — FACE RECOGNITION
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
#  ROUTES — MEDIA PLAYER
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
#  ROUTES — FILE MANAGER
# ==============================================
@app.get("/api/files")
async def list_files(path: str = "~", user: User = Depends(verify_token)):
    import os
    resolved = os.path.expanduser(path)
    if not os.path.exists(resolved):
        raise HTTPException(404, "Path not found")
    if not os.path.isdir(resolved):
        raise HTTPException(400, "Not a directory")

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
    dest_dir = os.path.expanduser(path)
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, file.filename)
    data = await file.read()
    with open(dest, "wb") as f:
        f.write(data)
    return {"saved_to": dest, "size": len(data)}


# ==============================================
#  ROUTES — DASHBOARD STATS
# ==============================================
@app.get("/api/stats")
async def dashboard_stats():
    reminders_count = 0
    try:
        from core.database import get_db
        async for session in get_db():
            from reminders.manager import count_reminders
            reminders_count = await count_reminders(session)
    except Exception:
        pass
    return {
        "gpu_vram": "4.2 / 12 GB",
        "gpu_pct": 35,
        "memory_hot": 12,
        "memory_cold": 88,
        "search_queries": 3,
        "commands": 0,
        "reminders": reminders_count,
        "notes": 0,
        "active_models": {
            "chat": os.getenv("CHAT_MODEL", "qwen3:4b"),
            "code": os.getenv("CODE_MODEL", "qwen2.5-coder:3b"),
            "vision": os.getenv("VISION_MODEL", "moondream")
        }
    }

# ==============================================
#  ROUTES — VOICE (STT/TTS)
# ==============================================
@app.post("/stt")
async def speech_to_text(file: UploadFile = File(...), user: User = Depends(verify_token)):
    from assistant.stt import get_stt
    audio_data = await file.read()
    text = get_stt().transcribe(audio_data)
    if not text:
        raise HTTPException(500, "Transcription failed")
    return {"transcript": text}

@app.post("/stt/local")
async def speech_to_text_local(file: UploadFile = File(...)):
    """Local-only STT — no auth required. For laptop mic testing."""
    audio_data = await file.read()
    text = get_stt().transcribe(audio_data)
    if not text:
        raise HTTPException(500, "Transcription failed")
    return {"transcript": text}

@app.post("/stt/base64")
async def speech_to_text_base64(req: dict):
    """STT accepting JSON with base64 audio."""
    if "audio" not in req:
        raise HTTPException(400, "Missing 'audio' field (base64 WAV)")
    import base64
    audio_data = base64.b64decode(req["audio"])
    text = get_stt().transcribe(audio_data)
    return {"transcript": text or ""}

@app.post("/tts")
async def text_to_speech(req: dict):
    from assistant.tts import get_tts
    text = req.get("text", "")
    if not text:
        raise HTTPException(400, "Text is required")
    
    audio_bytes = get_tts().synthesize(text)
    if not audio_bytes:
        raise HTTPException(500, "TTS generation failed")
    
    from fastapi.responses import Response
    return Response(content=audio_bytes, media_type="audio/wav")

@app.post("/api/tts/chatterbox")
async def tts_chatterbox(req: dict):
    from assistant.edge_tts_module import EdgeTTS
    text = req.get("text", "")
    if not text:
        raise HTTPException(400, "Text is required")
    tts = EdgeTTS(voice="en-US-ChristopherNeural")
    loop = asyncio.get_event_loop()
    audio_bytes = await tts.synthesize(text)
    if not audio_bytes:
        raise HTTPException(500, "TTS generation failed")
    from fastapi.responses import Response
    return Response(content=audio_bytes, media_type="audio/mpeg")

@app.post("/voice/test")
async def voice_test():
    from assistant.stt import get_stt
    from assistant.tts import get_tts
    import sounddevice as sd, numpy as np, io, soundfile as sf
    sr = 16000
    loop = asyncio.get_event_loop()

    def _run():
        print("[VoiceTest] Recording 3s...")
        recording = sd.rec(int(sr * 3), samplerate=sr, channels=1, dtype="float32")
        sd.wait()
        buf = io.BytesIO()
        sf.write(buf, recording, sr, format="WAV", subtype="PCM_16")
        audio_bytes = buf.getvalue()
        print(f"[VoiceTest] Recorded {len(audio_bytes)} bytes")

        text = get_stt().transcribe(audio_bytes)
        print(f"[VoiceTest] STT: {text}")

        response = f'I heard you say: {text}' if text else 'Sorry, I did not catch that.'
        tts_bytes = get_tts().synthesize(response)
        print(f"[VoiceTest] TTS: {len(tts_bytes)} bytes")

        data, play_sr = sf.read(io.BytesIO(tts_bytes))
        sd.play(data, play_sr)
        sd.wait()
        print("[VoiceTest] Playback done")
        return {"transcript": text, "response": response}

    return await loop.run_in_executor(None, _run)

@app.websocket("/tts/stream")
async def tts_stream_websocket(ws: WebSocket):
    from assistant.tts import get_tts
    await ws.accept()
    try:
        while True:
            data = await ws.receive_json()
            text = data.get("text", "")
            if text:
                audio_bytes = get_tts().synthesize(text)
                await ws.send_bytes(audio_bytes)
    except Exception as e:
        print(f"[TTS Stream] Error: {e}")
        await ws.close()


# ==============================================
#  WEBSOCKET — VOICE PIPELINE (STT + LLM + TTS)
# ==============================================
@app.websocket("/voice")
async def voice_websocket(ws: WebSocket):
    """WebSocket voice endpoint: receives raw audio, returns WAV audio.
    Flow: mic audio -> STT -> llm_router -> TTS -> speaker audio
    """
    from assistant.voice_pipeline import get_pipeline

    await ws.accept()
    pipeline = get_pipeline()
    try:
        while True:
            audio_bytes = await ws.receive_bytes()
            if not audio_bytes or len(audio_bytes) < 1024:
                continue
            audio_out = await pipeline.process_audio(audio_bytes)
            if audio_out:
                await ws.send_bytes(audio_out)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"[Voice WS] Error: {e}")
        await ws.close()


# ==============================================
#  ROUTES — BROWSER AGENT
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
#  WEBSOCKET — CHAT STREAM (for real-time streaming AI responses)
# ==============================================
@app.websocket("/ws/chat_stream")
async def chat_stream_websocket(ws: WebSocket):
    """
    Unified WebSocket handler: uses same LLM intent pipeline as REST API.
    """
    from core.model_router import route_request, get_router_model
    from core.llm_router import router as llm_router
    from assistant.engine import jarvis

    await ws.accept()
    try:
                while True:
                    raw = await ws.receive_text()
                    import json
                    msg = json.loads(raw)
                    msg_type = msg.get('type')

                    if msg_type == 'chat':
                        text = msg.get('text', '')
                        # Duplicate detection – avoid processing the same user message twice
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
                        model, tier, processed_query = route_request(text)

                        # Use same LLM-based intent + action pipeline as REST API
                        intent_data = await extract_intent(processed_query)
                        action_result = await execute_action(intent_data, message=text)
                        current_intent = intent_data.get("intent", "chat")

                        non_chat_intents = ("build", "pc_control", "open_url", "play_media",
                                            "reminder", "weather", "news", "stocks", "sports", "time", "web_search", "search")
                        if current_intent in non_chat_intents and action_result.get("executed") and not action_result.get("error"):
                            response_text = action_result.get("action", f"{current_intent} completed")
                        else:
                            try:
                                model_group = "cloud" if model == "cloud" else get_router_model(current_intent)
                                resp = await llm_router.acompletion(
                                    model=model_group,
                                    messages=[{"role": "system", "content": "You are JARVIS, your AI assistant. Be concise."},
                                              {"role": "user", "content": processed_query}],
                                    timeout=60,
                                )
                                response_text = epistemic_tagger.strip_tags(resp.choices[0].message.content)
                            except Exception:
                                response_text = "I had a temporary issue processing that request."

                        words = response_text.split()
                        for i, word in enumerate(words):
                            await ws.send_json({
                                'type': 'stream_token',
                                'token': word + ' ',
                                'complete': i == len(words) - 1,
                                'privacy_tier': tier.value,
                                'model': model,
                                'intent': current_intent,
                            })

                        await ws.send_json({
                            'type': 'tier_status',
                            'tier': f'Tier {tier.value}',
                            'status': 'completed'
                        })
                    elif msg_type == 'ping':
                        await ws.send_json({'type': 'pong'})
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f'[WS Chat] Error: {e}')
        try:
            await ws.close()
        except:
            pass


# ==============================================
#  ROUTES — WEB INTELLIGENCE
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

@app.post("/browse")
async def browser_agent(req: dict, user: User = Depends(verify_token)):
    """
    Upgraded browser agent endpoint using browser-use.
    """
    instruction = req.get('instruction', req.get('task', ''))
    if not instruction:
        raise HTTPException(400, "instruction is required")
    
    from tools.browser_tool import JarvisBrowser
    browser = JarvisBrowser()
    
    result = await browser.execute(instruction)
    return result


# ==============================================
#  ROUTES — COMPUTER CONTROL
# ==============================================
@app.post("/computer")
async def computer_control(req: dict, user: User = Depends(verify_token)):
    from pc_agent.computer_agent import computer_agent
    instruction = req.get("instruction", "")
    if not instruction:
        raise HTTPException(400, "Instruction is required")
    
    confirm = req.get("confirm", True)
    result = computer_agent.execute_natural_language(instruction, confirm=confirm)
    return result

# ==============================================
#  ROUTES — EXECUTIONS
# ==============================================
@app.get("/executions/recent")
async def get_recent_executions(n: int = 10):
    from autonomy.l3_executor.executor_layer import ExecutorLayer
    layer = ExecutorLayer()
    return {"executions": layer.recent(n)}


# ==============================================
#  RUN
# ==============================================
if __name__ == "__main__":
    import uvicorn
    print(f"\n[JARVIS] Server starting at http://{HOST}:{PORT}")
    print(f"[JARVIS] API docs at  http://localhost:{PORT}/docs\n")
    uvicorn.run("core.main:app", host=HOST, port=PORT, reload=True, log_level="info")
