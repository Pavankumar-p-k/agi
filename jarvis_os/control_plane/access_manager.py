"""Scoped host access and human approval management."""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
from jarvis_os.runtime.exceptions import RuntimeBoundaryViolation


class AccessManager:
    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}
        self._storage_path = Path(self.config.get("storage_path", "data/jarvis_access.json"))
        self._state: Dict[str, Any] = {
            "profiles": {
                "workspace": {
                    "description": "Code workspace access only.",
                    "scopes": ["workspace.read", "workspace.write", "shell.workspace", "browser.basic"],
                },
                "desktop": {
                    "description": "Desktop app launch and browser navigation.",
                    "scopes": ["app.launch", "browser.basic", "desktop.input"],
                },
                "mobile_sync": {
                    "description": "Android device inspection and sync metadata.",
                    "scopes": ["adb.read", "adb.control", "mobile.sync"],
                },
                "personal_assistant": {
                    "description": "Messaging, reminders, schedules, and notifications.",
                    "scopes": ["message.send", "message.read", "schedule.manage", "notify.local"],
                },
                "elevated_browser": {
                    "description": "DOM-level browser actions like login, form fill, cart, and checkout.",
                    "scopes": ["browser.dom"],
                },
            },
            "grants": ["workspace", "desktop", "mobile_sync", "personal_assistant"],
            "pending": [],
            "audit": [],
        }

    async def initialize(self):
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        if self._storage_path.exists():
            try:
                self._state = json.loads(self._storage_path.read_text(encoding="utf-8"))
            except Exception as err:
                import logging
                logging.getLogger(__name__).error("Exception swallowed: %s", err)
                raise RuntimeError(f"Exception swallowed: {err}")
        self._persist()

    async def shutdown(self):
        self._persist()

    def allowed_scopes(self) -> List[str]:
        scopes: List[str] = []
        for grant in self._state.get("grants", []):
            profile = self._state.get("profiles", {}).get(grant, {})
            scopes.extend(profile.get("scopes", []))
        return sorted(set(scopes))

    def can_access(self, scope: str) -> bool:
        return scope in self.allowed_scopes()

    def request_approval(self, action: str, scope: str, reason: str = "") -> Dict[str, Any]:
        ticket = {
            "ticket_id": f"apr_{uuid.uuid4().hex[:10]}",
            "action": action,
            "scope": scope,
            "reason": reason,
            "status": "pending",
            "created_at": time.time(),
        }
        self._state.setdefault("pending", []).append(ticket)
        self._audit("approval.requested", ticket)
        self._persist()
        return ticket

    def approve(self, ticket_id: str) -> Dict[str, Any]:
        ticket = self._find_ticket(ticket_id)
        if not ticket:
            return {"approved": False, "error": f"Ticket not found: {ticket_id}"}
        ticket["status"] = "approved"
        ticket["resolved_at"] = time.time()
        self._audit("approval.approved", ticket)
        self._persist()
        return {"approved": True, "ticket": ticket}

    def reject(self, ticket_id: str) -> Dict[str, Any]:
        ticket = self._find_ticket(ticket_id)
        if not ticket:
            return {"rejected": False, "error": f"Ticket not found: {ticket_id}"}
        ticket["status"] = "rejected"
        ticket["resolved_at"] = time.time()
        self._audit("approval.rejected", ticket)
        self._persist()
        return {"rejected": True, "ticket": ticket}

    def grant_profile(self, profile: str) -> Dict[str, Any]:
        if profile not in self._state.get("profiles", {}):
            return {"granted": False, "error": f"Unknown profile: {profile}"}
        grants = self._state.setdefault("grants", [])
        if profile not in grants:
            grants.append(profile)
            self._audit("profile.granted", {"profile": profile})
            self._persist()
        return {"granted": True, "profile": profile, "grants": grants}

    def status(self) -> Dict[str, Any]:
        pending = [ticket for ticket in self._state.get("pending", []) if ticket.get("status") == "pending"]
        return {
            "profiles": self._state.get("profiles", {}),
            "grants": list(self._state.get("grants", [])),
            "allowed_scopes": self.allowed_scopes(),
            "pending_approvals": pending,
            "audit_events": self._state.get("audit", [])[-20:],
        }

    def _find_ticket(self, ticket_id: str) -> Optional[Dict[str, Any]]:
        for ticket in self._state.get("pending", []):
            if ticket.get("ticket_id") == ticket_id:
                return ticket
        return None

    def _audit(self, name: str, payload: Dict[str, Any]):
        if name.endswith("rejected") or name.endswith("failed") or "error" in payload:
            raise RuntimeBoundaryViolation(f"Audit failure: {name} - {payload}")
        self._state.setdefault("audit", []).append({"ts": time.time(), "name": name, "payload": payload})
        self._state["audit"] = self._state["audit"][-200:]

    def _persist(self):
        self._storage_path.write_text(json.dumps(self._state, indent=2), encoding="utf-8")
