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
import logging
import os
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import verify_token
from ..database import User, get_db
from ..schemas import BrowserActionRequest, MessageRequest, NoteCreate, NoteUpdate, ReminderCreate

logger = logging.getLogger("jarvis")

router = APIRouter(tags=["Operations"])


def _get_config(key: str) -> str:
    from core.config_registry import config as _c
    return _c.get(key)


@router.get("/health")
async def health(request: Request):
    from sqlalchemy import text

    from ..database import AsyncSessionLocal
    db_connected = False
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
            db_connected = True
    except Exception as e:
        logger.warning("[core.routes.operations] handle_operation failed: %s", e)

    resource = getattr(request.app.state, "resource_monitor", None)
    services = getattr(request.app.state, "service_health", None)

    if resource and services:
        snap = resource.snapshot()
        svc = services.latest()
        overall = (
            snap.is_healthy
            and svc.ollama.status == "healthy"
            and db_connected
        )
        return {
            "status": "healthy" if overall else "degraded",
            "version": "0.1.0",
        }

    return {
        "status": "unknown",
        "version": "0.1.0",
    }


@router.post("/api/chat")
async def chat_endpoint(body: dict = {}):
    from core.intent_router import extract_intent
    from core.llm_router import get_router
    from core.model_router import route_request

    text = body.get("text") or body.get("message", "")
    if not text:
        raise HTTPException(400, "text or message field is required")

    model, tier, processed_query = route_request(text)
    intent_data = await extract_intent(processed_query)
    current_intent = intent_data.get("intent", "chat")
    model_group = "cloud" if model == "cloud" else "local"

    try:
        resp = await get_router().acompletion(
            model=model_group,
            messages=[{"role": "system", "content": "You are JARVIS, your AI assistant. Be concise."},
                      {"role": "user", "content": processed_query}],
            timeout=60,
        )
        response_text = resp.choices[0].message.content
    except Exception as e:
        logger.exception("[REST Chat] LLM failed: %s", e)
        response_text = "I had a temporary issue processing that request."

    return {"response": response_text, "model": model, "intent": current_intent}


@router.get("/metrics")
async def metrics_endpoint():
    from ..observability.metrics import collect_metrics
    return collect_metrics()


@router.get("/api/system/stats")
async def system_stats():
    import psutil
    mem = psutil.virtual_memory()
    cpu_percent = psutil.cpu_percent(interval=None)
    cpu_count = psutil.cpu_count()
    disk = psutil.disk_usage("/")
    net = psutil.net_io_counters()
    return {
        "cpu": {"percent": cpu_percent, "count": cpu_count},
        "memory": {"total": mem.total, "available": mem.available, "percent": mem.percent},
        "disk": {"total": disk.total, "free": disk.free, "percent": disk.percent},
        "network": {"bytes_sent": net.bytes_sent, "bytes_recv": net.bytes_recv},
        "timestamp": __import__("time").time(),
    }


# ── STT Providers ─────────────────────────────────────────────────

@router.get("/api/stt/providers")
async def stt_list_providers():
    from assistant.stt import init_stt_providers
    from assistant.stt_protocol import stt_registry
    if not stt_registry.list():
        init_stt_providers()
    return {"providers": stt_registry.list(), "default": stt_registry.default}


# ── Plugins ────────────────────────────────────────────────────────

@router.get("/api/plugins")
async def list_plugins(request: Request):
    registry = getattr(request.app.state, "plugin_registry", None)
    if not registry:
        return {"plugins": [], "total": 0}
    plugins = []
    for name, plugin in registry.plugins.items():
        try:
            health = await plugin.health_check()
        except Exception as e:
            logger.warning("[core.routes.operations] plugin health check failed: %s", e)
            health = {"healthy": False}
        plugins.append({
            "name": name,
            "version": plugin.manifest.version,
            "description": plugin.manifest.description,
            "hooks": plugin.manifest.hooks,
            "health": health,
        })
    return {"plugins": plugins, "total": registry.count}


# ── Skills ─────────────────────────────────────────────────────────

@router.get("/api/skills")
async def skills_list(request: Request):
    sm = getattr(request.app.state, "skill_manager", None)
    if not sm:
        return {"skills": []}
    return {"skills": sm.list()}


# ── Security Audit ─────────────────────────────────────────────────

@router.post("/api/security/audit")
async def security_run_audit():
    from ..security_audit import security_auditor
    report = await security_auditor.run_full_audit()
    return report


# ── Media Generation ───────────────────────────────────────────────

@router.post("/api/media/generate/image")
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


# ── Commitments ────────────────────────────────────────────────────

@router.get("/api/commitments")
async def commitments_list(request: Request, status: str | None = None):
    cs2 = getattr(request.app.state, "commitment_store", None)
    if not cs2:
        return {"commitments": []}
    return {"commitments": cs2.list(user_id="", status=status)}


class CommitmentAddRequest(BaseModel):
    description: str = ""
    due: str | None = None
    priority: str = "medium"
    source: str = "api"


@router.post("/api/commitments")
async def commitments_add(request: Request, body: CommitmentAddRequest):
    cs2 = getattr(request.app.state, "commitment_store", None)
    if not cs2:
        raise HTTPException(503, "Commitment tracker not available")
    cmt = cs2.add(
        user_id="",
        description=body.description,
        due_at=body.due,
        priority=body.priority,
        source_id=body.source,
    )
    return cmt


@router.post("/api/commitments/{cmt_id}/complete")
async def commitments_complete(request: Request, cmt_id: str):
    cs2 = getattr(request.app.state, "commitment_store", None)
    if not cs2:
        raise HTTPException(503, "Commitment tracker not available")
    ok = cs2.complete(cmt_id)
    return {"success": ok}


@router.post("/api/commitments/{cmt_id}/dismiss")
async def commitments_dismiss(request: Request, cmt_id: str):
    cs2 = getattr(request.app.state, "commitment_store", None)
    if not cs2:
        raise HTTPException(503, "Commitment tracker not available")
    ok = cs2.dismiss(cmt_id)
    return {"success": ok}


# ── Channels ───────────────────────────────────────────────────────

@router.get("/api/channels")
async def list_channels(request: Request):
    controller = getattr(request.app.state, "channel_controller", None)
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


@router.post("/api/channels/send")
async def channel_send(
    request: Request,
    req: MessageRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_token),
):
    controller = getattr(request.app.state, "channel_controller", None)
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


# ── Messaging Automation ──────────────────────────────────────────

@router.post("/api/message/send")
async def send_message(
    request: Request,
    req: MessageRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_token),
):
    from notes.activity_tracker import activity_tracker

    controller = getattr(request.app.state, "channel_controller", None)
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


# ── Content: Reminders, Notes, Activity ────────────────────────────

@router.get("/api/reminders")
async def list_reminders(db: AsyncSession = Depends(get_db), user: User = Depends(verify_token)):
    from reminders.manager import get_user_reminders
    items = await get_user_reminders(db, user)
    return [{"id": r.id, "title": r.title, "remind_at": r.remind_at, "repeat": r.repeat, "description": r.description} for r in items]


@router.post("/api/reminders")
async def create_reminder_route(
    req: ReminderCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_token),
):
    from reminders.manager import create_reminder
    r = await create_reminder(db, user, req.title, req.remind_at, req.description, req.repeat)
    return {"id": r.id, "title": r.title, "remind_at": r.remind_at}


@router.delete("/api/reminders/{reminder_id}")
async def delete_reminder_route(
    reminder_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_token),
):
    from reminders.manager import delete_reminder
    success = await delete_reminder(db, user, reminder_id)
    if not success:
        raise HTTPException(404, "Reminder not found")
    return {"deleted": True}


@router.get("/api/notes")
async def list_notes(db: AsyncSession = Depends(get_db), user: User = Depends(verify_token)):
    from notes.activity_tracker import notes_manager
    items = await notes_manager.get_all(db, user)
    return [{"id": n.id, "title": n.title, "content": n.content, "tags": n.tags, "updated_at": n.updated_at} for n in items]


@router.post("/api/notes")
async def create_note(req: NoteCreate, db: AsyncSession = Depends(get_db), user: User = Depends(verify_token)):
    from notes.activity_tracker import notes_manager
    n = await notes_manager.create(db, user, req.title, req.content, req.tags)
    return {"id": n.id, "title": n.title}


@router.put("/api/notes/{note_id}")
async def update_note(note_id: int, req: NoteUpdate, db: AsyncSession = Depends(get_db), user: User = Depends(verify_token)):
    from notes.activity_tracker import notes_manager
    n = await notes_manager.update(db, user, note_id, req.title, req.content)
    if not n:
        raise HTTPException(404, "Note not found")
    return {"id": n.id, "title": n.title}


@router.delete("/api/notes/{note_id}")
async def delete_note(note_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(verify_token)):
    from notes.activity_tracker import notes_manager
    success = await notes_manager.delete(db, user, note_id)
    if not success:
        raise HTTPException(404, "Note not found")
    return {"deleted": True}


@router.get("/api/activity/today")
async def today_activity(db: AsyncSession = Depends(get_db), user: User = Depends(verify_token)):
    from notes.activity_tracker import activity_tracker
    items = await activity_tracker.get_today(db, user.id)
    return [{"type": a.activity_type, "description": a.description, "ts": a.timestamp} for a in items]


@router.get("/api/activity/summary")
async def daily_summary(db: AsyncSession = Depends(get_db), user: User = Depends(verify_token)):
    from notes.activity_tracker import summary_generator
    summary = await summary_generator.generate(db, user)
    return {
        "date": summary.date,
        "summary": summary.summary,
        "productivity_score": summary.productivity_score,
        "data": summary.raw_data,
    }


# ── Media Player ────────────────────────────────────────────────────

@router.get("/api/media/status")
async def media_status():
    from media.player import media_player
    return media_player.get_status()


@router.post("/api/media/play")
async def media_play(track_index: int | None = None, query: str | None = None):
    from media.player import media_player
    if query:
        found = media_player.play_by_name(query)
        return {"playing": found}
    elif track_index is not None:
        media_player.play_by_index(track_index)
    else:
        media_player.play()
    return {"playing": True}


@router.post("/api/media/pause")
async def media_pause():
    from media.player import media_player
    media_player.pause()
    return {"paused": True}


@router.post("/api/media/next")
async def media_next():
    from media.player import media_player
    media_player.next_track()
    return media_player.get_status()


@router.post("/api/media/prev")
async def media_prev():
    from media.player import media_player
    media_player.prev_track()
    return media_player.get_status()


@router.post("/api/media/volume/{volume}")
async def set_volume(volume: int):
    from media.player import media_player
    media_player.set_volume(volume)
    return {"volume": volume}


@router.get("/api/media/playlist")
async def get_playlist():
    from media.player import media_player
    return media_player.get_playlist()


@router.get("/api/media/suggest/{mood}")
async def suggest_music(mood: str):
    from media.player import media_player, music_suggester
    status = media_player.get_status()
    if mood == "similar" and status.get("track"):
        return music_suggester.suggest_similar(status["track"])
    return music_suggester.suggest_by_mood(mood)


# ── Showcase & Highlights ─────────────────────────────────────────


@router.get("/api/monthly-highlights")
async def monthly_highlights():
    now = datetime.now()
    month_name = now.strftime("%B %Y")

    from sqlalchemy import and_, func, select

    from core.database import ChatHistory, ExecutionLog, get_db

    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    conversations = 0
    commands_executed = 0
    searches = 0
    reminders = 0

    try:
        async for session in get_db():
            from sqlalchemy import and_, func, select

            from core.database import ChatHistory, ExecutionLog
            q_conv = select(func.count(func.distinct(ChatHistory.session_id))).where(ChatHistory.timestamp >= start_of_month)
            conversations = (await session.execute(q_conv)).scalar() or 0

            q_cmd = select(func.count(ExecutionLog.id)).where(ExecutionLog.created_at >= start_of_month)
            commands_executed = (await session.execute(q_cmd)).scalar() or 0

            q_search = select(func.count(ChatHistory.id)).where(
                and_(ChatHistory.timestamp >= start_of_month, ChatHistory.intent == "web_search")
            )
            searches = (await session.execute(q_search)).scalar() or 0

            from reminders.manager import count_reminders
            reminders = await count_reminders(session)
            break
    except Exception as e:
        logger.exception("[Stats] Failed to count highlights: %s", e)

    return {
        "month": month_name,
        "conversations": conversations,
        "commands_executed": commands_executed,
        "searches": searches,
        "reminders": reminders,
        "top_models": [
            os.getenv("CHAT_MODEL") or _get_config("llm.chat_model"),
            os.getenv("CODE_MODEL") or _get_config("llm.code_model"),
            os.getenv("VISION_MODEL") or _get_config("llm.vision_model"),
        ],
        "highlights": [
            "13 AI models running across 9 Ollama ports",
            "6 autonomous agents for diverse tasks",
            "54K+ lines of Python and TypeScript",
            "100% local privacy \u2014 zero cloud dependency",
        ],
    }


# ── File Manager ──────────────────────────────────────────────────

@router.get("/api/files")
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
                "name": entry.name,
                "is_dir": entry.is_dir(),
                "size": entry.stat().st_size if entry.is_file() else 0,
                "modified": datetime.fromtimestamp(entry.stat().st_mtime).isoformat(),
            })
        except PermissionError:
            raise HTTPException(403, "Permission denied for this path")

    return {"path": resolved, "entries": sorted(entries, key=lambda x: (not x["is_dir"], x["name"]))}


@router.post("/api/files/upload")
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


# ── Browser Action ─────────────────────────────────────────────────

@router.post("/api/browser")
async def browser_action(
    req: BrowserActionRequest,
    user: User = Depends(verify_token),
):
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


# ── Generate UI ────────────────────────────────────────────────────

class GenUIRequest(BaseModel):
    message: str = ""
    context: str | None = None
    session_id: str | None = None


@router.post("/api/generate-ui")
async def generate_ui(
    req: GenUIRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_token),
):
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


# ── Dashboard Stats ────────────────────────────────────────────────

@router.get("/api/stats")
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
            "chat": os.getenv("CHAT_MODEL") or _get_config("llm.chat_model"),
            "code": os.getenv("CODE_MODEL") or _get_config("llm.code_model"),
            "vision": os.getenv("VISION_MODEL") or _get_config("llm.vision_model"),
        },
    }


def _get_gpu_stats() -> tuple[str, int]:
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


# ── Face Recognition ──────────────────────────────────────────────

@router.get("/api/faces")
async def list_faces(db: AsyncSession = Depends(get_db), user: User = Depends(verify_token)):
    from sqlalchemy import select

    from core.database import KnownFace
    result = await db.execute(select(KnownFace).where(KnownFace.owner_id == user.id))
    faces = result.scalars().all()
    return [{"id": f.id, "name": f.person_name, "relation": f.relation, "access_level": f.access_level, "image_count": f.image_count} for f in faces]


@router.post("/api/faces/register")
async def register_face(
    person_name: str = Form(...),
    relation: str = Form("unknown"),
    info: str = Form(""),
    access_level: str = Form("visitor"),
    images: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_token),
):
    try:
        import cv2
        import numpy as np
    except ImportError:
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


@router.post("/api/faces/identify")
async def identify_face(
    image: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_token),
):
    try:
        import cv2
        import numpy as np
    except ImportError:
        raise HTTPException(503, "numpy or opencv not installed (pip install numpy opencv-python)")
    from vision.face_recognition import face_recognizer
    data = await image.read()
    nparr = np.frombuffer(data, np.uint8)
    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    result = await face_recognizer.identify_and_lookup(db, user, frame)
    return result
