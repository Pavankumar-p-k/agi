"""Audit log — append-only, PII-redacted JSONL record of effectful actions.

Two pieces, one module:
- ``AuditLog``: buffered writer that appends one JSON object per line to a
  daily ``*.jsonl`` file (``force_flush()`` drains the buffer).
- ``EffectAuditMiddleware``: ASGI middleware that records every mutating
  request (POST/PUT/PATCH/DELETE) with its response status and request id.

PII is stripped from every recorded value before it is persisted.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── PII redaction ────────────────────────────────────────────────────────
_REDACTED = "[REDACTED]"

_PII_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), _REDACTED),
    (re.compile(r"\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b"), _REDACTED),
    (re.compile(r"\b(?:\d[ -]?){13,19}\b"), _REDACTED),
    (re.compile(r"(?i)\b(api[_-]?key|token)\b\s*[=:]\s*\S+"), f"\\1={_REDACTED}"),
    (re.compile(r"(?i)\bpassword\b\s*[=:]\s*\S+"), f"password={_REDACTED}"),
]


def _strip_pii(value: Any) -> Any:
    """Recursively redact PII from strings inside dicts/lists/scalars."""
    if value is None or isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, dict):
        return {k: _strip_pii(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_strip_pii(v) for v in value]
    if not isinstance(value, str):
        return value
    out = value
    for pattern, replacement in _PII_PATTERNS:
        out = pattern.sub(replacement, out)
    return out


class AuditLog:
    """Buffered, append-only audit log writer (one JSON object per line)."""

    def __init__(self, log_dir: Any = None, buffer_size: int = 100) -> None:
        self.log_dir = Path(log_dir) if log_dir is not None else Path(
            os.getenv("JARVIS_AUDIT_DIR", "data/audit"))
        self.buffer_size = max(1, int(buffer_size))
        self._buffer: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    # ── writing ──────────────────────────────────────────────────────
    def log(self, event: str = "", **fields: Any) -> None:
        entry: dict[str, Any] = {"event": event, "timestamp": time.time()}
        for key, value in fields.items():
            entry[key] = _strip_pii(value)
        should_flush = False
        with self._lock:
            self._buffer.append(entry)
            if len(self._buffer) >= self.buffer_size:
                should_flush = True
        if should_flush:
            self.force_flush()

    def _path(self) -> Path:
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return self.log_dir / f"audit_{day}.jsonl"

    def force_flush(self) -> None:
        with self._lock:
            entries, self._buffer = self._buffer, []
        if not entries:
            return
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            with self._path().open("a", encoding="utf-8") as handle:
                for entry in entries:
                    handle.write(json.dumps(entry, default=str) + "\n")
        except Exception:  # noqa: BLE001 — auditing must never break the app
            pass


class EffectAuditMiddleware:
    """Record mutating HTTP requests as ``effectful_request`` audit entries."""

    MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

    def __init__(self, app: Any, audit: Any = None) -> None:
        self.app = app
        self.audit = audit

    def _target(self) -> Any:
        if self.audit is not None:
            return self.audit
        import core.audit_log as module
        return module.audit_log

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope.get("type") != "http" or \
                str(scope.get("method", "")).upper() not in self.MUTATING_METHODS:
            await self.app(scope, receive, send)
            return

        captured: dict[str, Any] = {}

        async def send_wrapper(message: dict) -> None:
            if message.get("type") == "http.response.start":
                captured["status"] = message.get("status")
                for name, value in message.get("headers", []) or []:
                    if name.lower() == b"x-request-id":
                        captured["request_id"] = value.decode("utf-8", "replace")
            await send(message)

        await self.app(scope, receive, send_wrapper)
        try:
            self._target().log(
                event="effectful_request",
                method=scope.get("method", ""),
                path=scope.get("path", ""),
                status=captured.get("status"),
                request_id=captured.get("request_id", ""),
            )
        except Exception:  # noqa: BLE001
            pass


# Module-level singleton (tests swap this attribute to redirect writes).
audit_log = AuditLog()


__all__ = ["AuditLog", "EffectAuditMiddleware", "audit_log", "_strip_pii"]
