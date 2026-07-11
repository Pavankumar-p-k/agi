from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from core.storage.registry import USER_DB, ensure_db_dir

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS auth_users (
    username        TEXT PRIMARY KEY,
    password_hash   TEXT NOT NULL,
    created_at      REAL NOT NULL,
    is_admin        INTEGER NOT NULL DEFAULT 0,
    privileges      TEXT NOT NULL DEFAULT '{}',
    totp_secret     TEXT,
    totp_enabled    INTEGER NOT NULL DEFAULT 0,
    totp_backup_codes TEXT
);

CREATE TABLE IF NOT EXISTS auth_sessions (
    token   TEXT PRIMARY KEY,
    username TEXT NOT NULL,
    expiry  REAL NOT NULL,
    created_at REAL NOT NULL DEFAULT (julianday('now'))
);

CREATE INDEX IF NOT EXISTS idx_auth_sessions_username ON auth_sessions(username);
CREATE INDEX IF NOT EXISTS idx_auth_sessions_expiry ON auth_sessions(expiry);
"""


class AuthStore:
    """SQLite-backed store for auth users and sessions.

    Uses ``user.db`` from the bounded-context storage layout (WP-009).
    Thread-safe with a per-instance RLock.
    """

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path or USER_DB
        self._lock = threading.RLock()
        ensure_db_dir(self._db_path)
        self._init_schema()

    @property
    def db_path(self) -> str:
        return self._db_path

    def _init_schema(self) -> None:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.executescript(_SCHEMA)
            conn.commit()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # ── Users ────────────────────────────────────────────────────────────

    @property
    def users(self) -> dict[str, Any]:
        with self._lock:
            conn = self._conn()
            try:
                rows = conn.execute("SELECT * FROM auth_users").fetchall()
                result: dict[str, Any] = {}
                for r in rows:
                    username = r["username"]
                    privs: dict = {}
                    try:
                        privs = json.loads(r["privileges"])
                    except (json.JSONDecodeError, TypeError):
                        pass
                    backup: list[str] = []
                    if r["totp_backup_codes"]:
                        try:
                            backup = json.loads(r["totp_backup_codes"])
                        except (json.JSONDecodeError, TypeError):
                            pass
                    result[username] = {
                        "password_hash": r["password_hash"],
                        "created": r["created_at"],
                        "is_admin": bool(r["is_admin"]),
                        "privileges": privs,
                        "totp_enabled": bool(r["totp_enabled"]),
                        "totp_secret": r["totp_secret"],
                        "totp_backup_codes": backup,
                    }
                return result
            finally:
                conn.close()

    def get_user(self, username: str) -> dict[str, Any] | None:
        return self.users.get(username)

    def create_user(
        self,
        username: str,
        password_hash: str,
        is_admin: bool = False,
        privileges: dict | None = None,
    ) -> bool:
        with self._lock:
            conn = self._conn()
            try:
                existing = conn.execute(
                    "SELECT 1 FROM auth_users WHERE username = ?", (username,)
                ).fetchone()
                if existing:
                    return False
                conn.execute(
                    """INSERT INTO auth_users
                       (username, password_hash, created_at, is_admin, privileges)
                       VALUES (?, ?, ?, ?, ?)""",
                    (
                        username,
                        password_hash,
                        time.time(),
                        1 if is_admin else 0,
                        json.dumps(privileges or {}),
                    ),
                )
                conn.commit()
                return True
            finally:
                conn.close()

    def update_user(self, username: str, **fields: Any) -> bool:
        with self._lock:
            conn = self._conn()
            try:
                existing = conn.execute(
                    "SELECT 1 FROM auth_users WHERE username = ?", (username,)
                ).fetchone()
                if not existing:
                    return False
                for key, value in fields.items():
                    col = key.replace("_", " ")
                    conn.execute(
                        f"UPDATE auth_users SET {key} = ? WHERE username = ?",
                        (value, username),
                    )
                conn.commit()
                return True
            finally:
                conn.close()

    def delete_user(self, username: str) -> bool:
        with self._lock:
            conn = self._conn()
            try:
                conn.execute("DELETE FROM auth_users WHERE username = ?", (username,))
                conn.execute("DELETE FROM auth_sessions WHERE username = ?", (username,))
                conn.commit()
                return conn.total_changes > 0
            finally:
                conn.close()

    def user_count(self) -> int:
        with self._lock:
            conn = self._conn()
            try:
                return conn.execute("SELECT COUNT(*) FROM auth_users").fetchone()[0]
            finally:
                conn.close()

    # ── Sessions ──────────────────────────────────────────────────────────

    def create_session(self, token: str, username: str, ttl: float) -> bool:
        with self._lock:
            conn = self._conn()
            try:
                conn.execute(
                    "INSERT INTO auth_sessions (token, username, expiry) VALUES (?, ?, ?)",
                    (token, username, time.time() + ttl),
                )
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False
            finally:
                conn.close()

    def validate_session(self, token: str) -> str | None:
        with self._lock:
            conn = self._conn()
            try:
                row = conn.execute(
                    "SELECT username, expiry FROM auth_sessions WHERE token = ?",
                    (token,),
                ).fetchone()
                if row is None:
                    return None
                if time.time() > row["expiry"]:
                    conn.execute("DELETE FROM auth_sessions WHERE token = ?", (token,))
                    conn.commit()
                    return None
                username = row["username"]
                user = conn.execute(
                    "SELECT 1 FROM auth_users WHERE username = ?", (username,)
                ).fetchone()
                if user is None:
                    conn.execute("DELETE FROM auth_sessions WHERE token = ?", (token,))
                    conn.commit()
                    return None
                return username
            finally:
                conn.close()

    def delete_session(self, token: str) -> bool:
        with self._lock:
            conn = self._conn()
            try:
                conn.execute("DELETE FROM auth_sessions WHERE token = ?", (token,))
                conn.commit()
                return conn.total_changes > 0
            finally:
                conn.close()

    def delete_user_sessions(self, username: str, except_token: str | None = None) -> int:
        with self._lock:
            conn = self._conn()
            try:
                if except_token:
                    deleted = conn.execute(
                        "DELETE FROM auth_sessions WHERE username = ? AND token != ?",
                        (username, except_token),
                    ).rowcount
                else:
                    deleted = conn.execute(
                        "DELETE FROM auth_sessions WHERE username = ?", (username,)
                    ).rowcount
                conn.commit()
                return deleted
            finally:
                conn.close()

    def prune_expired_sessions(self) -> int:
        with self._lock:
            conn = self._conn()
            try:
                deleted = conn.execute(
                    "DELETE FROM auth_sessions WHERE expiry < ?", (time.time(),)
                ).rowcount
                conn.commit()
                return deleted
            finally:
                conn.close()

    # ── Migration ─────────────────────────────────────────────────────────

    def import_from_auth_manager(self, mgr: Any) -> tuple[int, int]:
        """Import users and sessions from a legacy ``AuthManager`` instance.

        Returns ``(users_imported, sessions_imported)``.
        Idempotent — existing users are skipped.
        """
        users_imported = 0
        sessions_imported = 0

        with self._lock:
            conn = self._conn()
            try:
                for username, data in mgr.users.items():
                    existing = conn.execute(
                        "SELECT 1 FROM auth_users WHERE username = ?", (username,)
                    ).fetchone()
                    if existing:
                        continue
                    conn.execute(
                        """INSERT INTO auth_users
                           (username, password_hash, created_at, is_admin, privileges,
                            totp_secret, totp_enabled, totp_backup_codes)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            username,
                            data.get("password_hash", ""),
                            data.get("created", time.time()),
                            1 if data.get("is_admin") else 0,
                            json.dumps(data.get("privileges", {})),
                            data.get("totp_secret"),
                            1 if data.get("totp_enabled") else 0,
                            json.dumps(data.get("totp_backup_codes", [])),
                        ),
                    )
                    users_imported += 1

                sessions = getattr(mgr, "_sessions", {})
                for token, sess in sessions.items():
                    existing = conn.execute(
                        "SELECT 1 FROM auth_sessions WHERE token = ?", (token,)
                    ).fetchone()
                    if existing:
                        continue
                    conn.execute(
                        "INSERT INTO auth_sessions (token, username, expiry) VALUES (?, ?, ?)",
                        (token, sess.get("username", ""), sess.get("expiry", 0)),
                    )
                    sessions_imported += 1

                conn.commit()
            finally:
                conn.close()

        logger.info(
            "AuthStore: imported %d users and %d sessions from AuthManager",
            users_imported,
            sessions_imported,
        )
        return (users_imported, sessions_imported)

    def export_to_json(self, auth_path: str, sessions_path: str) -> None:
        """Export all data back to JSON files (rollback utility)."""
        all_users = self.users
        config: dict[str, Any] = {
            "users": {},
            "signup_enabled": False,
        }
        sessions_data: dict[str, Any] = {}
        for username, data in all_users.items():
            config["users"][username] = {
                "password_hash": data["password_hash"],
                "created": data["created"],
                "is_admin": data["is_admin"],
                "privileges": data["privileges"],
            }
            if data.get("totp_enabled"):
                config["users"][username]["totp_enabled"] = True
                config["users"][username]["totp_secret"] = data["totp_secret"]
                config["users"][username]["totp_backup_codes"] = data.get("totp_backup_codes", [])

        with self._lock:
            conn = self._conn()
            try:
                rows = conn.execute("SELECT * FROM auth_sessions").fetchall()
                for r in rows:
                    sessions_data[r["token"]] = {
                        "username": r["username"],
                        "expiry": r["expiry"],
                    }
            finally:
                conn.close()

        Path(auth_path).parent.mkdir(parents=True, exist_ok=True)
        Path(auth_path).write_text(json.dumps(config, indent=2), encoding="utf-8")
        Path(sessions_path).write_text(json.dumps(sessions_data, indent=2), encoding="utf-8")
        logger.info("AuthStore: exported %d users, %d sessions to JSON", len(all_users), len(sessions_data))
