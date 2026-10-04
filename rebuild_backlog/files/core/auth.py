"""AuthManager — credential setup, session tokens, roles.

Contract (tests/architecture/test_authentication.py,
tests/architecture/test_authorization.py):
- ``AuthManager(auth_path=...)`` persists users in auth.json and sessions in
  ``sessions.json`` next to it (tests rewrite sessions[token]["expiry"]);
- ``setup(username, password)``, ``create_session(username, password)``,
  ``validate_token``, ``get_username_for_token``;
- users carry ``is_admin``; expired sessions are rejected on reload.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import time
from typing import Any, Dict, Optional

DEFAULT_AUTH_PATH = os.path.expanduser("~/.jarvis/auth.json")

SESSION_TTL_SECONDS = 24 * 3600


def _hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000
    ).hex()


class AuthManager:
    def __init__(self, auth_path: str = DEFAULT_AUTH_PATH):
        self.auth_path = auth_path
        self.sessions_path = os.path.join(
            os.path.dirname(auth_path) or ".", "sessions.json")
        self.users: Dict[str, dict] = {}
        self._config: Dict[str, Any] = {"users": self.users}
        self.sessions: Dict[str, dict] = {}
        self._load()

    # ── persistence ──────────────────────────────────────────────────
    def _load(self) -> None:
        if os.path.exists(self.auth_path):
            try:
                with open(self.auth_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._config = data if isinstance(data, dict) else {"users": {}}
                self.users = self._config.setdefault("users", {})
            except Exception:  # noqa: BLE001 — corrupt file: start clean
                self._config = {"users": {}}
                self.users = self._config["users"]
        if os.path.exists(self.sessions_path):
            try:
                with open(self.sessions_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    self.sessions = {
                        tok: sess
                        for tok, sess in loaded.items()
                        if isinstance(sess, dict)
                        and float(sess.get("expiry", 0)) > time.time()
                    }
            except Exception:  # noqa: BLE001
                self.sessions = {}

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self.auth_path) or ".", exist_ok=True)
        with open(self.auth_path, "w", encoding="utf-8") as f:
            json.dump(self._config, f, indent=2)

    def _save_sessions(self) -> None:
        os.makedirs(os.path.dirname(self.sessions_path) or ".", exist_ok=True)
        with open(self.sessions_path, "w", encoding="utf-8") as f:
            json.dump(self.sessions, f, indent=2)

    # ── users ────────────────────────────────────────────────────────
    def setup(self, username: str, password: str,
              is_admin: bool = True) -> bool:
        """Register a user. Single-user personal assistant: the owner is
        admin by default; pass is_admin=False to strip privileges."""
        salt = secrets.token_hex(16)
        self.users[username] = {
            "salt": salt,
            "password_hash": _hash_password(password, salt),
            "is_admin": bool(is_admin),
            "roles": ["admin"] if is_admin else [],
            "created_at": time.time(),
        }
        self._save()
        return True

    def verify_password(self, username: str, password: str) -> bool:
        user = self.users.get(username)
        if not user:
            return False
        return secrets.compare_digest(
            user.get("password_hash", ""),
            _hash_password(password, user.get("salt", "")),
        )

    def is_admin(self, username: str) -> bool:
        user = self.users.get(username) or {}
        return bool(user.get("is_admin"))

    def roles(self, username: str) -> list:
        user = self.users.get(username) or {}
        # The admin role is derived strictly from the is_admin flag, so
        # stripping the flag strips the role even if stale roles remain.
        roles = [r for r in user.get("roles", []) if r != "admin"]
        if user.get("is_admin"):
            roles.append("admin")
        return roles

    # ── sessions ─────────────────────────────────────────────────────
    def create_session(self, username: str, password: str,
                       ttl_seconds: int = SESSION_TTL_SECONDS) -> Optional[str]:
        if not self.verify_password(username, password):
            return None
        token = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip("=")
        self.sessions[token] = {
            "username": username,
            "created": time.time(),
            "expiry": time.time() + ttl_seconds,
        }
        self._save_sessions()
        return token

    def validate_token(self, token: str) -> bool:
        return self.get_username_for_token(token) is not None

    def get_username_for_token(self, token: str) -> Optional[str]:
        sess = self.sessions.get(token)
        if not sess:
            return None
        if float(sess.get("expiry", 0)) <= time.time():
            del self.sessions[token]
            self._save_sessions()
            return None
        return sess.get("username")

    def revoke(self, token: str) -> bool:
        if token in self.sessions:
            del self.sessions[token]
            self._save_sessions()
            return True
        return False


_auth_manager: Optional[AuthManager] = None


def get_auth_manager() -> AuthManager:
    global _auth_manager
    if _auth_manager is None:
        _auth_manager = AuthManager()
    return _auth_manager


def init_firebase():  # pragma: no cover — legacy hook kept for callers
    return None
