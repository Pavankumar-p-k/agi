# Copyright (c) 2024-2026 JARVIS Project
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# core/auth.py
"""DEPRECATED — use ``core.identity.IdentityService`` / ``core.identity.auth_store.AuthStore`` instead.

This module is a backward-compatibility shim. ``AuthManager`` still works
but delegates auth data to ``core.identity.auth_store.AuthStore`` (SQLite,
``user.db``). New code should use ``identity.get_identity_service()`` for
authentication and ``AuthStore`` for direct storage access.

Deprecated: v3.2
Remove after: v4.0
"""
from __future__ import annotations

import hmac
import json
import logging
import os
import secrets
import threading
import time
import warnings
from datetime import datetime
from pathlib import Path
from typing import Any

import bcrypt
import pyotp
from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .atomic_io import atomic_write_json as _atomic_write_json
from .authz import AuthContext, Role
from .authz.engine import authz_engine as policy_engine
from .config import DEV_MODE, FIREBASE_CREDENTIALS
from .database import User, get_db
from .rate_limiter import api_rate_limiter

logger = logging.getLogger(__name__)

_firebase_ready = False

# ---------------------------------------------------------------------------
# Privileges
# ---------------------------------------------------------------------------

DEFAULT_PRIVILEGES = {
    "can_use_agent": True,
    "can_use_browser": True,
    "can_use_bash": False,
    "can_use_documents": True,
    "can_use_research": True,
    "can_generate_images": True,
    "can_manage_memory": True,
    "max_messages_per_day": 0,
    "allowed_models": [],
}

ADMIN_PRIVILEGES = {k: (True if isinstance(v, bool) else (0 if isinstance(v, int) else []))
                    for k, v in DEFAULT_PRIVILEGES.items()}

DEFAULT_AUTH_PATH = os.path.join(
    Path(__file__).parent.parent, "data", "auth.json"
)
TOKEN_TTL = 60 * 60 * 24 * 7  # 7 days

RESERVED_USERNAMES = frozenset({"internal-tool", "api", "demo", "system"})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_compare(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


def _resolve_api_token() -> str | None:
    return os.getenv("JARVIS_API_TOKEN") or os.getenv("API_TOKEN") or None


def _is_trusted_proxy(request: Request) -> bool:
    trusted_proxies = os.getenv("TRUSTED_PROXIES", "").split(",")
    client_host = request.client.host if request.client else ""
    return client_host in ("127.0.0.1", "::1") or client_host in trusted_proxies


def _is_loopback(ip: str) -> bool:
    return ip in ("127.0.0.1", "::1", "localhost")


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


# ---------------------------------------------------------------------------
# Firebase
# ---------------------------------------------------------------------------

def init_firebase() -> None:
    global _firebase_ready
    try:
        import firebase_admin
        from firebase_admin import credentials

        if firebase_admin._apps:
            _firebase_ready = True
            return

        cred_path = FIREBASE_CREDENTIALS
        if cred_path and not cred_path.endswith(".json"):
            raise FileNotFoundError("Firebase credentials path must be a .json file")

        if cred_path and __import__("os").path.exists(cred_path):
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred)
            _firebase_ready = True
    except Exception as e:
        logger.warning("[AUTH] Firebase init failed: %s", e)
        _firebase_ready = False


async def _get_or_create_user(
    db: AsyncSession,
    uid: str,
    email: str | None = None,
    display_name: str | None = None,
) -> User:
    result = await db.execute(select(User).where(User.uid == uid))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(uid=uid, email=email or f"{uid}@local", display_name=display_name)
        db.add(user)
        await db.commit()
        await db.refresh(user)
    else:
        user.last_seen = datetime.utcnow()
        await db.commit()
    return user


# ---------------------------------------------------------------------------
# AuthManager — multi-user password + session + TOTP
# ---------------------------------------------------------------------------

class AuthManager:
    """DEPRECATED — Manages multi-user password + session-token auth system.

    Delegates primary storage to ``AuthStore`` (SQLite ``user.db``) with
    JSON fallback for backward compatibility.

    Use ``core.identity.IdentityService`` / ``core.identity.auth_store.AuthStore``
    instead.

    Deprecated: v3.2
    Remove after: v4.0
    """

    _deprecation_warned = False

    def __init__(self, auth_path: str = DEFAULT_AUTH_PATH):
        if not AuthManager._deprecation_warned:
            warnings.warn(
                "AuthManager is deprecated. "
                "Use 'core.identity.get_identity_service()' or "
                "'core.identity.auth_store.AuthStore' instead.",
                DeprecationWarning, stacklevel=2,
            )
            AuthManager._deprecation_warned = True
        self.auth_path = auth_path
        self._sessions_path = os.path.join(os.path.dirname(auth_path), "sessions.json")
        self._config: dict[str, Any] = {}
        self._sessions: dict[str, dict[str, Any]] = {}
        self._sessions_lock = threading.RLock()
        self._setup_lock = threading.Lock()
        self._load()
        self._load_sessions()
        self._migrate_single_user()
        self._migrate_legacy_admin_role()
        self._migrate_to_sqlite()

    def _load(self):
        try:
            if os.path.exists(self.auth_path):
                with open(self.auth_path, encoding="utf-8") as f:
                    self._config = json.load(f)
                if "users" in self._config:
                    self._config["users"] = {
                        k.strip().lower(): v
                        for k, v in self._config["users"].items()
                    }
                logger.info("Auth config loaded")
            else:
                self._config = {}
                logger.info("No auth config found — first-run setup required")
        except Exception as e:
            logger.error(f"Failed to load auth config: {e}")
            self._config = {}

    def _load_sessions(self):
        try:
            if os.path.exists(self._sessions_path):
                with open(self._sessions_path, encoding="utf-8") as f:
                    data = json.load(f)
                now = time.time()
                self._sessions = {k: v for k, v in data.items() if v.get("expiry", 0) > now}
                pruned = len(data) - len(self._sessions)
                if pruned > 0:
                    self._save_sessions()
                logger.info(f"Loaded {len(self._sessions)} session(s) from disk")
        except Exception as e:
            logger.error(f"Failed to load sessions: {e}")
            self._sessions = {}

    def _save_sessions(self):
        try:
            with self._sessions_lock:
                snapshot = dict(self._sessions)
            _atomic_write_json(self._sessions_path, snapshot)
        except Exception as e:
            logger.error(f"Failed to save sessions: {e}")

    def _migrate_single_user(self):
        if "password_hash" in self._config and "users" not in self._config:
            old_user = self._config.get("username", "admin")
            old_hash = self._config["password_hash"]
            self._config = {
                "users": {
                    old_user: {
                        "password_hash": old_hash,
                        "created": time.time(),
                        "is_admin": True,
                    }
                }
            }
            self._save()
            logger.info(f"Migrated single-user auth to multi-user (admin: {old_user})")

    def _migrate_legacy_admin_role(self):
        changed = False
        for username, user in self.users.items():
            if user.get("role") == "admin" and "is_admin" not in user:
                user["is_admin"] = True
                changed = True
                logger.info(f"Migrated legacy admin role for '{username}'")
        if changed:
            self._save()

    def _migrate_to_sqlite(self):
        """Migrate JSON auth data to SQLite AuthStore (idempotent)."""
        try:
            from core.identity.auth_store import AuthStore
            store = AuthStore()
            if store.user_count() == 0:
                imported = store.import_from_auth_manager(self)
                if imported[0] > 0 or imported[1] > 0:
                    logger.info("Auth data migrated to SQLite: %d users, %d sessions", *imported)
            else:
                expires = store.prune_expired_sessions()
                if expires:
                    logger.debug("Pruned %d expired sessions from SQLite store", expires)
        except Exception as e:
            logger.warning("SQLite auth migration skipped: %s", e)

    def _save(self):
        _atomic_write_json(self.auth_path, self._config, indent=2)

    @property
    def users(self) -> dict[str, Any]:
        return self._config.get("users", {})

    @property
    def signup_enabled(self) -> bool:
        return self._config.get("signup_enabled", False)

    @signup_enabled.setter
    def signup_enabled(self, value: bool):
        self._config["signup_enabled"] = value
        self._save()

    @property
    def is_configured(self) -> bool:
        return len(self.users) > 0

    def setup(self, username: str, password: str) -> bool:
        with self._setup_lock:
            if self.is_configured:
                return False
            return self.create_user(username, password, is_admin=True)

    def create_user(self, username: str, password: str, is_admin: bool = False) -> bool:
        username = username.strip().lower()
        if not username:
            return False
        if username in RESERVED_USERNAMES:
            logger.warning("Refused to create reserved username '%s'", username)
            return False
        if username in self.users:
            return False
        if "users" not in self._config:
            self._config["users"] = {}
        self._config["users"][username] = {
            "password_hash": _hash_password(password),
            "created": time.time(),
            "is_admin": is_admin,
            "privileges": dict(ADMIN_PRIVILEGES if is_admin else DEFAULT_PRIVILEGES),
        }
        self._save()
        logger.info(f"Created user '{username}' (admin={is_admin})")
        return True

    def delete_user(self, username: str, requesting_user: str) -> bool:
        username = username.strip().lower()
        if username not in self.users:
            return False
        if username == requesting_user:
            return False
        if not self.users.get(requesting_user, {}).get("is_admin"):
            return False
        del self._config["users"][username]
        self._save()
        revoked = 0
        with self._sessions_lock:
            to_drop = [tok for tok, sess in self._sessions.items()
                       if (sess or {}).get("username") == username]
            for tok in to_drop:
                self._sessions.pop(tok, None)
                revoked += 1
        if revoked:
            self._save_sessions()
        logger.info(f"Deleted user '{username}' (by {requesting_user}); revoked {revoked} active session(s)")
        return True

    def rename_user(self, old_username: str, new_username: str, requesting_user: str) -> bool:
        old_username = old_username.strip().lower()
        new_username = new_username.strip().lower()
        requesting_user = (requesting_user or "").strip().lower()
        if not old_username or not new_username:
            return False
        if new_username in RESERVED_USERNAMES:
            logger.warning("Refused to rename into reserved username '%s'", new_username)
            return False
        if old_username not in self.users:
            return False
        if new_username in self.users:
            return False
        if not self.users.get(requesting_user, {}).get("is_admin"):
            return False
        self._config.setdefault("users", {})[new_username] = self._config["users"].pop(old_username)
        self._save()
        renamed_sessions = 0
        with self._sessions_lock:
            for sess in self._sessions.values():
                sess_user = str((sess or {}).get("username") or "").strip().lower()
                if sess_user == old_username:
                    sess["username"] = new_username
                    renamed_sessions += 1
        if renamed_sessions:
            self._save_sessions()
        logger.info("Renamed '%s' -> '%s' (by %s); %d session(s)", old_username, new_username, requesting_user, renamed_sessions)
        return True

    def is_admin(self, username: str) -> bool:
        return self.users.get(username, {}).get("is_admin", False)

    def list_users(self) -> list[dict[str, Any]]:
        return [
            {"username": u, "is_admin": d.get("is_admin", False), "privileges": self.get_privileges(u)}
            for u, d in self.users.items()
        ]

    def get_privileges(self, username: str) -> dict[str, Any]:
        user = self.users.get(username, {})
        if user.get("is_admin"):
            return dict(ADMIN_PRIVILEGES)
        stored = user.get("privileges", {})
        return {**DEFAULT_PRIVILEGES, **stored}

    def set_privileges(self, username: str, privileges: dict[str, Any]) -> bool:
        username = username.strip().lower()
        if username not in self.users:
            return False
        if self.users[username].get("is_admin"):
            return False
        current = self.get_privileges(username)
        for k, v in privileges.items():
            if k in DEFAULT_PRIVILEGES:
                current[k] = v
        self._config["users"][username]["privileges"] = current
        self._save()
        logger.info(f"Updated privileges for '{username}': {current}")
        return True

    def change_password(self, username: str, current_password: str, new_password: str) -> bool:
        username = username.strip().lower()
        if username not in self.users:
            return False
        if not _verify_password(current_password, self.users[username]["password_hash"]):
            return False
        self._config["users"][username]["password_hash"] = _hash_password(new_password)
        self._save()
        return True

    def totp_enabled(self, username: str) -> bool:
        user = self.users.get(username.strip().lower(), {})
        return bool(user.get("totp_enabled"))

    def totp_generate_secret(self, username: str) -> str | None:
        username = username.strip().lower()
        if username not in self.users:
            return None
        secret = pyotp.random_base32()
        self._config["users"][username]["totp_secret_pending"] = secret
        self._save()
        return secret

    def totp_get_provisioning_uri(self, username: str, secret: str) -> str:
        totp = pyotp.TOTP(secret)
        return totp.provisioning_uri(name=username, issuer_name="JARVIS")

    def totp_confirm_enable(self, username: str, code: str) -> bool:
        username = username.strip().lower()
        user = self.users.get(username, {})
        secret = user.get("totp_secret_pending")
        if not secret:
            return False
        totp = pyotp.TOTP(secret)
        if not totp.verify(code, valid_window=1):
            return False
        self._config["users"][username]["totp_secret"] = secret
        self._config["users"][username]["totp_enabled"] = True
        self._config["users"][username].pop("totp_secret_pending", None)
        backup = [secrets.token_hex(4) for _ in range(8)]
        self._config["users"][username]["totp_backup_codes"] = backup
        self._save()
        logger.info(f"2FA enabled for '{username}'")
        return True

    def totp_verify(self, username: str, code: str) -> bool:
        username = username.strip().lower()
        user = self.users.get(username, {})
        if not user.get("totp_enabled"):
            return True
        secret = user.get("totp_secret")
        if not secret:
            return False
        backup = user.get("totp_backup_codes", [])
        if code in backup:
            backup.remove(code)
            self._config["users"][username]["totp_backup_codes"] = backup
            self._save()
            return True
        totp = pyotp.TOTP(secret)
        return totp.verify(code, valid_window=1)

    def totp_disable(self, username: str, password: str) -> bool:
        username = username.strip().lower()
        if not self.verify_password(username, password):
            return False
        self._config["users"][username].pop("totp_secret", None)
        self._config["users"][username].pop("totp_secret_pending", None)
        self._config["users"][username].pop("totp_backup_codes", None)
        self._config["users"][username]["totp_enabled"] = False
        self._save()
        return True

    def verify_password(self, username: str, password: str) -> bool:
        username = username.strip().lower()
        if username not in self.users:
            return False
        return _verify_password(password, self.users[username]["password_hash"])

    def create_session(self, username: str, password: str) -> str | None:
        username = username.strip().lower()
        if not self.verify_password(username, password):
            return None
        token = secrets.token_hex(32)
        with self._sessions_lock:
            self._sessions[token] = {
                "username": username,
                "expiry": time.time() + TOKEN_TTL,
            }
        self._save_sessions()
        return token

    def validate_token(self, token: str | None) -> bool:
        if not token:
            return False
        expired = False
        deleted_user = False
        with self._sessions_lock:
            session = self._sessions.get(token)
            if session is None:
                return False
            if time.time() > session["expiry"]:
                self._sessions.pop(token, None)
                expired = True
            else:
                if session.get("username") not in self.users:
                    self._sessions.pop(token, None)
                    deleted_user = True
        if expired or deleted_user:
            self._save_sessions()
            return False
        return True

    def get_username_for_token(self, token: str | None) -> str | None:
        if not token:
            return None
        expired = False
        deleted_user = False
        with self._sessions_lock:
            session = self._sessions.get(token)
            if session is None:
                return None
            if time.time() > session["expiry"]:
                self._sessions.pop(token, None)
                expired = True
            else:
                _u = session["username"]
                if _u not in self.users:
                    self._sessions.pop(token, None)
                    deleted_user = True
                else:
                    return _u
        if expired or deleted_user:
            self._save_sessions()
        return None

    def revoke_token(self, token: str):
        with self._sessions_lock:
            self._sessions.pop(token, None)
        self._save_sessions()

    def revoke_user_sessions(self, username: str, except_token: str | None = None) -> int:
        username = username.strip().lower()
        revoked = 0
        with self._sessions_lock:
            to_drop = [
                token for token, session in self._sessions.items()
                if token != except_token and (session or {}).get("username") == username
            ]
            for token in to_drop:
                self._sessions.pop(token, None)
                revoked += 1
            if revoked:
                self._save_sessions()
        return revoked

    def status(self, token: str | None) -> dict[str, Any]:
        username = self.get_username_for_token(token)
        authenticated = username is not None
        result = {
            "configured": self.is_configured,
            "authenticated": authenticated,
            "username": username,
            "is_admin": self.is_admin(username) if username else False,
        }
        if authenticated:
            result["privileges"] = self.get_privileges(username)
        return result

    def resolve_context(self, username: str) -> AuthContext:
        """Resolve a full AuthContext for a given username (for background tasks)."""
        roles = {Role.GUEST}
        if self.is_admin(username):
            roles.add(Role.ADMIN)
        elif username != "dev" and username != "api":
            roles.add(Role.DEVELOPER)

        if username == "dev":
            roles.add(Role.ADMIN)
        elif username == "api":
            roles.add(Role.OPERATOR)

        return AuthContext(
            user_id=username,
            roles=roles,
            scopes=set(),
            metadata={"source": "resolved"}
        )



# Lazy singleton for AuthManager (avoids disk I/O on every tool call)
_auth_manager_instance = None
def get_auth_manager() -> AuthManager:
    warnings.warn(
        "get_auth_manager() is deprecated. "
        "Use 'core.identity.get_identity_service()' instead.",
        DeprecationWarning, stacklevel=2,
    )
    global _auth_manager_instance
    if _auth_manager_instance is None:
        _auth_manager_instance = AuthManager()
    return _auth_manager_instance


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------

async def verify_token(
    authorization: str | None = Header(None),
    request: Request = None,
    db: AsyncSession = Depends(get_db),
) -> User:
    client_ip = request.client.host if request and request.client else "unknown"

    if not authorization:
        # Try session cookie (AuthManager)
        auth_mgr: AuthManager | None = getattr(request.app.state, "auth_manager", None) if request else None
        if auth_mgr:
            session_token = request.cookies.get("session_token") if request else None
            if session_token and auth_mgr.validate_token(session_token):
                username = auth_mgr.get_username_for_token(session_token)
                if username:
                    return await _get_or_create_user(db, uid=username, email=f"{username}@local", display_name=username)
        
        # ALWAYS allow loopback in local dev/rescue scenarios
        if _is_loopback(client_ip) or DEV_MODE:
            return await _get_or_create_user(db, uid="dev", email="dev@local", display_name="Dev User")
            
        if not api_rate_limiter.check("auth", client_ip):
            raise HTTPException(status_code=429, detail="Rate limit exceeded")
        raise HTTPException(status_code=401, detail="Missing Authorization header")


async def get_auth_context(
    user: User = Depends(verify_token),
    request: Request = None,
) -> AuthContext:
    """Resolve the AuthContext for the currently logged in user."""
    auth_mgr: AuthManager | None = getattr(request.app.state, "auth_manager", None) if request else None
    roles = {Role.GUEST}
    scopes = set()

    if auth_mgr:
        if auth_mgr.is_admin(user.uid):
            roles.add(Role.ADMIN)
        elif user.uid != "dev" and user.uid != "api":
            roles.add(Role.DEVELOPER)

    if user.uid == "dev":
        roles.add(Role.ADMIN)
    elif user.uid == "api":
        roles.add(Role.OPERATOR)

    client_ip = request.client.host if request and request.client else None

    return AuthContext(
        user_id=user.uid,
        roles=roles,
        scopes=scopes,
        ip_address=client_ip,
        session_id=request.cookies.get("session_token") if request else None
    )


def require_scope(scope: str):
    async def _dependency(ctx: AuthContext = Depends(get_auth_context)):
        if not policy_engine.evaluate(ctx, scope):
            raise HTTPException(status_code=403, detail=f"Insufficient permissions. Required scope: {scope}")
        return ctx
    return _dependency


def require_role(role: Role):
    async def _dependency(ctx: AuthContext = Depends(get_auth_context)):
        if Role.ADMIN not in ctx.roles and role not in ctx.roles:
            raise HTTPException(status_code=403, detail=f"Insufficient permissions. Required role: {role}")
        return ctx
    return _dependency


async def verify_token_from_request(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    """Alternative auth dependency that reads the token from the request (supports trusted-proxy forwarding)."""
    auth_header = request.headers.get("Authorization")
    if auth_header:
        return await verify_token(authorization=auth_header, request=request, db=db)

    if _is_trusted_proxy(request):
        forwarded_user = request.headers.get("X-Forwarded-User") or request.headers.get("X-User")
        if forwarded_user:
            return await _get_or_create_user(db, uid=forwarded_user, email=f"{forwarded_user}@local", display_name=forwarded_user)

    if DEV_MODE:
        return await _get_or_create_user(db, uid="dev", email="dev@local", display_name="Dev User")

    raise HTTPException(status_code=401, detail="Missing Authorization header")
