"""SchedulerMetrics — lightweight tracking for scheduler telemetry."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class TickRecord:
    tick: int
    timestamp: datetime
    activity_id: str | None
    score: int
    label: str
    duration_ms: float
    had_work: bool


@dataclass
class SchedulerMetrics:
    ticks: int = 0
    activities_resumed: int = 0
    activities_blocked: int = 0
    activities_completed: int = 0
    activities_failed: int = 0
    total_duration_ms: float = 0.0
    history: list[TickRecord] = field(default_factory=list)
    started_at: datetime | None = None
    last_tick_at: datetime | None = None

    def record_tick(self, record: TickRecord) -> None:
        self.ticks += 1
        self.last_tick_at = record.timestamp
        self.total_duration_ms += record.duration_ms
        self.history.append(record)

    def summary(self) -> dict[str, Any]:
        avg_ms = self.total_duration_ms / max(self.ticks, 1)
        return {
            "ticks": self.ticks,
            "activities_resumed": self.activities_resumed,
            "activities_blocked": self.activities_blocked,
            "activities_completed": self.activities_completed,
            "activities_failed": self.activities_failed,
            "avg_tick_ms": round(avg_ms, 1),
            "total_duration_ms": round(self.total_duration_ms, 1),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "last_tick_at": self.last_tick_at.isoformat() if self.last_tick_at else None,
        }
