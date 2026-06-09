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
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import BASE_DIR

logger = logging.getLogger(__name__)

PII_PATTERNS: list[re.Pattern] = [
    re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    re.compile(r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b"),
    re.compile(r"\b\d{16}\b"),
    re.compile(r"(?i)(password|secret|token|api[_-]?key)\s*[:=]\s*\S+"),
]


def _strip_pii(text: str) -> str:
    for pattern in PII_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text


class AuditLog:
    def __init__(self, log_dir: str | Path = "", buffer_size: int = 50):
        if not log_dir:
            log_dir = BASE_DIR / "data" / "audit"
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._current_file: Path | None = None
        self._buffer: list[dict] = []
        self._buffer_size = buffer_size

    def _get_file(self) -> Path:
        today = datetime.utcnow().strftime("%Y-%m-%d")
        path = self.log_dir / f"audit-{today}.jsonl"
        if path != self._current_file:
            self._flush()
            self._current_file = path
        return path

    def _flush(self) -> None:
        if not self._buffer:
            return
        try:
            path = self._get_file()
            with open(path, "a", encoding="utf-8") as f:
                for entry in self._buffer:
                    f.write(json.dumps(entry) + "\n")
            self._buffer.clear()
        except Exception as e:
            logger.exception("[AuditLog] Flush failed: %s", e)

    def log(
        self,
        event: str,
        user_id: str = "",
        path: str = "",
        method: str = "",
        status: int = 0,
        privacy_tier: str = "",
        request_body: Any = None,
        response_summary: str = "",
        extra: dict | None = None,
    ) -> None:
        entry = {
            "ts": time.time(),
            "event": event,
            "user_id": user_id,
            "path": path,
            "method": method,
            "status": status,
            "privacy_tier": privacy_tier,
            "response_summary": response_summary[:200] if response_summary else "",
        }
        if request_body is not None:
            serialized = _strip_pii(json.dumps(request_body, default=str))
            entry["request_body"] = serialized[:500]
        if extra:
            entry.update(extra)
        self._buffer.append(entry)
        if len(self._buffer) >= self._buffer_size:
            self._flush()

    def force_flush(self) -> None:
        self._flush()


audit_log = AuditLog()
