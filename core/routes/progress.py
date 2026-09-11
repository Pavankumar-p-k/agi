"""Progress contracts for native desktop activity reporting."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Callable
import time


@dataclass(frozen=True)
class ProgressEvent:
    activity_id: str
    status: str
    progress: float
    message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        if not self.activity_id:
            raise ValueError("activity_id is required")
        if not 0.0 <= self.progress <= 1.0:
            raise ValueError("progress must be between 0 and 1")
        if not self.status:
            raise ValueError("status is required")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class DesktopProgressReporter:
    """Publishes progress to an injected callback; no network is required."""

    def __init__(self, callback: Callable[[dict[str, Any]], Any] | None = None):
        self.callback = callback
        self.history: list[ProgressEvent] = []

    def report(
        self,
        activity_id: str,
        status: str,
        progress: float,
        message: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> ProgressEvent:
        event = ProgressEvent(
            activity_id=activity_id,
            status=status,
            progress=max(0.0, min(1.0, float(progress))),
            message=message,
            metadata=dict(metadata or {}),
        )
        self.history.append(event)
        if self.callback is not None:
            self.callback(event.to_dict())
        return event

    def latest(self, activity_id: str) -> ProgressEvent | None:
        for event in reversed(self.history):
            if event.activity_id == activity_id:
                return event
        return None
