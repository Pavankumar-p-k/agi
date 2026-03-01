from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime
from typing import List, Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from automation.routes import router as automation_router
from brain.api import router as brain_router
from core.auth import init_firebase, verify_token
from core.config import ALLOWED_ORIGINS, HOST, PORT
from core.database import ChatHistory, KnownFace, User, get_db, init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    print('=' * 50)
    print('  JARVIS - Starting up...')
    print('=' * 50)

    await init_db()
    init_firebase()

    from reminders.manager import reminder_manager

    await reminder_manager.load_and_schedule_all()

    from assistant.engine import jarvis

    reminder_manager.inject_tts(jarvis.tts)
    try:
        from automation.workflow_engine import workflow_engine

        await workflow_engine.start()
    except Exception as exc:
        print(f"[Automation] Workflow engine startup skipped: {exc}")

    try:
        from brain.orchestrator import get_brain

        await get_brain().startup()
    except Exception as exc:
        print(f"[Brain] Startup skipped: {exc}")

    print('[JARVIS] All systems online')
    yield

    from automation.messaging import messaging
    from reminders.manager import reminder_manager

    reminder_manager.shutdown()
    messaging.shutdown()
    try:
        from automation.workflow_engine import workflow_engine

        await workflow_engine.stop()
    except Exception as exc:
        print(f"[Automation] Workflow engine shutdown skipped: {exc}")
    try:
        from brain.orchestrator import get_brain

        await get_brain().shutdown()
    except Exception as exc:
        print(f"[Brain] Shutdown skipped: {exc}")
    print('[JARVIS] Shutdown complete.')


app = FastAPI(
    title='JARVIS API',
    description='Personal AI Life Operating System',
    version='1.0.0',
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)
app.include_router(automation_router)
app.include_router(brain_router)


class ChatRequest(BaseModel):
    message: str
    context: Optional[str] = ''


class ReminderCreate(BaseModel):
    title: str
    remind_at: datetime
    description: Optional[str] = ''
    repeat: Optional[str] = 'none'


class NoteCreate(BaseModel):
    title: str
    content: str
    tags: Optional[str] = ''


class NoteUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None


class MessageRequest(BaseModel):
    platform: str
    recipient: str
    message: str


class TaskCompleteRequest(BaseModel):
    reminder_id: int
    notify_platform: Optional[str] = None
    notify_recipient: Optional[str] = None
    notify_message: Optional[str] = None


@app.get('/')
async def root():
    return {
        'status': 'online',
        'system': 'JARVIS',
        'version': '1.0.0',
        'timestamp': datetime.utcnow().isoformat(),
    }


@app.get('/health')
async def health():
    from assistant.engine import jarvis

    return {
        'api': 'ok',
        'llm_available': jarvis.llm.is_available(),
        'timestamp': datetime.utcnow().isoformat(),
    }


@app.post('/api/chat')
async def chat(req: ChatRequest, db: AsyncSession = Depends(get_db), user: User = Depends(verify_token)):
    from assistant.engine import jarvis
    from automation.pc_automation import execute_command
    from notes.activity_tracker import activity_tracker

    # Tolerate list bullets or leading punctuation from user input:
    # "- send whatsapp to Rahul saying hello"
    raw_message = req.message.strip()
    message = raw_message.lstrip("-*• ").strip()

    # Try automation first; fallback to LLM only when no automation match exists.
    automation_result = execute_command(message)
    if automation_result.get('action') not in ('unknown', 'none'):
        result = {
            'response': str(automation_result.get('speech') or 'Done'),
            'intent': 'automation',
            'automation': automation_result,
            'user_id': user.id,
            'timestamp': datetime.utcnow().isoformat(),
        }
    else:
        result = await jarvis.process_text(message, user.id, context=req.context or '')

    db.add(ChatHistory(user_id=user.id, role='user', message=message))
    db.add(ChatHistory(user_id=user.id, role='assistant', message=result['response']))
    await db.commit()

    await activity_tracker.log(db, user.id, 'voice_command', f"Chat: {message[:100]}")
    return result


@app.get('/api/chat/history')
async def get_chat_history(
    db: AsyncSession = Depends(get_db), user: User = Depends(verify_token), limit: int = 50
):
    result = await db.execute(
        select(ChatHistory)
        .where(ChatHistory.user_id == user.id)
        .order_by(ChatHistory.timestamp.desc())
        .limit(limit)
    )
    messages = result.scalars().all()
    return [{'role': m.role, 'message': m.message, 'ts': m.timestamp} for m in reversed(messages)]


@app.get('/api/reminders')
async def list_reminders(db: AsyncSession = Depends(get_db), user: User = Depends(verify_token)):
    from reminders.manager import get_user_reminders

    items = await get_user_reminders(db, user)
    return [
        {
            'id': r.id,
            'title': r.title,
            'remind_at': r.remind_at,
            'repeat': r.repeat,
            'description': r.description,
            'is_done': r.is_done,
        }
        for r in items
    ]


@app.post('/api/reminders')
async def create_reminder_route(
    req: ReminderCreate, db: AsyncSession = Depends(get_db), user: User = Depends(verify_token)
):
    from reminders.manager import create_reminder

    reminder = await create_reminder(db, user, req.title, req.remind_at, req.description or '', req.repeat or 'none')
    return {
        'id': reminder.id,
        'title': reminder.title,
        'remind_at': reminder.remind_at,
        'repeat': reminder.repeat,
        'description': reminder.description,
        'is_done': reminder.is_done,
    }


@app.delete('/api/reminders/{reminder_id}')
async def delete_reminder_route(
    reminder_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(verify_token)
):
    from reminders.manager import delete_reminder

    success = await delete_reminder(db, user, reminder_id)
    if not success:
        raise HTTPException(404, 'Reminder not found')
    return {'deleted': True}


@app.post('/api/reminders/{reminder_id}/complete')
async def complete_reminder_route(
    reminder_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(verify_token)
):
    from reminders.manager import complete_reminder

    reminder = await complete_reminder(db, user, reminder_id)
    if not reminder:
        raise HTTPException(404, 'Reminder not found')

    return {
        'completed': True,
        'reminder': {
            'id': reminder.id,
            'title': reminder.title,
            'is_done': reminder.is_done,
            'remind_at': reminder.remind_at,
        },
    }


@app.get('/api/notes')
async def list_notes(db: AsyncSession = Depends(get_db), user: User = Depends(verify_token)):
    from notes.activity_tracker import notes_manager

    items = await notes_manager.get_all(db, user)
    return [{'id': n.id, 'title': n.title, 'content': n.content, 'tags': n.tags, 'updated_at': n.updated_at} for n in items]


@app.post('/api/notes')
async def create_note(req: NoteCreate, db: AsyncSession = Depends(get_db), user: User = Depends(verify_token)):
    from notes.activity_tracker import notes_manager

    note = await notes_manager.create(db, user, req.title, req.content, req.tags or '')
    return {
        'id': note.id,
        'title': note.title,
        'content': note.content,
        'tags': note.tags,
        'updated_at': note.updated_at,
    }


@app.put('/api/notes/{note_id}')
async def update_note(
    note_id: int, req: NoteUpdate, db: AsyncSession = Depends(get_db), user: User = Depends(verify_token)
):
    from notes.activity_tracker import notes_manager

    note = await notes_manager.update(db, user, note_id, req.title, req.content)
    if not note:
        raise HTTPException(404, 'Note not found')
    return {'id': note.id, 'title': note.title}


@app.delete('/api/notes/{note_id}')
async def delete_note(note_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(verify_token)):
    from notes.activity_tracker import notes_manager

    success = await notes_manager.delete(db, user, note_id)
    if not success:
        raise HTTPException(404, 'Note not found')
    return {'deleted': True}


@app.get('/api/activity/today')
async def today_activity(db: AsyncSession = Depends(get_db), user: User = Depends(verify_token)):
    from notes.activity_tracker import activity_tracker

    items = await activity_tracker.get_today(db, user.id)
    return [{'type': a.activity_type, 'description': a.description, 'ts': a.timestamp} for a in items]


@app.get('/api/activity/summary')
async def daily_summary(db: AsyncSession = Depends(get_db), user: User = Depends(verify_token)):
    from notes.activity_tracker import summary_generator

    summary = await summary_generator.generate(db, user)
    return {
        'date': summary.date,
        'summary': summary.summary,
        'productivity_score': summary.productivity_score,
        'data': summary.raw_data,
    }


@app.post('/api/message/send')
async def send_message(
    req: MessageRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_token),
):
    from automation.messaging import messaging
    from notes.activity_tracker import activity_tracker

    if req.platform == 'whatsapp':
        success = messaging.send_whatsapp(req.recipient, req.message)
    elif req.platform == 'instagram':
        success = messaging.send_instagram_dm(req.recipient, req.message)
    else:
        raise HTTPException(400, "Platform must be 'whatsapp' or 'instagram'")

    if success:
        await activity_tracker.log(db, user.id, 'message_sent', f'Sent {req.platform} message to {req.recipient}')
    return {
        'success': success,
        'platform': req.platform,
        'recipient': req.recipient,
        'error': '' if success else (messaging.last_error or 'Failed to send message'),
    }


@app.post('/api/tasks/complete')
async def complete_task(
    req: TaskCompleteRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_token),
):
    from automation.messaging import messaging
    from notes.activity_tracker import activity_tracker
    from reminders.manager import complete_reminder

    reminder = await complete_reminder(db, user, req.reminder_id)
    if not reminder:
        raise HTTPException(404, 'Reminder not found')

    notify_result = None
    if req.notify_platform and req.notify_recipient and req.notify_message:
        platform = req.notify_platform.strip().lower()
        if platform == 'whatsapp':
            sent = messaging.send_whatsapp(req.notify_recipient, req.notify_message)
        elif platform == 'instagram':
            sent = messaging.send_instagram_dm(req.notify_recipient, req.notify_message)
        else:
            raise HTTPException(400, "notify_platform must be 'whatsapp' or 'instagram'")

        notify_result = {
            'success': sent,
            'platform': platform,
            'recipient': req.notify_recipient,
            'error': '' if sent else (messaging.last_error or 'Failed to send message'),
        }
        if sent:
            await activity_tracker.log(
                db,
                user.id,
                'message_sent',
                f'Sent {platform} message to {req.notify_recipient}',
            )

    await activity_tracker.log(db, user.id, 'task_completed', f'Completed reminder #{reminder.id}: {reminder.title}')

    return {
        'completed': True,
        'reminder': {
            'id': reminder.id,
            'title': reminder.title,
            'is_done': reminder.is_done,
            'remind_at': reminder.remind_at,
        },
        'notification': notify_result,
    }


@app.post('/api/faces/register')
async def register_face(
    person_name: str = Form(...),
    relation: str = Form('unknown'),
    info: str = Form(''),
    access_level: str = Form('visitor'),
    images: List[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_token),
):
    from vision.face_recognition import face_recognizer

    payloads: list[bytes] = []
    for image in images:
        data = await image.read()
        if data:
            payloads.append(data)

    if not payloads:
        raise HTTPException(400, 'No valid images provided')

    face = await face_recognizer.register_face(db, user, person_name, payloads, relation, info, access_level)
    return {'id': face.id, 'person_name': face.person_name, 'image_count': face.image_count}


@app.post('/api/faces/identify')
async def identify_face(
    image: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_token),
):
    from vision.face_recognition import face_recognizer

    data = await image.read()
    return await face_recognizer.identify_and_lookup(db, user, data)


@app.get('/api/faces')
async def list_faces(db: AsyncSession = Depends(get_db), user: User = Depends(verify_token)):
    result = await db.execute(select(KnownFace).where(KnownFace.owner_id == user.id))
    faces = result.scalars().all()
    return [
        {
            'id': face.id,
            'name': face.person_name,
            'relation': face.relation,
            'access_level': face.access_level,
            'image_count': face.image_count,
        }
        for face in faces
    ]


@app.get('/api/media/status')
async def media_status():
    from media.player import media_player

    return media_player.get_status()


@app.post('/api/media/play')
async def media_play(track_index: Optional[int] = None, query: Optional[str] = None):
    from media.player import media_player

    if query:
        found = media_player.play_by_name(query)
        return {'playing': found}
    if track_index is not None:
        media_player.play_by_index(track_index)
    else:
        media_player.play()
    return {'playing': True}


@app.post('/api/media/pause')
async def media_pause():
    from media.player import media_player

    media_player.pause()
    return {'paused': True}


@app.post('/api/media/next')
async def media_next():
    from media.player import media_player

    media_player.next_track()
    return media_player.get_status()


@app.post('/api/media/volume/{volume}')
async def set_volume(volume: int):
    from media.player import media_player

    media_player.set_volume(volume)
    return {'volume': volume}


@app.get('/api/media/playlist')
async def get_playlist():
    from media.player import media_player

    return media_player.get_playlist()


@app.get('/api/media/suggest/{mood}')
async def suggest_music(mood: str):
    from media.player import media_player, music_suggester

    status = media_player.get_status()
    if mood == 'similar' and status.get('track'):
        return music_suggester.suggest_similar(status['track'])
    return music_suggester.suggest_by_mood(mood)


@app.get('/api/files')
async def list_files(path: str = '~', user: User = Depends(verify_token)):
    import os

    resolved = os.path.expanduser(path)
    if not os.path.exists(resolved):
        raise HTTPException(404, 'Path not found')
    if not os.path.isdir(resolved):
        raise HTTPException(400, 'Not a directory')

    entries = []
    for entry in os.scandir(resolved):
        try:
            stats = entry.stat()
            entries.append(
                {
                    'name': entry.name,
                    'is_dir': entry.is_dir(),
                    'size': stats.st_size if entry.is_file() else 0,
                    'modified': datetime.fromtimestamp(stats.st_mtime).isoformat(),
                }
            )
        except PermissionError:
            continue

    entries.sort(key=lambda item: (not item['is_dir'], item['name'].lower()))
    return {'path': resolved, 'entries': entries}


@app.post('/api/files/upload')
async def upload_file(path: str = Form(...), file: UploadFile = File(...), user: User = Depends(verify_token)):
    import os

    dest_dir = os.path.expanduser(path)
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, file.filename)
    data = await file.read()

    with open(dest, 'wb') as handle:
        handle.write(data)

    return {'saved_to': dest, 'size': len(data)}


@app.websocket('/ws/{device_id}/{user_id}')
async def websocket_endpoint(ws: WebSocket, device_id: str, user_id: int):
    from network.websocket_server import connection_manager, handle_message

    await connection_manager.connect(ws, device_id, user_id)
    try:
        await ws.send_json(
            {
                'type': 'connected',
                'payload': {
                    'device_id': device_id,
                    'user_id': user_id,
                    'server_time': datetime.utcnow().isoformat(),
                },
            }
        )
        while True:
            raw = await ws.receive_text()
            await handle_message(ws, device_id, user_id, raw)
    except WebSocketDisconnect:
        connection_manager.disconnect(device_id, user_id)


if __name__ == '__main__':
    import uvicorn

    print(f'\n[JARVIS] Server starting at http://{HOST}:{PORT}')
    print(f'[JARVIS] API docs at  http://localhost:{PORT}/docs\n')
    uvicorn.run('core.main:app', host=HOST, port=PORT, reload=False, log_level='info')
