from __future__ import annotations

import json
import time
from pathlib import Path

from ..contracts import ToolSpec


def register_communication_tools(registry) -> None:
    registry.register(
        ToolSpec("send_email", "Queue an outbound email draft.", ["to", "subject", "body"], category="communication"),
        lambda to, subject, body, **_: _send_email(registry, to, subject, body),
    )
    registry.register(
        ToolSpec("send_notification", "Emit a local notification event.", ["title", "message"], category="communication"),
        lambda title, message, **_: _send_notification(registry, title, message),
    )
    registry.register(
        ToolSpec("log_event", "Append an event to the communication log.", ["message", "level"], category="communication"),
        lambda message, level="INFO", **_: _log_event(registry, message, level),
    )
    registry.register(
        ToolSpec("read_event_log", "Read recent communication events.", [], category="communication", read_only=True),
        lambda **_: _read_log(registry),
    )


def _outbox_file(registry) -> Path:
    return Path(registry.config.data_dir) / "outbox.jsonl"


def _log_file(registry) -> Path:
    return Path(registry.config.data_dir) / "events.jsonl"


def _send_email(registry, to: str, subject: str, body: str) -> dict:
    payload = {"type": "email", "to": to, "subject": subject, "body": body, "timestamp": time.time()}
    with _outbox_file(registry).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload) + "\n")
    return {"queued": True, "to": to, "subject": subject}


def _send_notification(registry, title: str, message: str) -> dict:
    payload = {"type": "notification", "title": title, "message": message, "timestamp": time.time()}
    with _log_file(registry).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload) + "\n")
    return {"sent": True, "title": title, "message": message}


def _log_event(registry, message: str, level: str) -> dict:
    payload = {"type": "log", "level": level, "message": message, "timestamp": time.time()}
    with _log_file(registry).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload) + "\n")
    return {"logged": True, "level": level, "message": message}


def _read_log(registry) -> dict:
    target = _log_file(registry)
    if not target.exists():
        return {"events": []}
    rows = [json.loads(line) for line in target.read_text(encoding="utf-8").splitlines() if line.strip()]
    return {"events": rows[-50:]}
