from __future__ import annotations

import base64
import json
import logging
import os
import sqlite3
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False


def _derive_key(master_key: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=600_000)
    return base64.urlsafe_b64encode(kdf.derive(master_key.encode()))


class PluginSecrets:
    def __init__(self, db_path: str | Path | None = None, master_key: str | None = None):
        if db_path is None:
            db_path = Path("data") / "plugin_secrets.db"
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._master_key = master_key or os.environ.get("JARVIS_SECRETS_KEY", "")
        self._fernet = None
        self._local = threading.local()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(str(self._db_path))
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
        return self._local.conn

    def _init_db(self) -> None:
        conn = self._get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS plugin_secrets (
                plugin_name TEXT NOT NULL,
                key TEXT NOT NULL,
                encrypted_value TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (plugin_name, key)
            )
        """)
        conn.commit()

    def _get_fernet(self) -> Any | None:
        if self._fernet is not None:
            return self._fernet
        if not HAS_CRYPTO or not self._master_key:
            logger.warning("[Secrets] Encryption unavailable (install cryptography or set JARVIS_SECRETS_KEY)")
            return None
        salt = self._db_path.stat().st_size.to_bytes(8, "big") + b"JARVIS"
        key = _derive_key(self._master_key, salt)
        self._fernet = Fernet(key)
        return self._fernet

    def set(self, plugin_name: str, key: str, value: str) -> None:
        conn = self._get_conn()
        fernet = self._get_fernet()
        if fernet:
            stored = fernet.encrypt(value.encode()).decode()
        else:
            stored = base64.b64encode(value.encode()).decode()
        conn.execute(
            """INSERT INTO plugin_secrets (plugin_name, key, encrypted_value)
               VALUES (?, ?, ?)
               ON CONFLICT(plugin_name, key) DO UPDATE SET
                   encrypted_value = excluded.encrypted_value""",
            (plugin_name, key, stored),
        )
        conn.commit()

    def get(self, plugin_name: str, key: str) -> str | None:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT encrypted_value FROM plugin_secrets WHERE plugin_name = ? AND key = ?",
            (plugin_name, key),
        ).fetchone()
        if row is None:
            return None
        fernet = self._get_fernet()
        try:
            if fernet:
                return fernet.decrypt(row["encrypted_value"].encode()).decode()
            return base64.b64decode(row["encrypted_value"]).decode()
        except Exception as e:
            logger.warning("[Secrets] Failed to decrypt %s/%s: %s", plugin_name, key, e)
            return None

    def delete(self, plugin_name: str, key: str) -> bool:
        conn = self._get_conn()
        cur = conn.execute(
            "DELETE FROM plugin_secrets WHERE plugin_name = ? AND key = ?",
            (plugin_name, key),
        )
        conn.commit()
        return cur.rowcount > 0

    def list_keys(self, plugin_name: str) -> list[str]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT key FROM plugin_secrets WHERE plugin_name = ? ORDER BY key",
            (plugin_name,),
        ).fetchall()
        return [r["key"] for r in rows]

    def clear(self, plugin_name: str) -> int:
        conn = self._get_conn()
        cur = conn.execute("DELETE FROM plugin_secrets WHERE plugin_name = ?", (plugin_name,))
        conn.commit()
        return cur.rowcount

    def has_key(self) -> bool:
        return bool(self._master_key)
