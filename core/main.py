"""
core/main.py — JARVIS FastAPI server: all routes + WebSocket + startup
"""
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


# ══════════════════════════════════════════════
#  STARTUP / SHUTDOWN
# ══════════════════════════════════════════════
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
        print("  [AUTONOMY] Autonomous stack initialized ✓")
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
            print("  [HYBRID] Model fallback system ready ✓")

            asyncio.create_task(hybrid_manager._warmup_models())
            print("  [HYBRID] Hybrid Automation System ready ✓")
        else:
            print("  [HYBRID] Skipping hybrid automation init because autonomy layer failed.")
    except Exception as e:
        startup_status["warnings"].append(f"hybrid: {e}")
        print(f"  [WARNING] Hybrid automation init failed: {e}")

    # Verify Ollama models (wait for Ollama to be ready first)
    try:
        import asyncio
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
        print("  [VOICE] Wake word detector started ✓")
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


# ══════════════════════════════════════════════
#  APP
# ══════════════════════════════════════════════
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
    print("[Router] Hybrid Automation routes loaded ✓")
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


# ══════════════════════════════════════════════
#  PYDANTIC SCHEMAS
# ══════════════════════════════════════════════
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


# ══════════════════════════════════════════════
#  ROUTES — HEALTH
# ══════════════════════════════════════════════
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
    from assistant.engine import jarvis
    return {
        "api": "ok",
        "llm_available": jarvis.llm.is_available(),
        "autonomy": startup_status["autonomy"],
        "hybrid": startup_status["hybrid"],
        "warnings": startup_status["warnings"],
        "timestamp": datetime.utcnow().isoformat()
    }


# ══════════════════════════════════════════════
#  ROUTES — ASSISTANT
# ══════════════════════════════════════════════
@app.post("/api/chat")
async def chat(
    req: ChatRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_token)
):
    from assistant.engine import jarvis
    from core.database import ChatHistory
    from core.model_router import route_request
    
    # Route based on privacy tier
    model, tier, processed_query = route_request(req.message)
    
    result = await jarvis.process_text(processed_query, user.id)
    result['privacy_tier'] = tier.value
    result['model'] = model
    result['reason'] = f"Routed to {tier.value} based on content classification."

    # Save to history
    db.add(ChatHistory(user_id=user.id, role="user", message=req.message))
    db.add(ChatHistory(user_id=user.id, role="assistant", message=result["response"]))
    await db.commit()

    # Log activity
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


# ══════════════════════════════════════════════
#  ROUTES — REMINDERS
# ══════════════════════════════════════════════
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


# ══════════════════════════════════════════════
#  ROUTES — NOTES
# ══════════════════════════════════════════════
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


# ══════════════════════════════════════════════
#  ROUTES — ACTIVITY & SUMMARY
# ══════════════════════════════════════════════
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


# ══════════════════════════════════════════════
#  ROUTES — MESSAGING AUTOMATION
# ══════════════════════════════════════════════
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


# ══════════════════════════════════════════════
#  ROUTES — FACE RECOGNITION
# ══════════════════════════════════════════════
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


# ══════════════════════════════════════════════
#  ROUTES — MEDIA PLAYER
# ══════════════════════════════════════════════
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


# ══════════════════════════════════════════════
#  ROUTES — FILE MANAGER
# ══════════════════════════════════════════════
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


# ══════════════════════════════════════════════
#  ROUTES — VOICE (STT/TTS)
# ══════════════════════════════════════════════
from assistant.stt import stt
from assistant.tts import tts

@app.post("/stt")
async def speech_to_text(file: UploadFile = File(...), user: User = Depends(verify_token)):
    audio_data = await file.read()
    text = stt.transcribe(audio_data)
    if not text:
        raise HTTPException(500, "Transcription failed")
    return {"transcript": text}

@app.post("/tts")
async def text_to_speech(req: dict):
    text = req.get("text", "")
    if not text:
        raise HTTPException(400, "Text is required")
    
    audio_bytes = tts.synthesize(text)
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
                audio_bytes = tts.synthesize(text)
                await ws.send_bytes(audio_bytes)
    except Exception as e:
        print(f"[TTS Stream] Error: {e}")
        await ws.close()


# ══════════════════════════════════════════════
#  ROUTES — BROWSER AGENT
# ══════════════════════════════════════════════
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


# ══════════════════════════════════════════════
#  WEBSOCKET — CHAT STREAM (for real-time streaming AI responses)
# ══════════════════════════════════════════════
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


# ══════════════════════════════════════════════
#  ROUTES — WEB INTELLIGENCE
# ══════════════════════════════════════════════
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


# ══════════════════════════════════════════════
#  RUN
# ══════════════════════════════════════════════
if __name__ == "__main__":
    import uvicorn
    print(f"\n[JARVIS] Server starting at http://{HOST}:{PORT}")
    print(f"[JARVIS] API docs at  http://localhost:{PORT}/docs\n")
    uvicorn.run("core.main:app", host=HOST, port=PORT, reload=True, log_level="info")
