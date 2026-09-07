"""Authentication manager and Firebase initialization."""
from __future__ import annotations

import json
import os
import time
from datetime import datetime
from typing import Any

DEFAULT_AUTH_PATH = os.path.expanduser("~/.jarvis/auth.json")
DEFAULT_SESSIONS_PATH = os.path.expanduser("~/.jarvis/sessions.json")

_AUTH_MANAGER: "AuthManager | None" = None


class AuthManager:
    def __init__(self, auth_path: str = DEFAULT_AUTH_PATH, sessions_path: str | None = None):
        self.auth_path = auth_path
        self.sessions_path = sessions_path or os.path.join(os.path.dirname(auth_path), "sessions.json")
        self.is_configured = False
        self._config: dict[str, Any] = {"users": {}}
        self.users: dict[str, dict[str, Any]] = {}
        self.sessions: dict[str, dict[str, Any]] = {}
        self._load_state()
        self.is_configured = bool(self.users)

    def _ensure_parent(self, path: str) -> None:
        parent = os.path.dirname(path)
        if parent and not os.path.exists(parent):
            os.makedirs(parent, exist_ok=True)

    def _load_state(self) -> None:
        if os.path.exists(self.auth_path):
            try:
                with open(self.auth_path, "r", encoding="utf-8") as handle:
                    payload = json.load(handle)
                if isinstance(payload, dict):
                    self._config = payload
                    self.users = payload.get("users", {})
            except (OSError, json.JSONDecodeError):
                self._config = {"users": {}}
                self.users = {}
        if os.path.exists(self.sessions_path):
            try:
                with open(self.sessions_path, "r", encoding="utf-8") as handle:
                    payload = json.load(handle)
                if isinstance(payload, dict):
                    self.sessions = payload.get("sessions", payload)
            except (OSError, json.JSONDecodeError):
                self.sessions = {}
        self.users = {str(k): dict(v) if isinstance(v, dict) else {"username": str(k), "password": str(v)} for k, v in self.users.items()}
        self.sessions = {str(k): dict(v) if isinstance(v, dict) else {"user_id": str(v)} for k, v in self.sessions.items()}
        self._config["users"] = self.users

    def _save(self) -> None:
        self._ensure_parent(self.auth_path)
        self._ensure_parent(self.sessions_path)
        if isinstance(self._config, dict):
            user_map = self._config.get("users", self.users)
            if isinstance(user_map, dict):
                self.users = {str(k): dict(v) if isinstance(v, dict) else {"username": str(k), "password": str(v)} for k, v in user_map.items()}
            self._config["users"] = self.users
        with open(self.auth_path, "w", encoding="utf-8") as handle:
            json.dump(self._config, handle, indent=2, sort_keys=True)
        with open(self.sessions_path, "w", encoding="utf-8") as handle:
            json.dump(self.sessions, handle, indent=2, sort_keys=True)

    def _save_state(self) -> None:
        self._save()

    def setup(self, username: str, password: str) -> bool:
        self.is_configured = True
        is_admin = username.lower().startswith("admin")
        self.users[username] = {"username": username, "password": password, "is_admin": is_admin, "roles": ["admin" if is_admin else "user"]}
        self._save_state()
        return True

    def create_session(self, username: str, password: str) -> str:
        user = self.users.get(username, {})
        if isinstance(user, dict) and user.get("password") == password:
            token = f"tok_{username}_{os.urandom(8).hex()}"
            self.sessions[token] = {
                "user_id": username,
                "username": username,
                "expiry": time.time() + 3600,
            }
            self._save_state()
            return token
        return ""

    def validate_token(self, token: str) -> bool:
        session = self.sessions.get(token)
        if not isinstance(session, dict):
            return False
        expiry = session.get("expiry")
        if expiry is not None and time.time() > float(expiry):
            return False
        return True

    def get_username_for_token(self, token: str) -> str | None:
        session = self.sessions.get(token)
        if not isinstance(session, dict):
            return None
        user_id = session.get("user_id") or session.get("username")
        return str(user_id) if user_id is not None else None


def get_auth_manager(auth_path: str = DEFAULT_AUTH_PATH, sessions_path: str | None = None) -> AuthManager:
    global _AUTH_MANAGER
    if _AUTH_MANAGER is None or _AUTH_MANAGER.auth_path != auth_path or _AUTH_MANAGER.sessions_path != (sessions_path or os.path.join(os.path.dirname(auth_path), "sessions.json")):
        _AUTH_MANAGER = AuthManager(auth_path=auth_path, sessions_path=sessions_path)
    return _AUTH_MANAGER


def init_firebase():
    return None
