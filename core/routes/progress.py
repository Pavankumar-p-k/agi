"""DesktopProgressReporter — structured progress events to a sink.

The desktop agent loop emits one event per step into
logs/desktop_progress.jsonl (or any callable sink) so progress can be
observed externally while a task runs.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass
class ProgressEvent:
    activity_id: str
    status: str
    progress: float
    message: str = ""
    metadata: dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        if not self.activity_id:
            raise ValueError("activity_id is required")
        if not self.status:
            raise ValueError("status is required")

    def to_dict(self) -> dict:
        return {
            "activity_id": self.activity_id,
            "status": self.status,
            "progress": self.progress,
            "message": self.message,
            "metadata": dict(self.metadata),
            "timestamp": self.timestamp,
        }


class DesktopProgressReporter:
    """Writes progress events through a sink callable and keeps the latest."""

    def __init__(self, sink: Optional[Callable[[dict], Any]] = None) -> None:
        self._sink = sink
        self._latest: dict[str, ProgressEvent] = {}

    def report(self, activity_id: str, status: str, progress: float,
               message: str = "", metadata: Optional[dict] = None) -> ProgressEvent:
        event = ProgressEvent(
            activity_id=str(activity_id),
            status=str(status),
            progress=max(0.0, min(1.0, float(progress))),
            message=str(message),
            metadata=dict(metadata or {}),
        )
        self._latest[event.activity_id] = event
        if self._sink is not None:
            try:
                self._sink(event.to_dict())
            except Exception:  # noqa: BLE001 — progress must never break the task
                pass
        return event

    def latest(self, activity_id: str) -> Optional[ProgressEvent]:
        return self._latest.get(str(activity_id))


__all__ = ["DesktopProgressReporter", "ProgressEvent"]
