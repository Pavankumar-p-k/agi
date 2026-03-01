from __future__ import annotations

import asyncio
import csv
import io
import re
from typing import Any

from fastapi import APIRouter, Body

from automation.auto_reply import auto_reply_manager
from automation.mobile_data_store import mobile_data_store
from automation.pc_automation import (
    APP_MAP,
    SITE_MAP,
    browser,
    close_app,
    contacts_db,
    execute_command,
    ig,
    launch_app,
    supported_commands,
    sys_ctrl,
    wa,
)
from automation.messaging import messaging
from automation.workflow_engine import workflow_engine

router = APIRouter(prefix='/api/automation', tags=['automation'])


def _normalize_contact_name(value: str) -> str:
    return re.sub(r'\s+', ' ', str(value or '').strip().lower())


def _pick_field(row: dict[str, Any], *candidates: str) -> str:
    lowered = {str(k).strip().lower(): v for k, v in row.items()}
    for key in candidates:
        if key in lowered:
            return str(lowered.get(key, '') or '').strip()
    return ''


@router.post('/command')
async def run_command(body: dict[str, Any] = Body(...)):
    command = str(body.get('command', '')).strip()
    if not command:
        return {'success': False, 'speech': 'No command provided.'}
    result = execute_command(command)
    if result.get('action') not in ('unknown', 'none'):
        return result

    # Fallback to general assistant response so voice clients always get a spoken reply.
    try:
        from assistant.engine import jarvis

        reply = await asyncio.to_thread(jarvis.llm.chat, command, '')
        reply_text = str(reply or '').strip()
        if not reply_text:
            reply_text = "I heard you. Please try that again."
        return {
            'success': True,
            'action': 'chat_reply',
            'intent': 'general_chat',
            'speech': reply_text,
            'response': reply_text,
        }
    except Exception:
        return {
            'success': True,
            'action': 'chat_reply',
            'intent': 'general_chat',
            'speech': "I heard you. I can run automation commands or answer general questions.",
            'response': "I heard you. I can run automation commands or answer general questions.",
        }


@router.get('/capabilities')
async def capabilities():
    return {
        'apps': list(APP_MAP.keys()),
        'sites': list(SITE_MAP.keys()),
        'auto_reply': True,
        'workflow_automation': True,
        'workflow_triggers': [item['type'] for item in workflow_engine.list_trigger_types()],
        'workflow_steps': [item['type'] for item in workflow_engine.list_step_types()],
        'examples': supported_commands(),
    }


@router.get('/workflows/step-types')
async def workflow_step_types():
    return {'success': True, 'step_types': workflow_engine.list_step_types()}


@router.get('/workflows/trigger-types')
async def workflow_trigger_types():
    return {'success': True, 'trigger_types': workflow_engine.list_trigger_types()}


@router.get('/status')
async def automation_status():
    status = await workflow_engine.status()
    return {'success': True, 'status': status}


@router.get('/workflows')
async def list_workflows():
    workflows = await workflow_engine.list_workflows()
    return {'success': True, 'workflows': workflows}


@router.get('/workflows/{workflow_id}')
async def get_workflow(workflow_id: str):
    workflow = await workflow_engine.get_workflow(workflow_id)
    if not workflow:
        return {'success': False, 'error': 'Workflow not found'}
    return {'success': True, 'workflow': workflow}


@router.post('/workflows')
async def create_workflow(body: dict[str, Any] = Body(...)):
    workflow = await workflow_engine.create_workflow(body or {})
    return {'success': True, 'workflow': workflow}


@router.put('/workflows/{workflow_id}')
async def update_workflow(workflow_id: str, body: dict[str, Any] = Body(...)):
    workflow = await workflow_engine.update_workflow(workflow_id, body or {})
    if not workflow:
        return {'success': False, 'error': 'Workflow not found'}
    return {'success': True, 'workflow': workflow}


@router.delete('/workflows/{workflow_id}')
async def delete_workflow(workflow_id: str):
    deleted = await workflow_engine.delete_workflow(workflow_id)
    if not deleted:
        return {'success': False, 'error': 'Workflow not found'}
    return {'success': True, 'deleted': workflow_id}


@router.post('/workflows/{workflow_id}/clone')
async def clone_workflow(workflow_id: str):
    workflow = await workflow_engine.clone_workflow(workflow_id)
    if not workflow:
        return {'success': False, 'error': 'Workflow not found'}
    return {'success': True, 'workflow': workflow}


@router.post('/workflows/{workflow_id}/run')
async def run_workflow(workflow_id: str, body: dict[str, Any] | None = Body(default=None)):
    triggered_by = str((body or {}).get('triggered_by', 'manual')).strip() or 'manual'
    input_payload = (body or {}).get('input_payload', {})
    if not isinstance(input_payload, dict):
        input_payload = {}
    try:
        run = await workflow_engine.trigger_workflow(
            workflow_id, triggered_by=triggered_by, input_payload=input_payload
        )
    except KeyError:
        return {'success': False, 'error': 'Workflow not found'}
    except ValueError as exc:
        return {'success': False, 'error': str(exc)}
    return {'success': True, 'run': run}


@router.get('/workflows/{workflow_id}/runs')
async def list_workflow_runs(workflow_id: str, limit: int = 20):
    workflow = await workflow_engine.get_workflow(workflow_id)
    if not workflow:
        return {'success': False, 'error': 'Workflow not found'}
    runs = await workflow_engine.list_runs(workflow_id=workflow_id, limit=limit)
    return {'success': True, 'runs': runs}


@router.get('/workflow-runs')
async def list_all_workflow_runs(limit: int = 20):
    runs = await workflow_engine.list_runs(limit=limit)
    return {'success': True, 'runs': runs}


@router.get('/workflow-runs/{run_id}')
async def get_workflow_run(run_id: str):
    run = await workflow_engine.get_run(run_id)
    if not run:
        return {'success': False, 'error': 'Run not found'}
    return {'success': True, 'run': run}


@router.post('/workflow-runs/{run_id}/cancel')
async def cancel_workflow_run(run_id: str):
    try:
        cancelled = await workflow_engine.cancel_run(run_id)
    except KeyError:
        return {'success': False, 'error': 'Run not found'}
    return {'success': True, 'cancelled': cancelled, 'run_id': run_id}


@router.delete('/workflow-runs')
async def clear_workflow_runs(workflow_id: str | None = None):
    removed = await workflow_engine.clear_runs(workflow_id=workflow_id)
    return {'success': True, 'removed': removed, 'workflow_id': workflow_id or ''}


@router.post('/workflows/webhook/{token}')
async def trigger_workflow_webhook(token: str, body: dict[str, Any] | None = Body(default=None)):
    payload = body if isinstance(body, dict) else {}
    try:
        run = await workflow_engine.trigger_webhook(token, payload=payload)
    except KeyError:
        return {'success': False, 'error': 'Webhook workflow not found'}
    except ValueError as exc:
        return {'success': False, 'error': str(exc)}
    return {'success': True, 'run': run}


@router.get('/contacts')
async def list_contacts():
    return contacts_db.list_all()


@router.get('/contacts/search')
async def search_contacts(q: str):
    return contacts_db.search(q)


@router.post('/contacts')
async def add_contact(body: dict[str, Any] = Body(...)):
    name = str(body.get('name', '')).strip()
    if not name:
        return {'success': False, 'error': 'Name required'}
    contact = contacts_db.add(
        name=name,
        phone=str(body.get('phone', '')).strip(),
        whatsapp=str(body.get('whatsapp', '')).strip(),
        instagram=str(body.get('instagram', '')).strip(),
        email=str(body.get('email', '')).strip(),
        notes=str(body.get('notes', '')).strip(),
    )
    return {'success': True, 'contact': contact}


@router.post('/contacts/bulk')
async def bulk_upsert_contacts(body: dict[str, Any] = Body(...)):
    raw_contacts = body.get('contacts')
    csv_text = str(body.get('csv_text', '') or '')
    tsv_text = str(body.get('tsv_text', '') or '')
    parsed_rows: list[dict[str, Any]] = []

    if isinstance(raw_contacts, list):
        parsed_rows = [item for item in raw_contacts if isinstance(item, dict)]
    elif csv_text.strip() or tsv_text.strip():
        text = csv_text if csv_text.strip() else tsv_text
        delimiter = '\t' if tsv_text.strip() else ','
        reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
        parsed_rows = [dict(row or {}) for row in reader]
    else:
        return {
            'success': False,
            'error': 'Provide either contacts (array) or csv_text/tsv_text',
        }

    existing = {_normalize_contact_name(c.get('name', '')) for c in contacts_db.list_all()}
    created = 0
    updated = 0
    skipped = 0
    failed: list[dict[str, Any]] = []
    sample: list[dict[str, Any]] = []

    for idx, row in enumerate(parsed_rows):
        name = _pick_field(row, 'name', 'full name', 'fullname', 'display name')
        if not name:
            skipped += 1
            failed.append({'index': idx, 'error': 'name missing'})
            continue

        phone = _pick_field(row, 'phone', 'mobile', 'number')
        whatsapp = _pick_field(row, 'whatsapp', 'whatsapp number', 'wa')
        instagram = _pick_field(row, 'instagram', 'instagram handle', 'insta', 'ig')
        email = _pick_field(row, 'email', 'mail')
        notes = _pick_field(row, 'notes', 'note')

        key = _normalize_contact_name(name)
        current = contacts_db.get(name) if key in existing else None
        if isinstance(current, dict):
            if not phone:
                phone = str(current.get('phone', '') or '')
            if not whatsapp:
                whatsapp = str(current.get('whatsapp', '') or '')
            if not instagram:
                instagram = str(current.get('instagram', '') or '')
            if not email:
                email = str(current.get('email', '') or '')
            if not notes:
                notes = str(current.get('notes', '') or '')

        if key in existing:
            updated += 1
        else:
            created += 1
            existing.add(key)

        contact = contacts_db.add(
            name=name,
            phone=phone,
            whatsapp=whatsapp,
            instagram=instagram,
            email=email,
            notes=notes,
        )
        if len(sample) < 10:
            sample.append(contact)

    return {
        'success': True,
        'summary': {
            'received': len(parsed_rows),
            'created': created,
            'updated': updated,
            'skipped': skipped,
            'failed': len(failed),
            'total_contacts_now': len(contacts_db.list_all()),
        },
        'sample': sample,
        'errors': failed[:20],
    }


@router.get('/contacts/stats')
async def contacts_stats():
    items = contacts_db.list_all()
    total = len(items)
    with_whatsapp = sum(1 for c in items if str(c.get('whatsapp', '') or '').strip())
    with_instagram = sum(1 for c in items if str(c.get('instagram', '') or '').strip())
    with_email = sum(1 for c in items if str(c.get('email', '') or '').strip())
    return {
        'success': True,
        'stats': {
            'total': total,
            'with_whatsapp': with_whatsapp,
            'with_instagram': with_instagram,
            'with_email': with_email,
            'missing_whatsapp': max(0, total - with_whatsapp),
            'missing_instagram': max(0, total - with_instagram),
            'missing_email': max(0, total - with_email),
        },
    }


@router.post('/mobile-data/sync')
async def sync_mobile_data(body: dict[str, Any] = Body(...)):
    device_id = str(body.get('device_id', '')).strip() or 'mobile-default'
    summary = mobile_data_store.sync(device_id=device_id, payload=body or {})
    return {'success': True, 'summary': summary}


@router.get('/mobile-data/stats')
async def mobile_data_stats():
    return {'success': True, 'stats': mobile_data_store.stats()}


@router.delete('/contacts/{name}')
async def delete_contact(name: str):
    ok = contacts_db.delete(name)
    return {'success': ok, 'deleted': name}


@router.post('/whatsapp/send')
async def send_whatsapp(body: dict[str, Any] = Body(...)):
    contact = str(body.get('contact', '')).strip()
    message = str(body.get('message', '')).strip()
    if not contact or not message:
        return {'success': False, 'error': 'contact and message required'}
    if re.match(r'^[+\d]', contact):
        return wa.send_by_number(contact, message)
    return wa.send_to_contact(contact, message)


@router.post('/instagram/send')
async def send_instagram(body: dict[str, Any] = Body(...)):
    contact = str(body.get('contact', '')).strip()
    message = str(body.get('message', '')).strip()
    if not contact or not message:
        return {'success': False, 'error': 'contact and message required'}
    contact_obj = contacts_db.get(contact)
    if contact_obj and contact_obj.get('instagram'):
        return ig.send_to_contact(contact, message)
    return ig.send(contact, message)


@router.post('/messaging/login')
async def login_messaging(body: dict[str, Any] = Body(...)):
    platform = str(body.get('platform', '')).strip().lower()
    if platform not in {'whatsapp', 'instagram'}:
        return {'success': False, 'error': 'platform must be whatsapp or instagram'}
    ok = messaging.login(platform)
    return {
        'success': ok,
        'platform': platform,
        'error': '' if ok else messaging.last_error,
    }


@router.get('/messaging/auto-reply/profile')
async def get_auto_reply_profile():
    return {'success': True, 'profile': auto_reply_manager.get_profile()}


@router.put('/messaging/auto-reply/profile')
async def update_auto_reply_profile(body: dict[str, Any] = Body(...)):
    profile = auto_reply_manager.update_profile(body)
    return {'success': True, 'profile': profile}


@router.post('/messaging/auto-reply/generate')
async def generate_auto_reply(body: dict[str, Any] = Body(...)):
    incoming_message = str(body.get('incoming_message', '')).strip()
    platform = str(body.get('platform', '')).strip().lower()
    sender = str(body.get('sender', '')).strip()
    extra_context = str(body.get('context', '')).strip()
    result = auto_reply_manager.generate_reply(
        incoming_message=incoming_message,
        platform=platform,
        sender=sender,
        extra_context=extra_context,
    )
    return result


@router.post('/messaging/auto-reply/respond')
async def auto_reply_respond(body: dict[str, Any] = Body(...)):
    platform = str(body.get('platform', '')).strip().lower()
    recipient = str(body.get('recipient', '')).strip()
    incoming_message = str(body.get('incoming_message', '')).strip()
    sender = str(body.get('sender', '')).strip() or recipient
    extra_context = str(body.get('context', '')).strip()

    if platform not in {'whatsapp', 'instagram'}:
        return {'success': False, 'error': 'platform must be whatsapp or instagram'}
    if not recipient:
        return {'success': False, 'error': 'recipient is required'}

    generated = auto_reply_manager.generate_reply(
        incoming_message=incoming_message,
        platform=platform,
        sender=sender,
        extra_context=extra_context,
    )
    if not generated.get('success'):
        return generated

    reply_text = str(generated.get('reply', '')).strip()
    if not reply_text:
        return {'success': False, 'error': 'Failed to generate reply text'}

    if platform == 'whatsapp':
        send_result = wa.send_to_contact(recipient, reply_text)
    else:
        send_result = ig.send_to_contact(recipient, reply_text)

    success = bool(send_result.get('success'))
    error = str(send_result.get('error', '')).strip()
    return {
        'success': success,
        'platform': platform,
        'recipient': recipient,
        'incoming_message': incoming_message,
        'reply': reply_text,
        'send': send_result,
        'error': '' if success else error,
    }


@router.post('/browser/open')
async def open_url(body: dict[str, Any] = Body(...)):
    url = str(body.get('url', '')).strip()
    if not url:
        return {'success': False, 'error': 'url required'}
    ok = browser.open(url)
    return {'success': ok, 'url': url, 'error': '' if ok else 'Failed to open URL'}


@router.post('/browser/google')
async def google_search(body: dict[str, Any] = Body(...)):
    query = str(body.get('query', '')).strip()
    if not query:
        return {'success': False, 'error': 'query required'}
    ok = browser.google(query)
    return {'success': ok, 'query': query, 'error': '' if ok else 'Failed to open Google search'}


@router.post('/browser/youtube')
async def youtube(body: dict[str, Any] = Body(...)):
    query = str(body.get('query', '')).strip()
    if not query:
        return {'success': False, 'error': 'query required'}
    if bool(body.get('autoplay', False)):
        ok = browser.youtube_play(query)
    else:
        ok = browser.youtube_search(query)
    return {'success': ok, 'query': query, 'error': '' if ok else 'Failed to open YouTube'}


@router.post('/browser/maps')
async def maps_search(body: dict[str, Any] = Body(...)):
    place = str(body.get('place', '')).strip()
    if not place:
        return {'success': False, 'error': 'place required'}
    ok = browser.maps(place)
    return {'success': ok, 'place': place, 'error': '' if ok else 'Failed to open maps'}


@router.get('/browser/sites')
async def list_sites():
    return {'sites': list(SITE_MAP.keys())}


@router.post('/apps/launch')
async def open_app(body: dict[str, Any] = Body(...)):
    app_name = str(body.get('app', '')).strip()
    if not app_name:
        return {'success': False, 'error': 'app required'}
    return launch_app(app_name)


@router.post('/apps/close')
async def close_app_route(body: dict[str, Any] = Body(...)):
    app_name = str(body.get('app', '')).strip()
    if not app_name:
        return {'success': False, 'error': 'app required'}
    return close_app(app_name)


@router.get('/apps/list')
async def list_apps():
    return {'apps': list(APP_MAP.keys())}


@router.post('/system/screenshot')
async def screenshot():
    path = sys_ctrl.screenshot()
    return {'success': bool(path), 'path': path}


@router.post('/system/volume')
async def volume(body: dict[str, Any] = Body(...)):
    action = str(body.get('action', 'up')).strip().lower()
    steps = int(body.get('steps', 2))
    if action == 'up':
        sys_ctrl.vol_up(steps)
    elif action == 'down':
        sys_ctrl.vol_down(steps)
    elif action == 'mute':
        sys_ctrl.mute()
    else:
        return {'success': False, 'error': "action must be one of: up, down, mute"}
    return {'success': True, 'action': action, 'steps': steps}


@router.post('/system/lock')
async def lock_screen():
    sys_ctrl.lock()
    return {'success': True}


@router.post('/system/sleep')
async def sleep_pc():
    sys_ctrl.sleep()
    return {'success': True}


@router.post('/system/shutdown')
async def shutdown_pc(body: dict[str, Any] = Body(...)):
    delay = int(body.get('delay', 60))
    sys_ctrl.shutdown(delay)
    return {'success': True, 'in_seconds': delay}


@router.post('/system/cancel_shutdown')
async def cancel_shutdown():
    sys_ctrl.cancel_shutdown()
    return {'success': True}
