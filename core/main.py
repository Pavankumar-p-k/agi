"""
core/main.py — JARVIS FastAPI server: all routes + WebSocket + startup
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional, List

from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
import base64
import httpx
import webbrowser
import subprocess
import json
import re
import urllib.parse

from .config import HOST, PORT, ALLOWED_ORIGINS
from .database import get_db, init_db, User
from .auth import verify_token, init_firebase

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

            asyncio.create_task(hybrid_manager._warmup_models())
            print("  [HYBRID] Hybrid Automation System ready [OK]")
        else:
            print("  [HYBRID] Skipping hybrid automation init because autonomy layer failed.")
    except Exception as e:
        startup_status["warnings"].append(f"hybrid: {e}")
        print(f"  [WARNING] Hybrid automation init failed: {e}")

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

    # Start WakeWordDetector
    try:
        from assistant.wake_word import wake_word_detector
        from assistant.engine import jarvis
        
        def on_wake():
            print("[EVENT] Wake word detected!")
            # Trigger something or just log
        
        wake_word_detector.start(on_wake)
        print("  [VOICE] Wake word detector started [OK]")
    except Exception as e:
        print(f"  [WARNING] Wake word detector failed: {e}")

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


# ==============================================
#  PYDANTIC SCHEMAS
# ==============================================
class ChatRequest(BaseModel):
    message: str
    context: Optional[str] = ""

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
    return {
        "status": "online",
        "system": "JARVIS",
        "version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat()
    }

@app.get("/health")
async def health():
    from assistant.stt import get_stt
    from assistant.tts import get_tts
    from core.database import get_db
    
    stt_loaded = False
    try:
        stt_loaded = get_stt().model is not None
    except: pass
    
    tts_loaded = False
    try:
        tts_loaded = get_tts().pipeline is not None
    except: pass
    
    ollama_ready = False
    try:
        import requests
        resp = requests.get("http://localhost:11434/api/tags", timeout=1)
        ollama_ready = resp.status_code == 200
    except: pass

    db_connected = False
    try:
        # Simple check for DB file existence or a quick query
        import os
        db_connected = os.path.exists("data/jarvis.db")
    except: pass

    return {
        "ollama": ollama_ready,
        "stt_loaded": stt_loaded,
        "tts_loaded": tts_loaded,
        "db_connected": db_connected,
        "timestamp": datetime.utcnow().isoformat()
    }


# ==============================================
#  LLM INTENT EXTRACTION + ACTION EXECUTOR
# ==============================================

INTENT_SYSTEM_PROMPT = """Classify the user message into one of these intents. Return ONLY valid JSON with no other text.

intents:
- open_app: user wants to open a website or URL
- media_play: user wants to play music, video, or media
- web_search: user wants to search the web
- reminder: user wants to set a reminder or alert
- pc_control: user wants to open a desktop application
- chat: anything else

JSON format: {"intent":"intent_name","action":"...","target":"...","parameters":{}}
"""


async def extract_intent(message: str) -> dict:
    try:
        examples = """
Examples:
USER: opn yt
AI: {"intent":"open_app","action":"open","target":"youtube","parameters":{}}

USER: play beat it by michael jackson
AI: {"intent":"media_play","action":"play","target":"beat it by michael jackson","parameters":{}}

USER: search latest AI news
AI: {"intent":"web_search","action":"search","target":"latest AI news","parameters":{}}

USER: open notepad
AI: {"intent":"pc_control","action":"open_app","target":"notepad","parameters":{}}

USER: remind me to drink water in 1 minute
AI: {"intent":"reminder","action":"create","target":"drink water","parameters":{"time":"in 1 minute"}}

USER: what is python
AI: {"intent":"chat","action":"answer","target":"python explanation","parameters":{}}
"""
        payload = {
            "model": "qwen3:4b",
            "messages": [
                {"role": "system", "content": INTENT_SYSTEM_PROMPT},
                {"role": "user", "content": f"{examples}\n\nClassify this message (return ONLY valid JSON):\n{message}"}
            ],
            "stream": False
        }
        r = httpx.post("http://localhost:11434/api/chat", json=payload, timeout=30)
        content = r.json()["message"]["content"]
        content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
        parsed = json.loads(content)
        intent = parsed.get("intent", "chat")
        if intent not in ("open_app", "media_play", "web_search", "reminder", "pc_control", "chat"):
            intent = "chat"
        parsed["intent"] = intent
        return parsed
    except Exception:
        return {"intent": "chat", "action": "answer", "target": message}


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


def build_ollama_llm(messages: list, timeout: int = 60) -> str:
    available_models = ["qwen3:4b", "qwen2.5-coder:3b", "mistral:latest"]
    chat_model = "qwen3:4b"
    try:
        r = httpx.get("http://localhost:11434/api/tags", timeout=2)
        if r.status_code == 200:
            installed = [m["name"] for m in r.json().get("models", [])]
            for candidate in available_models:
                if candidate in installed or candidate.replace(":latest", "") in [x.replace(":latest", "") for x in installed]:
                    chat_model = candidate
                    break
    except Exception:
        pass
    payload = {"model": chat_model, "messages": messages, "stream": False}
    resp = httpx.post("http://localhost:11434/api/chat", json=payload, timeout=timeout)
    resp.raise_for_status()
    return resp.json()["message"]["content"]


async def execute_action(intent_data: dict, db=None, user=None) -> dict:
    intent = intent_data.get("intent")
    target = intent_data.get("target", "")
    action = intent_data.get("action", "")

    url_map = {
        "youtube": "https://youtube.com",
        "google": "https://google.com",
        "whatsapp": "https://web.whatsapp.com",
        "amazon": "https://amazon.com",
        "gmail": "https://gmail.com",
        "netflix": "https://netflix.com",
        "spotify": "https://open.spotify.com",
        "github": "https://github.com",
        "twitter": "https://twitter.com",
        "instagram": "https://instagram.com",
        "facebook": "https://facebook.com",
        "reddit": "https://reddit.com",
        "linkedin": "https://linkedin.com",
    }
    pc_apps = {
        "notepad": "notepad.exe",
        "calculator": "calc.exe",
        "explorer": "explorer.exe",
        "vscode": "code",
        "cmd": "cmd.exe",
        "chrome": "chrome.exe",
        "edge": "msedge.exe",
        "firefox": "firefox.exe",
    }

    if intent == "open_app":
        for app, url in url_map.items():
            if app in target.lower():
                webbrowser.open(url)
                return {"executed": True, "action": f"Opened {app}", "url": url}
        webbrowser.open(f"https://google.com/search?q={urllib.parse.quote(target)}")
        return {"executed": True, "action": f"Searched for {target}"}

    elif intent == "media_play":
        query = urllib.parse.quote(target)
        url = f"https://www.youtube.com/results?search_query={query}"
        webbrowser.open(url)
        return {"executed": True, "action": f"Opened YouTube search for: {target}", "url": url}

    elif intent == "web_search":
        query = urllib.parse.quote(target)
        try:
            r = httpx.get(
                f"https://api.duckduckgo.com/?q={query}&format=json&no_html=1",
                timeout=10
            )
            data = r.json()
            results = []
            for item in data.get("RelatedTopics", [])[:5]:
                if "Text" in item and "FirstURL" in item:
                    results.append({"title": item["Text"][:200], "url": item["FirstURL"]})
            return {"executed": True, "search_results": results}
        except Exception as e:
            return {"executed": True, "action": f"Web search for {target} opened in browser", "url": f"https://duckduckgo.com/?q={query}"}

    elif intent == "reminder":
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

    elif intent == "pc_control":
        for app, exe in pc_apps.items():
            if app in target.lower():
                try:
                    subprocess.Popen([exe])
                    return {"executed": True, "action": f"Launched {app}"}
                except Exception as e:
                    return {"executed": False, "error": str(e)}
        return {"executed": False, "error": f"Unknown app: {target}"}

    else:
        return {"executed": False, "action": "chat_only"}


# ==============================================
#  ROUTES — ASSISTANT
# ==============================================
@app.post("/api/chat")
async def chat(
    req: ChatRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_token)
):
    from core.database import ChatHistory

    # Step 1: Check Ollama connectivity
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

    # Step 2: Extract intent using LLM
    intent_data = await extract_intent(req.message)

    # Step 3: Execute real action if needed
    action_result = await execute_action(intent_data, db=db, user=user)

    # Step 4: Build action context for LLM
    action_context = ""
    if action_result.get("executed") and intent_data["intent"] != "chat":
        action_context = f"\n[SYSTEM: Action executed: {json.dumps(action_result)}]"

    # Step 5: Get real Ollama response with action awareness
    try:
        reply = build_ollama_llm([
            {"role": "system", "content": (
                "You are JARVIS, a personal AI assistant. "
                "Be concise and direct. "
                "If an action was executed, confirm it naturally. "
                "Never say you cannot do things you just did."
            ) + action_context},
            {"role": "user", "content": req.message}
        ])
    except Exception as e:
        reply = ""
        if action_result.get("executed"):
            reply = f"Action completed: {action_result.get('action', '')}"
        else:
            reply = f"Model error: {e}"

    # Step 6: Build response
    result = {
        "response": reply,
        "intent": intent_data,
        "action": action_result,
        "model": "qwen3:4b",
    }

    db.add(ChatHistory(user_id=user.id, role="user", message=req.message))
    db.add(ChatHistory(user_id=user.id, role="assistant", message=result["response"]))
    await db.commit()

    from notes.activity_tracker import activity_tracker
    await activity_tracker.log(db, user.id, "voice_command", f"Chat: {req.message[:100]}")

    return result


@app.get("/api/chat/history")
async def get_chat_history(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_token),
    limit: int = 50
):
    from sqlalchemy import select
    from core.database import ChatHistory
    result = await db.execute(
        select(ChatHistory)
        .where(ChatHistory.user_id == user.id)
        .order_by(ChatHistory.timestamp.desc())
        .limit(limit)
    )
    messages = result.scalars().all()
    return [{"role": m.role, "message": m.message, "ts": m.timestamp} for m in reversed(messages)]


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
#  ROUTES — VOICE (STT/TTS)
# ==============================================
from assistant.stt import get_stt
from assistant.tts import get_tts

@app.post("/stt")
async def speech_to_text(file: UploadFile = File(...), user: User = Depends(verify_token)):
    audio_data = await file.read()
    text = get_stt().transcribe(audio_data)
    if not text:
        raise HTTPException(500, "Transcription failed")
    return {"transcript": text}

@app.post("/tts")
async def text_to_speech(req: dict):
    text = req.get("text", "")
    if not text:
        raise HTTPException(400, "Text is required")
    
    audio_bytes = get_tts().synthesize(text)
    if not audio_bytes:
        raise HTTPException(500, "TTS generation failed")
    
    from fastapi.responses import Response
    return Response(content=audio_bytes, media_type="audio/wav")

@app.get("/tts/stream")
async def tts_stream_websocket(ws: WebSocket):
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
    from core.model_router import route_request
    
    await ws.accept()
    try:
        while True:
            raw = await ws.receive_text()
            import json
            msg = json.loads(raw)
            msg_type = msg.get('type')
            
            if msg_type == 'chat':
                text = msg.get('text', '')
                model, tier, processed_query = route_request(text)
                
                # Stream tokens from assistant
                from assistant.engine import jarvis
                result = await jarvis.process_text(processed_query, user_id=1)
                
                response_text = result.get('response', '')
                
                # Send tokens one word at a time for streaming effect
                words = response_text.split()
                for i, word in enumerate(words):
                    await ws.send_json({
                        'type': 'stream_token',
                        'token': word + ' ',
                        'complete': i == len(words) - 1,
                        'privacy_tier': tier.value,
                        'model': model,
                    })
                
                await ws.send_json({
                    'type': 'tier_status',
                    'tier': f'Tier {tier.value}',
                })
            elif msg_type == 'ping':
                await ws.send_json({'type': 'pong'})
    except Exception as e:
        print(f'[WS Chat] Error: {e}')
        await ws.close()


# ==============================================
#  ROUTES — WEB INTELLIGENCE
# ==============================================
from tools.search_tool import search_engine, decision_gate

@app.post("/search")
async def search_route(req: dict, user: User = Depends(verify_token)):
    query = req.get("query", "")
    if not query:
        raise HTTPException(400, "Query is required")
    
    # Check decision gate
    should_search = decision_gate.should_search(query, req.get("confidence", 1.0))
    if not should_search and not req.get("force", False):
        return {"searched": False, "reason": "Decision gate rejected search"}
    
    results = search_engine.search(query)
    scraped = search_engine.scrape_top(results)
    
    return {
        "searched": True,
        "results": [vars(r) for r in results],
        "context": scraped
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
from pc_agent.computer_agent import computer_agent

@app.post("/computer")
async def computer_control(req: dict, user: User = Depends(verify_token)):
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
