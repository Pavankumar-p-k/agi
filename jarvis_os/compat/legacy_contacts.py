from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


class LegacyContactsAdapter:
    def __init__(self, backend_root: Path) -> None:
        self.backend_root = Path(backend_root)
        self.path = self.backend_root / "data" / "contacts.json"

    def status(self) -> dict[str, Any]:
        payload = self._load()
        return {
            "name": "legacy_contacts",
            "available": self.path.exists(),
            "path": str(self.path),
            "count": len(payload),
        }

    def list_all(self) -> dict[str, Any]:
        contacts = sorted(self._load().values(), key=lambda item: str(item.get("name", "")).lower())
        return {"contacts": contacts, "count": len(contacts), "available": self.path.exists()}

    def search(self, query: str) -> dict[str, Any]:
        lowered = query.lower().strip()
        contacts = [
            contact
            for contact in self._load().values()
            if lowered in str(contact.get("name", "")).lower()
            or lowered in str(contact.get("phone", ""))
            or lowered in str(contact.get("instagram", "")).lower()
            or lowered in str(contact.get("whatsapp", ""))
        ]
        contacts.sort(key=lambda item: str(item.get("name", "")).lower())
        return {"contacts": contacts, "count": len(contacts), "query": query, "available": self.path.exists()}

    def upsert(
        self,
        *,
        name: str,
        phone: str = "",
        instagram: str = "",
        whatsapp: str = "",
        email: str = "",
        notes: str = "",
    ) -> dict[str, Any]:
        payload = self._load()
        key = name.lower().strip()
        contact = {
            "name": name.strip(),
            "phone": phone.strip(),
            "whatsapp": whatsapp.strip() or phone.strip(),
            "instagram": instagram.strip().lstrip("@"),
            "email": email.strip(),
            "notes": notes.strip(),
            "added_at": payload.get(key, {}).get("added_at", time.strftime("%Y-%m-%dT%H:%M:%S")),
        }
        payload[key] = contact
        self._save(payload)
        return {"saved": True, "contact": contact, "count": len(payload), "path": str(self.path)}

    def delete(self, name: str) -> dict[str, Any]:
        payload = self._load()
        key = name.lower().strip()
        deleted = key in payload
        contact = payload.pop(key, None)
        if deleted:
            self._save(payload)
        return {"deleted": deleted, "contact": contact or {}, "count": len(payload), "path": str(self.path)}

    def _load(self) -> dict[str, dict[str, Any]]:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception as err:
            import logging
            logging.getLogger(__name__).error("Exception swallowed: %s", err)
            raise RuntimeError(f"Exception swallowed: {err}")
        return {}

    def _save(self, payload: dict[str, dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
