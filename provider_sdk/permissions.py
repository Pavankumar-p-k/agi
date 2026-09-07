"""Durable permission and audit model for providers and OS actions.

Persists grant state and audit trail to SQLite so they survive restarts.
OS-level actions (cmd, powershell, regedit, task manager, file delete/write,
process control) are tracked separately with full provenance.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("jarvis.provider_sdk.permissions")

ALL_PERMISSIONS: frozenset[str] = frozenset({
    # Filesystem
    "filesystem.read",
    "filesystem.write",
    "filesystem.delete",
    # Network
    "network.http",
    "network.smtp",
    "network.websocket",
    # Clipboard
    "clipboard.read",
    "clipboard.write",
    # Desktop
    "desktop.window.read",
    "desktop.window.move",
    "desktop.mouse.move",
    "desktop.mouse.click",
    "desktop.keyboard.type",
    "desktop.screen.capture",
    # Process
    "process.list",
    "process.control",
    # Browser
    "browser.tabs.read",
    "browser.tabs.control",
    # System
    "system.environment",
    "system.shell",
    # OS gated actions (explicit permission required)
    "os.cmd",
    "os.powershell",
    "os.regedit",
    "os.task_manager",
    "os.file_delete",
    "os.file_write",
    "os.process_kill",
})

HIGH_RISK: frozenset[str] = frozenset({
    "system.shell",
    "os.cmd",
    "os.powershell",
    "os.regedit",
    "os.task_manager",
    "os.process_kill",
    "desktop.mouse.click",
    "desktop.keyboard.type",
    "desktop.screen.capture",
    "process.control",
    "filesystem.write",
    "filesystem.delete",
    "os.file_delete",
    "os.file_write",
})

# Map tool/action names to required permissions
ACTION_PERMISSION_MAP: dict[str, str] = {
    "cmd": "os.cmd",
    "cmd.exe": "os.cmd",
    "powershell": "os.powershell",
    "powershell.exe": "os.powershell",
    "pwsh": "os.powershell",
    "regedit": "os.regedit",
    "regedit.exe": "os.regedit",
    "taskmgr": "os.task_manager",
    "taskmgr.exe": "os.task_manager",
    "task_manager": "os.task_manager",
    "taskkill": "os.process_kill",
    "taskkill.exe": "os.process_kill",
    "stop-process": "os.process_kill",
    "kill": "os.process_kill",
    "write_file": "os.file_write",
    "append_file": "os.file_write",
    "delete_file": "os.file_delete",
    "del": "os.file_delete",
    "rm": "os.file_delete",
    "rd": "os.file_delete",
    "rmdir": "os.file_delete",
}


def validate_permissions(declared: list[str]) -> list[str]:
    errors: list[str] = []
    for p in declared:
        if p in ("all", "*", "everything", "any"):
            errors.append(f"Wildcard permission '{p}' is not allowed")
        elif p not in ALL_PERMISSIONS:
            errors.append(f"Unknown permission '{p}'")
    return errors


@dataclass
class PermissionGrant:
    permissions: frozenset[str] = field(default_factory=frozenset)
    high_risk_warning: bool = False
    granted_at: float = field(default_factory=time.time)
    expires_at: Optional[float] = None

    def allows(self, permission: str) -> bool:
        if self.expires_at and time.time() > self.expires_at:
            return False
        return permission in self.permissions


class PermissionManager:
    """Manages permission grants with durable SQLite-backed audit trail."""

    def __init__(self, db_path: str | Path = "data/permissions.db") -> None:
        self._db_path = Path(db_path)
        self._grants: dict[str, PermissionGrant] = {}
        self._lock = threading.Lock()
        self._ensure_db()

    def _ensure_db(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS permission_grants (
                    provider_id TEXT NOT NULL,
                    permissions TEXT NOT NULL,
                    high_risk_warning INTEGER NOT NULL DEFAULT 0,
                    granted_at REAL NOT NULL,
                    expires_at REAL,
                    PRIMARY KEY (provider_id)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS permission_audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    result TEXT NOT NULL,
                    provider_id TEXT NOT NULL,
                    permission TEXT NOT NULL,
                    action TEXT,
                    reason TEXT,
                    timestamp REAL NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS os_action_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider_id TEXT,
                    action TEXT NOT NULL,
                    target TEXT,
                    permission_required TEXT,
                    granted INTEGER NOT NULL,
                    reason TEXT,
                    metadata TEXT,
                    timestamp REAL NOT NULL
                )
            """)
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self._db_path))

    def grant(
        self,
        provider_id: str,
        permissions: frozenset[str],
        expires_in: Optional[float] = None,
    ) -> PermissionGrant:
        expires_at = time.time() + expires_in if expires_in else None
        grant = PermissionGrant(
            permissions=permissions,
            high_risk_warning=bool(permissions & HIGH_RISK),
            expires_at=expires_at,
        )
        with self._lock:
            self._grants[provider_id] = grant
            with self._connect() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO permission_grants "
                    "(provider_id, permissions, high_risk_warning, granted_at, expires_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (
                        provider_id,
                        json.dumps(sorted(permissions)),
                        int(grant.high_risk_warning),
                        grant.granted_at,
                        expires_at,
                    ),
                )
                conn.commit()
        return grant

    def load_grants(self) -> None:
        """Load persisted grants into memory (call at startup)."""
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT provider_id, permissions, high_risk_warning, granted_at, expires_at "
                    "FROM permission_grants"
                ).fetchall()
                for row in rows:
                    perms = frozenset(json.loads(row[1]))
                    self._grants[row[0]] = PermissionGrant(
                        permissions=perms,
                        high_risk_warning=bool(row[2]),
                        granted_at=row[3],
                        expires_at=row[4],
                    )

    def check(self, provider_id: str, permission: str) -> bool:
        grant = self._grants.get(provider_id)
        if grant is None:
            self._audit("DENY", provider_id, permission, reason="No grant exists")
            return False
        if not grant.allows(permission):
            self._audit("DENY", provider_id, permission, reason="Not in granted set")
            return False
        self._audit("ALLOW", provider_id, permission, reason="")
        return True

    def check_action(self, provider_id: str, action: str) -> bool:
        """Check if a provider has permission for a named action (e.g. 'cmd', 'write_file')."""
        required = ACTION_PERMISSION_MAP.get(action)
        if required is None:
            return True
        return self.check(provider_id, required)

    def log_os_action(
        self,
        action: str,
        target: str,
        provider_id: Optional[str] = None,
        permission_required: Optional[str] = None,
        granted: bool = True,
        reason: str = "",
        metadata: Optional[dict] = None,
    ) -> None:
        """Record an OS-level action to the durable audit log."""
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO os_action_log "
                    "(provider_id, action, target, permission_required, granted, reason, metadata, timestamp) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        provider_id,
                        action,
                        target,
                        permission_required,
                        int(granted),
                        reason,
                        json.dumps(metadata) if metadata else None,
                        time.time(),
                    ),
                )
                conn.commit()
        logger.info(
            "[OS_ACTION] %s %s provider=%s granted=%s reason=%s",
            action, target, provider_id, granted, reason,
        )

    def get_os_action_log(
        self,
        provider_id: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict]:
        with self._lock:
            with self._connect() as conn:
                if provider_id:
                    rows = conn.execute(
                        "SELECT id, provider_id, action, target, permission_required, "
                        "granted, reason, metadata, timestamp "
                        "FROM os_action_log WHERE provider_id = ? "
                        "ORDER BY timestamp DESC LIMIT ?",
                        (provider_id, limit),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT id, provider_id, action, target, permission_required, "
                        "granted, reason, metadata, timestamp "
                        "FROM os_action_log ORDER BY timestamp DESC LIMIT ?",
                        (limit,),
                    ).fetchall()
                return [
                    {
                        "id": r[0],
                        "provider_id": r[1],
                        "action": r[2],
                        "target": r[3],
                        "permission_required": r[4],
                        "granted": bool(r[5]),
                        "reason": r[6],
                        "metadata": json.loads(r[7]) if r[7] else None,
                        "timestamp": r[8],
                    }
                    for r in rows
                ]

    def _audit(
        self,
        result: str,
        provider_id: str,
        permission: str,
        action: str = "",
        reason: str = "",
    ) -> None:
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO permission_audit_log "
                    "(result, provider_id, permission, action, reason, timestamp) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (result, provider_id, permission, action, reason, time.time()),
                )
                conn.commit()

    def get_audit_log(
        self,
        provider_id: Optional[str] = None,
        limit: int = 500,
    ) -> list[dict]:
        with self._lock:
            with self._connect() as conn:
                if provider_id:
                    rows = conn.execute(
                        "SELECT id, result, provider_id, permission, action, reason, timestamp "
                        "FROM permission_audit_log WHERE provider_id = ? "
                        "ORDER BY timestamp DESC LIMIT ?",
                        (provider_id, limit),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT id, result, provider_id, permission, action, reason, timestamp "
                        "FROM permission_audit_log ORDER BY timestamp DESC LIMIT ?",
                        (limit,),
                    ).fetchall()
                return [
                    {
                        "id": r[0],
                        "result": r[1],
                        "provider_id": r[2],
                        "permission": r[3],
                        "action": r[4],
                        "reason": r[5],
                        "timestamp": r[6],
                    }
                    for r in rows
                ]

    def violations(
        self,
        provider_id: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict]:
        with self._lock:
            with self._connect() as conn:
                if provider_id:
                    rows = conn.execute(
                        "SELECT id, result, provider_id, permission, action, reason, timestamp "
                        "FROM permission_audit_log "
                        "WHERE result = 'DENY' AND provider_id = ? "
                        "ORDER BY timestamp DESC LIMIT ?",
                        (provider_id, limit),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT id, result, provider_id, permission, action, reason, timestamp "
                        "FROM permission_audit_log "
                        "WHERE result = 'DENY' "
                        "ORDER BY timestamp DESC LIMIT ?",
                        (limit,),
                    ).fetchall()
                return [
                    {
                        "id": r[0],
                        "result": r[1],
                        "provider_id": r[2],
                        "permission": r[3],
                        "action": r[4],
                        "reason": r[5],
                        "timestamp": r[6],
                    }
                    for r in rows
                ]

    def revoke(self, provider_id: str) -> bool:
        with self._lock:
            self._grants.pop(provider_id, None)
            with self._connect() as conn:
                conn.execute(
                    "DELETE FROM permission_grants WHERE provider_id = ?",
                    (provider_id,),
                )
                conn.commit()
        return True

    def clear(self) -> None:
        with self._lock:
            self._grants.clear()
            with self._connect() as conn:
                conn.execute("DELETE FROM permission_grants")
                conn.commit()


permission_manager = PermissionManager()
