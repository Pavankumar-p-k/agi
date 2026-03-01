
from __future__ import annotations

import asyncio
import json
import re
import subprocess
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from automation.auto_reply import auto_reply_manager
from automation.pc_automation import (
    browser,
    close_app,
    execute_command,
    ig,
    launch_app,
    sys_ctrl,
    wa,
)

DATA_DIR = Path(__file__).resolve().parent.parent / 'data'
STATE_FILE = DATA_DIR / 'automation_workflows.json'
RUN_HISTORY_LIMIT = 500
SCHEDULER_INTERVAL_SECONDS = 2.0

STEP_TYPE_DEFS: list[dict[str, Any]] = [
    {'type': 'command', 'description': 'Run natural language command', 'params': {'text': 'string'}},
    {'type': 'set_var', 'description': 'Set runtime var', 'params': {'name': 'string', 'value': 'any'}},
    {'type': 'open_url', 'description': 'Open URL', 'params': {'url': 'string'}},
    {'type': 'google_search', 'description': 'Google query', 'params': {'query': 'string'}},
    {'type': 'youtube_search', 'description': 'YouTube query', 'params': {'query': 'string'}},
    {'type': 'youtube_play', 'description': 'YouTube play intent', 'params': {'query': 'string'}},
    {'type': 'maps_search', 'description': 'Maps search', 'params': {'place': 'string'}},
    {'type': 'launch_app', 'description': 'Launch app', 'params': {'app': 'string'}},
    {'type': 'close_app', 'description': 'Close app', 'params': {'app': 'string'}},
    {'type': 'whatsapp_send', 'description': 'WhatsApp message', 'params': {'recipient': 'string', 'message': 'string'}},
    {'type': 'instagram_send', 'description': 'Instagram DM', 'params': {'recipient': 'string', 'message': 'string'}},
    {
        'type': 'auto_reply_send',
        'description': 'Generate and send auto reply',
        'params': {'platform': 'whatsapp|instagram', 'recipient': 'string', 'incoming_message': 'string'},
    },
    {'type': 'shell', 'description': 'Run shell command', 'params': {'command': 'string', 'cwd': 'string'}},
    {'type': 'http_request', 'description': 'HTTP request', 'params': {'url': 'string', 'method': 'GET|POST'}},
    {'type': 'file_write', 'description': 'Write file', 'params': {'path': 'string', 'content': 'string'}},
    {'type': 'file_read', 'description': 'Read file', 'params': {'path': 'string'}},
    {
        'type': 'system_action',
        'description': 'System action',
        'params': {'action': 'screenshot|volume_up|volume_down|mute|lock|sleep|shutdown|cancel_shutdown'},
    },
    {'type': 'wait', 'description': 'Delay', 'params': {'seconds': 'number'}},
]

TRIGGER_DEFS: list[dict[str, Any]] = [
    {'type': 'manual', 'description': 'Run by API'},
    {'type': 'interval', 'description': 'Every N seconds', 'params': {'interval_seconds': '10-86400'}},
    {'type': 'daily', 'description': 'Daily HH:MM UTC', 'params': {'daily_time': 'HH:MM', 'weekdays': '[0..6]'}},
    {'type': 'once', 'description': 'One time ISO datetime', 'params': {'once_at': 'ISO datetime'}},
    {'type': 'webhook', 'description': 'Webhook token trigger', 'params': {'webhook_token': 'string'}},
]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _utcnow().isoformat()


def _safe_int(v: Any, d: int) -> int:
    try:
        return int(v)
    except Exception:
        return d


def _safe_float(v: Any, d: float) -> float:
    try:
        return float(v)
    except Exception:
        return d


def _to_dt(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(str(value))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _deep_copy(value: Any) -> Any:
    return json.loads(json.dumps(value))


def _hhmm(value: Any, default: str = '09:00') -> str:
    raw = str(value or '').strip()
    if not re.match(r'^\d{2}:\d{2}$', raw):
        return default
    h, m = raw.split(':')
    hh, mm = _safe_int(h, 9), _safe_int(m, 0)
    if 0 <= hh <= 23 and 0 <= mm <= 59:
        return f'{hh:02d}:{mm:02d}'
    return default


def _text(v: str, max_chars: int = 4000) -> str:
    return (v or '')[:max_chars]


class WorkflowEngine:
    def __init__(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()
        self._workflows: dict[str, dict[str, Any]] = {}
        self._runs: list[dict[str, Any]] = []
        self._running = False
        self._scheduler_task: Optional[asyncio.Task[None]] = None
        self._active_workflow_tasks: dict[str, asyncio.Task[None]] = {}
        self._run_tasks: dict[str, asyncio.Task[None]] = {}
        self._run_to_workflow: dict[str, str] = {}
        self._load_state()

    def _load_state(self) -> None:
        if not STATE_FILE.exists():
            self._save_state()
            return
        try:
            payload = json.loads(STATE_FILE.read_text(encoding='utf-8') or '{}')
            workflows = payload.get('workflows', [])
            runs = payload.get('runs', [])
            loaded: dict[str, dict[str, Any]] = {}
            for row in workflows:
                wf = self._sanitize_workflow(row or {}, existing=False)
                loaded[wf['id']] = wf
            self._workflows = loaded
            ids = set(loaded.keys())
            self._runs = [self._sanitize_run(r) for r in runs if str((r or {}).get('workflow_id', '')) in ids][:RUN_HISTORY_LIMIT]
        except Exception:
            self._workflows, self._runs = {}, []
            self._save_state()

    def _save_state(self) -> None:
        STATE_FILE.write_text(
            json.dumps({'workflows': list(self._workflows.values()), 'runs': self._runs[:RUN_HISTORY_LIMIT]}, indent=2),
            encoding='utf-8',
        )
    def _sanitize_trigger(self, trigger: Any) -> dict[str, Any]:
        if not isinstance(trigger, dict):
            trigger = {}
        t = str(trigger.get('type', 'manual')).strip().lower() or 'manual'
        if t not in {'manual', 'interval', 'daily', 'once', 'webhook'}:
            t = 'manual'
        interval = min(86400, max(10, _safe_int(trigger.get('interval_seconds', 300), 300)))
        weekdays_raw = trigger.get('weekdays', [0, 1, 2, 3, 4, 5, 6])
        if not isinstance(weekdays_raw, list):
            weekdays_raw = [0, 1, 2, 3, 4, 5, 6]
        weekdays = sorted({n for n in (_safe_int(v, -1) for v in weekdays_raw) if 0 <= n <= 6}) or [0, 1, 2, 3, 4, 5, 6]
        once_at = _to_dt(trigger.get('once_at', ''))
        token = str(trigger.get('webhook_token', '')).strip()
        if t == 'webhook' and not token:
            token = uuid.uuid4().hex
        return {
            'type': t,
            'interval_seconds': interval,
            'daily_time': _hhmm(trigger.get('daily_time', '09:00')),
            'weekdays': weekdays,
            'once_at': once_at.isoformat() if once_at else '',
            'webhook_token': token,
        }

    def _sanitize_steps(self, steps: Any) -> list[dict[str, Any]]:
        if not isinstance(steps, list):
            return []
        out: list[dict[str, Any]] = []
        for raw in steps:
            if not isinstance(raw, dict):
                continue
            t = str(raw.get('type', '')).strip().lower()
            if not t:
                continue
            params = raw.get('params', {})
            if not isinstance(params, dict):
                params = {}
            out.append(
                {
                    'id': str(raw.get('id') or uuid.uuid4().hex),
                    'name': str(raw.get('name') or t).strip() or t,
                    'type': t,
                    'params': params,
                    'continue_on_error': bool(raw.get('continue_on_error', False)),
                    'delay_seconds': min(3600.0, max(0.0, _safe_float(raw.get('delay_seconds', 0), 0))),
                    'retry_count': min(5, max(0, _safe_int(raw.get('retry_count', 0), 0))),
                    'retry_delay_seconds': min(120.0, max(0.0, _safe_float(raw.get('retry_delay_seconds', 1), 1))),
                    'timeout_seconds': min(300.0, max(0.0, _safe_float(raw.get('timeout_seconds', 0), 0))),
                }
            )
        return out

    def _sanitize_workflow(self, raw: dict[str, Any], existing: bool) -> dict[str, Any]:
        now = _now_iso()
        wid = str(raw.get('id') or uuid.uuid4().hex)
        variables = raw.get('variables', {})
        if not isinstance(variables, dict):
            variables = {}
        tags = raw.get('tags', [])
        if not isinstance(tags, list):
            tags = []
        return {
            'id': wid,
            'name': str(raw.get('name') or '').strip() or f'Workflow {wid[:8]}',
            'description': str(raw.get('description') or '').strip(),
            'enabled': bool(raw.get('enabled', True)),
            'trigger': self._sanitize_trigger(raw.get('trigger', {})),
            'steps': self._sanitize_steps(raw.get('steps', [])),
            'variables': variables,
            'tags': [str(t).strip() for t in tags if str(t).strip()],
            'created_at': str(raw.get('created_at') or now),
            'updated_at': now if existing else str(raw.get('updated_at') or now),
            'last_run_at': str(raw.get('last_run_at') or '').strip(),
            'last_run_status': str(raw.get('last_run_status') or '').strip(),
            'success_runs': max(0, _safe_int(raw.get('success_runs', 0), 0)),
            'failed_runs': max(0, _safe_int(raw.get('failed_runs', 0), 0)),
        }

    def _sanitize_run(self, raw: Any) -> dict[str, Any]:
        if not isinstance(raw, dict):
            now = _now_iso()
            return {
                'id': uuid.uuid4().hex,
                'workflow_id': '',
                'workflow_name': '',
                'triggered_by': 'unknown',
                'status': 'failed',
                'started_at': now,
                'finished_at': now,
                'steps': [],
                'success_count': 0,
                'failure_count': 0,
                'error': 'Malformed run payload',
                'input_payload': {},
                'variables': {},
            }
        return {
            'id': str(raw.get('id') or uuid.uuid4().hex),
            'workflow_id': str(raw.get('workflow_id') or ''),
            'workflow_name': str(raw.get('workflow_name') or ''),
            'triggered_by': str(raw.get('triggered_by') or 'unknown'),
            'status': str(raw.get('status') or 'failed'),
            'started_at': str(raw.get('started_at') or _now_iso()),
            'finished_at': str(raw.get('finished_at') or ''),
            'steps': raw.get('steps', []) if isinstance(raw.get('steps', []), list) else [],
            'success_count': max(0, _safe_int(raw.get('success_count', 0), 0)),
            'failure_count': max(0, _safe_int(raw.get('failure_count', 0), 0)),
            'error': str(raw.get('error') or ''),
            'input_payload': raw.get('input_payload', {}) if isinstance(raw.get('input_payload', {}), dict) else {},
            'variables': raw.get('variables', {}) if isinstance(raw.get('variables', {}), dict) else {},
        }

    def _resolve_path(self, path: str, ctx: dict[str, Any]) -> Any:
        cur: Any = ctx
        for part in path.split('.'):
            token = part.strip()
            if token == '':
                return ''
            if isinstance(cur, dict):
                if token not in cur:
                    return ''
                cur = cur[token]
            elif isinstance(cur, list):
                if not token.isdigit():
                    return ''
                idx = int(token)
                if idx < 0 or idx >= len(cur):
                    return ''
                cur = cur[idx]
            else:
                return ''
        return cur

    def _render(self, value: Any, ctx: dict[str, Any]) -> Any:
        if isinstance(value, dict):
            return {k: self._render(v, ctx) for k, v in value.items()}
        if isinstance(value, list):
            return [self._render(v, ctx) for v in value]
        if not isinstance(value, str):
            return value
        pat = re.compile(r'{{\s*([^{}]+)\s*}}')
        full = pat.fullmatch(value.strip())
        if full:
            return self._resolve_path(full.group(1).strip(), ctx)
        return pat.sub(lambda m: str(self._resolve_path(m.group(1).strip(), ctx)), value)

    def _next_run(self, wf: dict[str, Any], now: Optional[datetime] = None) -> str:
        now_dt = now or _utcnow()
        if not wf.get('enabled'):
            return ''
        trigger = wf.get('trigger', {})
        t = str(trigger.get('type', 'manual'))
        if t == 'manual':
            return ''
        if t == 'webhook':
            return 'webhook'
        if t == 'interval':
            base = _to_dt(wf.get('last_run_at')) or _to_dt(wf.get('created_at')) or now_dt
            return (base + timedelta(seconds=_safe_int(trigger.get('interval_seconds', 300), 300))).isoformat()
        if t == 'daily':
            hhmm = str(trigger.get('daily_time', '09:00'))
            hh, mm = _safe_int(hhmm.split(':')[0], 9), _safe_int(hhmm.split(':')[1], 0)
            days = trigger.get('weekdays', [0, 1, 2, 3, 4, 5, 6])
            if not isinstance(days, list):
                days = [0, 1, 2, 3, 4, 5, 6]
            dayset = {n for n in (_safe_int(v, -1) for v in days) if 0 <= n <= 6}
            for add in range(0, 8):
                d = now_dt + timedelta(days=add)
                if d.weekday() not in dayset:
                    continue
                candidate = d.replace(hour=hh, minute=mm, second=0, microsecond=0)
                if candidate >= now_dt:
                    return candidate.isoformat()
            return ''
        if t == 'once':
            if _to_dt(wf.get('last_run_at')):
                return ''
            once_at = _to_dt(trigger.get('once_at'))
            return once_at.isoformat() if once_at else ''
        return ''

    def _is_due(self, wf: dict[str, Any], now: datetime) -> bool:
        if not wf.get('enabled'):
            return False
        trigger = wf.get('trigger', {})
        t = str(trigger.get('type', 'manual'))
        if t == 'interval':
            base = _to_dt(wf.get('last_run_at')) or _to_dt(wf.get('created_at')) or now
            return (now - base) >= timedelta(seconds=_safe_int(trigger.get('interval_seconds', 300), 300))
        if t == 'daily':
            hhmm = str(trigger.get('daily_time', '09:00'))
            hh, mm = _safe_int(hhmm.split(':')[0], 9), _safe_int(hhmm.split(':')[1], 0)
            days = trigger.get('weekdays', [0, 1, 2, 3, 4, 5, 6])
            if not isinstance(days, list):
                days = [0, 1, 2, 3, 4, 5, 6]
            dayset = {n for n in (_safe_int(v, -1) for v in days) if 0 <= n <= 6}
            if now.weekday() not in dayset:
                return False
            scheduled = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
            if now < scheduled:
                return False
            last = _to_dt(wf.get('last_run_at'))
            return not last or last.date() != now.date()
        if t == 'once':
            once_at = _to_dt(trigger.get('once_at'))
            return bool(once_at and now >= once_at and not _to_dt(wf.get('last_run_at')))
        return False

    def _find_run(self, run_id: str) -> Optional[dict[str, Any]]:
        for run in self._runs:
            if run.get('id') == run_id:
                return run
        return None
    async def start(self) -> None:
        async with self._lock:
            if self._running:
                return
            self._running = True
            self._scheduler_task = asyncio.create_task(self._scheduler_loop())

    async def stop(self) -> None:
        async with self._lock:
            self._running = False
            sch = self._scheduler_task
            self._scheduler_task = None
            tasks = list(self._run_tasks.values())
            self._active_workflow_tasks, self._run_tasks, self._run_to_workflow = {}, {}, {}
        if sch:
            sch.cancel()
            await asyncio.gather(sch, return_exceptions=True)
        for t in tasks:
            t.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _scheduler_loop(self) -> None:
        while True:
            try:
                async with self._lock:
                    if not self._running:
                        return
                    now = _utcnow()
                    due_ids = [
                        wid for wid, wf in self._workflows.items() if self._is_due(wf, now) and wid not in self._active_workflow_tasks
                    ]
                for wid in due_ids:
                    try:
                        await self.trigger_workflow(wid, triggered_by='scheduler')
                    except Exception:
                        continue
                await asyncio.sleep(SCHEDULER_INTERVAL_SECONDS)
            except asyncio.CancelledError:
                raise
            except Exception:
                await asyncio.sleep(SCHEDULER_INTERVAL_SECONDS)

    async def status(self) -> dict[str, Any]:
        async with self._lock:
            active = [r for r in self._runs if r.get('status') == 'running']
            return {
                'engine_running': self._running,
                'workflow_count': len(self._workflows),
                'enabled_workflow_count': len([w for w in self._workflows.values() if w.get('enabled')]),
                'active_run_count': len(active),
                'active_runs': [
                    {
                        'run_id': r.get('id'),
                        'workflow_id': r.get('workflow_id'),
                        'workflow_name': r.get('workflow_name'),
                        'started_at': r.get('started_at'),
                    }
                    for r in active
                ],
            }

    async def list_workflows(self) -> list[dict[str, Any]]:
        async with self._lock:
            now = _utcnow()
            rows = sorted(self._workflows.values(), key=lambda i: str(i.get('updated_at', '')), reverse=True)
            out = _deep_copy(rows)
            for wf in out:
                wf['next_run_at'] = self._next_run(wf, now=now)
                wf['is_running'] = wf.get('id') in self._active_workflow_tasks
            return out

    async def get_workflow(self, workflow_id: str) -> Optional[dict[str, Any]]:
        async with self._lock:
            wf = self._workflows.get(workflow_id)
            if not wf:
                return None
            out = _deep_copy(wf)
            out['next_run_at'] = self._next_run(out)
            out['is_running'] = workflow_id in self._active_workflow_tasks
            return out

    async def create_workflow(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with self._lock:
            wf = self._sanitize_workflow(payload or {}, existing=False)
            self._workflows[wf['id']] = wf
            self._save_state()
            out = _deep_copy(wf)
            out['next_run_at'] = self._next_run(out)
            out['is_running'] = False
            return out

    async def update_workflow(self, workflow_id: str, payload: dict[str, Any]) -> Optional[dict[str, Any]]:
        async with self._lock:
            old = self._workflows.get(workflow_id)
            if not old:
                return None
            merged = dict(old)
            merged.update(payload or {})
            merged['id'] = workflow_id
            merged['created_at'] = old.get('created_at', _now_iso())
            wf = self._sanitize_workflow(merged, existing=True)
            self._workflows[workflow_id] = wf
            self._save_state()
            out = _deep_copy(wf)
            out['next_run_at'] = self._next_run(out)
            out['is_running'] = workflow_id in self._active_workflow_tasks
            return out

    async def clone_workflow(self, workflow_id: str) -> Optional[dict[str, Any]]:
        async with self._lock:
            old = self._workflows.get(workflow_id)
            if not old:
                return None
            wf = _deep_copy(old)
            wf['id'] = uuid.uuid4().hex
            wf['name'] = f"{wf.get('name', 'Workflow')} (Copy)"
            wf['enabled'] = False
            wf['created_at'] = _now_iso()
            wf['updated_at'] = _now_iso()
            wf['last_run_at'] = ''
            wf['last_run_status'] = ''
            wf['success_runs'] = 0
            wf['failed_runs'] = 0
            for step in wf.get('steps', []):
                step['id'] = uuid.uuid4().hex
            if wf.get('trigger', {}).get('type') == 'webhook':
                wf['trigger']['webhook_token'] = uuid.uuid4().hex
            self._workflows[wf['id']] = wf
            self._save_state()
            wf['next_run_at'] = self._next_run(wf)
            wf['is_running'] = False
            return _deep_copy(wf)

    async def delete_workflow(self, workflow_id: str) -> bool:
        async with self._lock:
            if workflow_id not in self._workflows:
                return False
            task = self._active_workflow_tasks.get(workflow_id)
            if task:
                task.cancel()
            del self._workflows[workflow_id]
            self._runs = [r for r in self._runs if r.get('workflow_id') != workflow_id]
            self._save_state()
            return True

    async def clear_runs(self, workflow_id: Optional[str] = None) -> int:
        async with self._lock:
            before = len(self._runs)
            if workflow_id:
                self._runs = [r for r in self._runs if r.get('workflow_id') != workflow_id]
            else:
                self._runs = [r for r in self._runs if r.get('status') == 'running']
            removed = before - len(self._runs)
            self._save_state()
            return removed

    async def list_runs(self, workflow_id: Optional[str] = None, limit: int = 20) -> list[dict[str, Any]]:
        lim = min(RUN_HISTORY_LIMIT, max(1, _safe_int(limit, 20)))
        async with self._lock:
            rows = self._runs
            if workflow_id:
                rows = [r for r in rows if r.get('workflow_id') == workflow_id]
            return _deep_copy(rows[:lim])

    async def get_run(self, run_id: str) -> Optional[dict[str, Any]]:
        async with self._lock:
            row = self._find_run(run_id)
            return _deep_copy(row) if row else None

    async def trigger_workflow(
        self,
        workflow_id: str,
        triggered_by: str = 'manual',
        input_payload: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        async with self._lock:
            wf = self._workflows.get(workflow_id)
            if not wf:
                raise KeyError('Workflow not found')
            if workflow_id in self._active_workflow_tasks:
                raise ValueError('Workflow is already running')
            run_id = uuid.uuid4().hex
            run = {
                'id': run_id,
                'workflow_id': workflow_id,
                'workflow_name': wf.get('name', ''),
                'triggered_by': triggered_by,
                'status': 'running',
                'started_at': _now_iso(),
                'finished_at': '',
                'steps': [],
                'success_count': 0,
                'failure_count': 0,
                'error': '',
                'input_payload': input_payload or {},
                'variables': {},
            }
            self._runs.insert(0, run)
            self._runs = self._runs[:RUN_HISTORY_LIMIT]
            task = asyncio.create_task(self._run_workflow(workflow_id, run_id))
            self._active_workflow_tasks[workflow_id] = task
            self._run_tasks[run_id] = task
            self._run_to_workflow[run_id] = workflow_id
            self._save_state()
            return _deep_copy(run)

    async def trigger_webhook(self, token: str, payload: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        async with self._lock:
            wid = ''
            for id_, wf in self._workflows.items():
                tr = wf.get('trigger', {})
                if wf.get('enabled') and tr.get('type') == 'webhook' and str(tr.get('webhook_token')) == token:
                    wid = id_
                    break
            if not wid:
                raise KeyError('Webhook workflow not found')
        return await self.trigger_workflow(wid, triggered_by='webhook', input_payload=payload or {})

    async def cancel_run(self, run_id: str) -> bool:
        async with self._lock:
            task = self._run_tasks.get(run_id)
            if not task:
                if not self._find_run(run_id):
                    raise KeyError('Run not found')
                return False
            task.cancel()
            return True
    async def _run_workflow(self, workflow_id: str, run_id: str) -> None:
        status, err = 'success', ''
        vars_ctx: dict[str, Any] = {}
        try:
            async with self._lock:
                wf = self._workflows.get(workflow_id)
                run = self._find_run(run_id)
                if not wf or not run:
                    return
                steps = _deep_copy(wf.get('steps', []))
                if isinstance(wf.get('variables', {}), dict):
                    vars_ctx.update(_deep_copy(wf.get('variables', {})))
                payload = run.get('input_payload', {})
                if isinstance(payload, dict):
                    if isinstance(payload.get('variables'), dict):
                        vars_ctx.update(_deep_copy(payload['variables']))
                    for k, v in payload.items():
                        if k != 'variables':
                            # Keep raw payload names accessible directly in templates.
                            vars_ctx[k] = v
                            vars_ctx[f'payload_{k}'] = v
            ctx: dict[str, Any] = {
                'workflow': {'id': workflow_id},
                'run': {'id': run_id},
                'vars': vars_ctx,
                'steps': [],
                'last': {},
            }
            for i, step in enumerate(steps):
                delay = _safe_float(step.get('delay_seconds', 0), 0)
                if delay > 0:
                    await asyncio.sleep(delay)
                step_r = self._render(step, ctx)
                retries = _safe_int(step_r.get('retry_count', 0), 0)
                retry_delay = _safe_float(step_r.get('retry_delay_seconds', 1), 1)
                timeout = _safe_float(step_r.get('timeout_seconds', 0), 0)
                attempt, result = 0, {'success': False, 'error': 'not executed'}
                started = _now_iso()
                while True:
                    attempt += 1
                    try:
                        coro = self._execute_step(step_r, ctx)
                        result = await asyncio.wait_for(coro, timeout=timeout) if timeout > 0 else await coro
                    except asyncio.TimeoutError:
                        result = {'success': False, 'error': f'timeout {timeout}s'}
                    except Exception as ex:
                        result = {'success': False, 'error': str(ex)}
                    if result.get('success') or attempt > retries:
                        break
                    await asyncio.sleep(max(0.0, retry_delay))
                finished = _now_iso()
                ok = bool(result.get('success'))
                step_row = {
                    'index': i,
                    'step_id': step_r.get('id', ''),
                    'name': step_r.get('name', step_r.get('type', 'step')),
                    'type': step_r.get('type', ''),
                    'params': step_r.get('params', {}),
                    'success': ok,
                    'attempts': attempt,
                    'output': result,
                    'started_at': started,
                    'finished_at': finished,
                }
                ctx['steps'].append({'index': i, 'success': ok, 'output': result, 'type': step_row['type'], 'name': step_row['name']})
                ctx['last'] = result
                async with self._lock:
                    run = self._find_run(run_id)
                    if not run:
                        return
                    run['steps'].append(step_row)
                    run['variables'] = _deep_copy(vars_ctx)
                    if ok:
                        run['success_count'] += 1
                    else:
                        run['failure_count'] += 1
                        if not bool(step_r.get('continue_on_error', False)):
                            status = 'failed'
                            err = str(result.get('error') or 'step failed')
                    self._save_state()
                if status == 'failed':
                    break
        except asyncio.CancelledError:
            status, err = 'cancelled', 'Run cancelled'
        except Exception as ex:
            status, err = 'failed', str(ex)
        finally:
            async with self._lock:
                run = self._find_run(run_id)
                wf = self._workflows.get(workflow_id)
                if run:
                    run['status'] = status
                    run['error'] = err
                    run['finished_at'] = _now_iso()
                    run['variables'] = _deep_copy(vars_ctx)
                if wf:
                    wf['last_run_at'] = _now_iso()
                    wf['last_run_status'] = status
                    wf['updated_at'] = _now_iso()
                    if status == 'success':
                        wf['success_runs'] = _safe_int(wf.get('success_runs', 0), 0) + 1
                    elif status in {'failed', 'cancelled'}:
                        wf['failed_runs'] = _safe_int(wf.get('failed_runs', 0), 0) + 1
                self._active_workflow_tasks.pop(workflow_id, None)
                self._run_tasks.pop(run_id, None)
                self._run_to_workflow.pop(run_id, None)
                self._save_state()

    async def _execute_step(self, step: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        t = str(step.get('type', '')).strip().lower()
        p = step.get('params', {})
        if not isinstance(p, dict):
            p = {}
        try:
            if t == 'set_var':
                name = str(p.get('name') or '').strip()
                if not name:
                    return {'success': False, 'error': "set_var requires name"}
                ctx['vars'][name] = p.get('value')
                return {'success': True, 'name': name, 'value': p.get('value')}
            if t == 'command':
                text = str(p.get('text') or p.get('command') or '').strip()
                if not text:
                    return {'success': False, 'error': "command requires text"}
                r = await asyncio.to_thread(execute_command, text)
                return {'success': bool(r.get('success')), 'result': r}
            if t == 'open_url':
                url = str(p.get('url') or '').strip()
                if not url:
                    return {'success': False, 'error': "open_url requires url"}
                ok = await asyncio.to_thread(browser.open, url)
                return {'success': bool(ok), 'url': url}
            if t == 'google_search':
                q = str(p.get('query') or '').strip()
                if not q:
                    return {'success': False, 'error': "google_search requires query"}
                ok = await asyncio.to_thread(browser.google, q)
                return {'success': bool(ok), 'query': q}
            if t == 'youtube_search':
                q = str(p.get('query') or '').strip()
                if not q:
                    return {'success': False, 'error': "youtube_search requires query"}
                ok = await asyncio.to_thread(browser.youtube_search, q)
                return {'success': bool(ok), 'query': q}
            if t == 'youtube_play':
                q = str(p.get('query') or '').strip()
                if not q:
                    return {'success': False, 'error': "youtube_play requires query"}
                ok = await asyncio.to_thread(browser.youtube_play, q)
                return {'success': bool(ok), 'query': q}
            if t == 'maps_search':
                place = str(p.get('place') or '').strip()
                if not place:
                    return {'success': False, 'error': "maps_search requires place"}
                ok = await asyncio.to_thread(browser.maps, place)
                return {'success': bool(ok), 'place': place}
            if t == 'launch_app':
                app = str(p.get('app') or '').strip()
                if not app:
                    return {'success': False, 'error': "launch_app requires app"}
                r = await asyncio.to_thread(launch_app, app)
                return {'success': bool(r.get('success')), 'result': r}
            if t == 'close_app':
                app = str(p.get('app') or '').strip()
                if not app:
                    return {'success': False, 'error': "close_app requires app"}
                r = await asyncio.to_thread(close_app, app)
                return {'success': bool(r.get('success')), 'result': r}
            if t == 'whatsapp_send':
                to, msg = str(p.get('recipient') or '').strip(), str(p.get('message') or '').strip()
                if not to or not msg:
                    return {'success': False, 'error': "whatsapp_send requires recipient and message"}
                r = await asyncio.to_thread(wa.send_to_contact, to, msg)
                return {'success': bool(r.get('success')), 'result': r}
            if t == 'instagram_send':
                to, msg = str(p.get('recipient') or '').strip(), str(p.get('message') or '').strip()
                if not to or not msg:
                    return {'success': False, 'error': "instagram_send requires recipient and message"}
                r = await asyncio.to_thread(ig.send_to_contact, to, msg)
                return {'success': bool(r.get('success')), 'result': r}
            if t == 'auto_reply_send':
                platform = str(p.get('platform') or '').strip().lower()
                to = str(p.get('recipient') or '').strip()
                incoming = str(p.get('incoming_message') or '').strip()
                sender = str(p.get('sender') or to).strip()
                if platform not in {'whatsapp', 'instagram'}:
                    return {'success': False, 'error': "auto_reply_send platform must be whatsapp or instagram"}
                if not to or not incoming:
                    return {'success': False, 'error': "auto_reply_send requires recipient and incoming_message"}
                g = await asyncio.to_thread(
                    auto_reply_manager.generate_reply,
                    incoming,
                    platform,
                    sender,
                    str(p.get('context') or '').strip(),
                )
                if not g.get('success'):
                    return {'success': False, 'error': str(g.get('error', 'failed to generate reply'))}
                reply = str(g.get('reply') or '').strip()
                if not reply:
                    return {'success': False, 'error': 'generated reply empty'}
                sent = await asyncio.to_thread(wa.send_to_contact if platform == 'whatsapp' else ig.send_to_contact, to, reply)
                return {'success': bool(sent.get('success')), 'generated_reply': reply, 'send_result': sent}
            if t == 'shell':
                cmd = str(p.get('command') or '').strip()
                if not cmd:
                    return {'success': False, 'error': "shell requires command"}
                cwd = str(p.get('cwd') or '').strip() or None
                timeout = max(1, min(300, _safe_int(p.get('timeout', 60), 60)))
                allow_nonzero = bool(p.get('allow_nonzero', False))

                def runner() -> subprocess.CompletedProcess[str]:
                    return subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True, timeout=timeout)

                cp = await asyncio.to_thread(runner)
                ok = cp.returncode == 0 or allow_nonzero
                return {
                    'success': ok,
                    'returncode': cp.returncode,
                    'stdout': _text(cp.stdout or ''),
                    'stderr': _text(cp.stderr or ''),
                }
            if t == 'http_request':
                url = str(p.get('url') or '').strip()
                if not url:
                    return {'success': False, 'error': "http_request requires url"}
                method = str(p.get('method') or 'GET').strip().upper()
                headers = p.get('headers', {})
                if not isinstance(headers, dict):
                    headers = {}
                timeout = max(1.0, min(120.0, _safe_float(p.get('timeout', 20), 20)))
                data: Optional[bytes] = None
                if 'body_json' in p:
                    data = json.dumps(p.get('body_json')).encode('utf-8')
                    headers.setdefault('Content-Type', 'application/json')
                elif 'body_text' in p:
                    data = str(p.get('body_text') or '').encode('utf-8')

                def call_http() -> dict[str, Any]:
                    req = urllib.request.Request(
                        url=url,
                        method=method,
                        headers={str(k): str(v) for k, v in headers.items()},
                        data=data,
                    )
                    try:
                        with urllib.request.urlopen(req, timeout=timeout) as resp:
                            body = resp.read().decode('utf-8', errors='replace')
                            return {
                                'success': True,
                                'status': int(resp.status),
                                'headers': dict(resp.headers.items()),
                                'body': _text(body),
                            }
                    except urllib.error.HTTPError as he:
                        body = he.read().decode('utf-8', errors='replace') if he.fp else ''
                        return {
                            'success': False,
                            'status': int(he.code),
                            'error': str(he),
                            'body': _text(body),
                        }
                    except Exception as ex:
                        return {'success': False, 'error': str(ex)}

                return await asyncio.to_thread(call_http)
            if t == 'file_write':
                path = str(p.get('path') or '').strip()
                if not path:
                    return {'success': False, 'error': "file_write requires path"}
                content = str(p.get('content') or '')
                append = bool(p.get('append', False))
                fpath = Path(path).expanduser()
                fpath.parent.mkdir(parents=True, exist_ok=True)
                if append:
                    with fpath.open('a', encoding='utf-8') as f:
                        f.write(content)
                else:
                    fpath.write_text(content, encoding='utf-8')
                return {'success': True, 'path': str(fpath), 'bytes': len(content.encode('utf-8'))}
            if t == 'file_read':
                path = str(p.get('path') or '').strip()
                if not path:
                    return {'success': False, 'error': "file_read requires path"}
                max_chars = max(100, min(20000, _safe_int(p.get('max_chars', 4000), 4000)))
                fpath = Path(path).expanduser()
                if not fpath.exists():
                    return {'success': False, 'error': f'File not found: {fpath}'}
                full = fpath.read_text(encoding='utf-8', errors='replace')
                part = full[:max_chars]
                return {
                    'success': True,
                    'path': str(fpath),
                    'content': part,
                    'truncated': len(full) > len(part),
                }
            if t == 'system_action':
                action = str(p.get('action') or '').strip().lower()
                if action == 'screenshot':
                    path = await asyncio.to_thread(sys_ctrl.screenshot)
                    return {'success': bool(path), 'path': path}
                if action == 'volume_up':
                    steps = _safe_int(p.get('steps', 2), 2)
                    await asyncio.to_thread(sys_ctrl.vol_up, steps)
                    return {'success': True, 'action': action, 'steps': steps}
                if action == 'volume_down':
                    steps = _safe_int(p.get('steps', 2), 2)
                    await asyncio.to_thread(sys_ctrl.vol_down, steps)
                    return {'success': True, 'action': action, 'steps': steps}
                if action == 'mute':
                    await asyncio.to_thread(sys_ctrl.mute)
                    return {'success': True, 'action': action}
                if action == 'lock':
                    await asyncio.to_thread(sys_ctrl.lock)
                    return {'success': True, 'action': action}
                if action == 'sleep':
                    await asyncio.to_thread(sys_ctrl.sleep)
                    return {'success': True, 'action': action}
                if action == 'shutdown':
                    delay = _safe_int(p.get('delay', 60), 60)
                    await asyncio.to_thread(sys_ctrl.shutdown, delay)
                    return {'success': True, 'action': action, 'delay': delay}
                if action == 'cancel_shutdown':
                    await asyncio.to_thread(sys_ctrl.cancel_shutdown)
                    return {'success': True, 'action': action}
                return {'success': False, 'error': f'Unknown system_action: {action}'}
            if t == 'wait':
                sec = max(0.0, min(3600.0, _safe_float(p.get('seconds', 1), 1)))
                await asyncio.sleep(sec)
                return {'success': True, 'slept_seconds': sec}
            return {'success': False, 'error': f'Unknown step type: {t}'}
        except Exception as ex:
            return {'success': False, 'error': str(ex)}

    def list_step_types(self) -> list[dict[str, Any]]:
        return _deep_copy(STEP_TYPE_DEFS)

    def list_trigger_types(self) -> list[dict[str, Any]]:
        return _deep_copy(TRIGGER_DEFS)


workflow_engine = WorkflowEngine()
