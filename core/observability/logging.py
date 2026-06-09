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
from __future__ import annotations

import json
import logging
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

_request_id: ContextVar[str] = ContextVar("_request_id", default="")
_user_id: ContextVar[str] = ContextVar("_user_id", default="")
_session_id: ContextVar[str] = ContextVar("_session_id", default="")


class LogContext:
    """Context variable manager for structured log fields."""

    @staticmethod
    def get_request_id() -> str:
        return _request_id.get()

    @staticmethod
    def set_request_id(rid: str):
        _request_id.set(rid)

    @staticmethod
    def get_user_id() -> str:
        return _user_id.get()

    @staticmethod
    def set_user_id(uid: str):
        _user_id.set(uid)

    @staticmethod
    def get_session_id() -> str:
        return _session_id.get()

    @staticmethod
    def set_session_id(sid: str):
        _session_id.set(sid)

    @staticmethod
    def reset():
        _request_id.set("")
        _user_id.set("")
        _session_id.set("")


class JsonFormatter(logging.Formatter):
    """JSON log formatter with structured context fields."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "line": record.lineno,
        }

        rid = LogContext.get_request_id()
        if rid:
            entry["request_id"] = rid
        uid = LogContext.get_user_id()
        if uid:
            entry["user_id"] = uid
        sid = LogContext.get_session_id()
        if sid:
            entry["session_id"] = sid

        if record.exc_info and record.exc_info[0]:
            entry["exception"] = self.formatException(record.exc_info)

        if hasattr(record, "extra_fields"):
            entry.update(record.extra_fields)

        return json.dumps(entry, default=str)


def configure_json_logging(level: int = logging.INFO, log_dir: str = "data/logs", max_bytes: int = 10 * 1024 * 1024, backup_count: int = 5) -> None:
    """Replace root logger handlers with JSON formatter and rotating file handler.

    Args:
        level: Log level (default: INFO, not DEBUG, to avoid token leakage in production).
        log_dir: Directory for rotating log files.
        max_bytes: Max bytes per log file before rotation.
        backup_count: Number of rotated log files to keep.
    """
    from logging.handlers import RotatingFileHandler
    from pathlib import Path

    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)
    log_file = log_path / "jarvis.json.log"

    root = logging.getLogger()
    root.setLevel(level)

    for handler in root.handlers[:]:
        root.removeHandler(handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(level)
    stream_handler.setFormatter(JsonFormatter())
    root.addHandler(stream_handler)

    file_handler = RotatingFileHandler(log_file, maxBytes=max_bytes, backupCount=backup_count)
    file_handler.setLevel(level)
    file_handler.setFormatter(JsonFormatter())
    root.addHandler(file_handler)

    # Ensure key loggers propagate
    for name in ("jarvis", "uvicorn", "uvicorn.access", "uvicorn.error"):
        lg = logging.getLogger(name)
        lg.setLevel(level)
        lg.propagate = True
