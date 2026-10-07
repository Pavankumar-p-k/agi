"""core.auth — password accounts + session tokens, file-backed, stdlib only.

Contract (tests/architecture/test_authentication.py,
tests/architecture/test_authorization.py, tests/architecture/test_resource_grant.py):

- ``AuthManager(auth_path=...)`` loads users from ``auth_path`` and sessions
  from ``<auth_path dir>/sessions.json``; re-initialising reloads persisted
  state (the expired-token fixtures edit the sessions file directly);
- ``setup(username, password)`` creates or updates an account — the first
  account on a fresh store becomes admin;
- ``create_session(username, password)`` verifies credentials and returns an
  opaque token (or ``None`` on bad credentials);
- ``get_username_for_token(token)`` returns the username for a live session
  or ``None`` for unknown/expired tokens;
- ``roles(username)`` returns ``["admin"]`` for admins, ``[]`` otherwise;
- users live in ``self._config["users"]`` (mutated + ``_save()`` by tests).

No network, no third-party dependencies: PBKDF2-HMAC-SHA256 for password
hashing, ``secrets`` for tokens, atomic ``os.replace`` writes.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import secrets
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

#: Default store location (patchable; tests redirect it to a tempdir).
DEFAULT_AUTH_PATH = str(
    Path(__file__).resolve().parent.parent / "personal" / "auth.json"
)

#: Session time-to-live, in seconds.
SESSION_TTL_SECONDS = 24 * 3600

_PBKDF2_ITERATIONS = 200_000
_SALT_BYTES = 16


def _hash_password(password: str, salt_hex: str) -> str:
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt_hex),
        _PBKDF2_ITERATIONS,
    )
    return digest.hex()


def _atomic_write_json(path: str, payload: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(tmp, target)


def _read_json(path: str) -> Optional[Any]:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        logger.warning("auth store %s unreadable (%s) — starting empty", path, exc)
        return None


class AuthManager:
    """File-backed user accounts + session tokens."""

    def __init__(self, auth_path: Optional[str] = None) -> None:
        self.auth_path = str(auth_path) if auth_path else str(DEFAULT_AUTH_PATH)
        self._lock = threading.RLock()
        self._config: Dict[str, Any] = {"users": {}}
        stored = _read_json(self.auth_path)
        if isinstance(stored, dict) and isinstance(stored.get("users"), dict):
            self._config = stored
        self._sessions: Dict[str, Dict[str, Any]] = {}
        stored_sessions = _read_json(self._sessions_path())
        if isinstance(stored_sessions, dict):
            self._sessions = stored_sessions

    # ── paths ──────────────────────────────────────────────────────────
    def _sessions_path(self) -> str:
        return str(Path(self.auth_path).parent / "sessions.json")

    # ── users ──────────────────────────────────────────────────────────
    @property
    def users(self) -> Dict[str, Any]:
        """Live view of the account table (fixtures mutate it directly)."""
        return self._config.setdefault("users", {})

    def _save(self) -> None:
        _atomic_write_json(self.auth_path, self._config)

    def setup(self, username: str, password: str) -> None:
        """Create or reset an account. First account on a fresh store = admin."""
        username = str(username or "").strip()
        if not username or not password:
            raise ValueError("username and password are required")
        with self._lock:
            users = self.users
            is_new_admin = not users
            if username in users and isinstance(users[username], dict):
                record = users[username]
            else:
                record = {}
            if "salt" not in record or "hash" not in record or is_new_admin:
                record["salt"] = secrets.token_hex(_SALT_BYTES)
                record["hash"] = _hash_password(password, record["salt"])
            record["is_admin"] = True if is_new_admin else bool(
                record.get("is_admin", False)
            )
            record["created"] = record.get("created") or time.time()
            users[username] = record
            self._save()

    def verify_password(self, username: str, password: str) -> bool:
        record = self.users.get(username)
        if not isinstance(record, dict) or "hash" not in record or "salt" not in record:
            return False
        import hmac

        return hmac.compare_digest(
            _hash_password(password, record["salt"]), record["hash"]
        )

    def roles(self, username: str) -> List[str]:
        record = self.users.get(username)
        if not isinstance(record, dict):
            return []
        return ["admin"] if record.get("is_admin") else []

    def is_admin(self, username: str) -> bool:
        record = self.users.get(username)
        return bool(isinstance(record, dict) and record.get("is_admin"))

    # ── sessions ───────────────────────────────────────────────────────
    def _save_sessions(self) -> None:
        _atomic_write_json(self._sessions_path(), self._sessions)

    def create_session(self, username: str, password: str) -> Optional[str]:
        """Validate credentials and mint a session token (None on failure)."""
        if not self.verify_password(username, password):
            return None
        with self._lock:
            token = secrets.token_urlsafe(32)
            now = time.time()
            self._sessions[token] = {
                "username": username,
                "created": now,
                "expiry": now + SESSION_TTL_SECONDS,
            }
            self._save_sessions()
            return token

    def get_username_for_token(self, token: str) -> Optional[str]:
        """Username for a live session; ``None`` for unknown/expired tokens."""
        if not token:
            return None
        with self._lock:
            record = self._sessions.get(token)
            if not isinstance(record, dict):
                return None
            if float(record.get("expiry", 0)) <= time.time():
                # Lazily drop expired sessions so the store stays clean.
                self._sessions.pop(token, None)
                self._save_sessions()
                return None
            return str(record.get("username", "")) or None

    def logout(self, token: str) -> bool:
        with self._lock:
            existed = self._sessions.pop(token, None) is not None
        if existed:
            self._save_sessions()
        return existed


_auth_manager: Optional[AuthManager] = None


def get_auth_manager() -> AuthManager:
    """Process-wide AuthManager (created on first use, patchable in tests)."""
    global _auth_manager
    if _auth_manager is None:
        _auth_manager = AuthManager()
    return _auth_manager


def set_auth_manager(manager: AuthManager) -> None:
    global _auth_manager
    _auth_manager = manager


__all__ = ["AuthManager", "get_auth_manager", "set_auth_manager", "DEFAULT_AUTH_PATH"]
