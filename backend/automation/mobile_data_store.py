from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DATA_DIR = Path(__file__).resolve().parent.parent / 'data'
STORE_FILE = DATA_DIR / 'mobile_data_store.json'


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_list_of_dicts(value: Any, limit: int = 5000) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    out: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, dict):
            out.append(item)
            if len(out) >= limit:
                break
    return out


class MobileDataStore:
    def __init__(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._state: dict[str, Any] = {'devices': {}}
        self._load()

    def _load(self) -> None:
        if not STORE_FILE.exists():
            self._save()
            return
        try:
            raw = STORE_FILE.read_text(encoding='utf-8')
            payload = json.loads(raw) if raw.strip() else {}
            if isinstance(payload, dict):
                self._state = payload
            if not isinstance(self._state.get('devices'), dict):
                self._state['devices'] = {}
        except Exception:
            self._state = {'devices': {}}
            self._save()

    def _save(self) -> None:
        STORE_FILE.write_text(json.dumps(self._state, indent=2), encoding='utf-8')

    def sync(self, device_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        did = str(device_id or '').strip() or 'mobile-default'
        contacts = _safe_list_of_dicts(payload.get('contacts', []), limit=10000)
        call_logs = _safe_list_of_dicts(payload.get('call_logs', []), limit=10000)
        calendar_events = _safe_list_of_dicts(payload.get('calendar_events', []), limit=10000)
        sms_messages = _safe_list_of_dicts(payload.get('sms_messages', []), limit=10000)

        with self._lock:
            devices = self._state.setdefault('devices', {})
            devices[did] = {
                'updated_at': _now_iso(),
                'contacts': contacts,
                'call_logs': call_logs,
                'calendar_events': calendar_events,
                'sms_messages': sms_messages,
                'counts': {
                    'contacts': len(contacts),
                    'call_logs': len(call_logs),
                    'calendar_events': len(calendar_events),
                    'sms_messages': len(sms_messages),
                },
            }
            self._save()
            return {'device_id': did, **devices[did]['counts'], 'updated_at': devices[did]['updated_at']}

    def get_device(self, device_id: str) -> dict[str, Any]:
        did = str(device_id or '').strip() or 'mobile-default'
        with self._lock:
            devices = self._state.get('devices', {})
            item = devices.get(did, {})
            if not isinstance(item, dict):
                item = {}
            return dict(item)

    def stats(self) -> dict[str, Any]:
        with self._lock:
            devices = self._state.get('devices', {})
            device_count = 0
            contacts = 0
            call_logs = 0
            calendar_events = 0
            sms_messages = 0
            last_updated = ''
            per_device: list[dict[str, Any]] = []

            for did, item in devices.items():
                if not isinstance(item, dict):
                    continue
                cnt = item.get('counts', {})
                if not isinstance(cnt, dict):
                    cnt = {}
                c_contacts = int(cnt.get('contacts', 0) or 0)
                c_calls = int(cnt.get('call_logs', 0) or 0)
                c_events = int(cnt.get('calendar_events', 0) or 0)
                c_sms = int(cnt.get('sms_messages', 0) or 0)
                updated = str(item.get('updated_at', '') or '')

                device_count += 1
                contacts += c_contacts
                call_logs += c_calls
                calendar_events += c_events
                sms_messages += c_sms
                if updated > last_updated:
                    last_updated = updated

                per_device.append(
                    {
                        'device_id': str(did),
                        'updated_at': updated,
                        'contacts': c_contacts,
                        'call_logs': c_calls,
                        'calendar_events': c_events,
                        'sms_messages': c_sms,
                    }
                )

            return {
                'device_count': device_count,
                'contacts': contacts,
                'call_logs': call_logs,
                'calendar_events': calendar_events,
                'sms_messages': sms_messages,
                'last_updated': last_updated,
                'devices': per_device,
            }


mobile_data_store = MobileDataStore()

