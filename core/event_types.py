"""Canonical event type definitions.

Every subsystem publishes and subscribes to these typed events,
making the system fully event-driven instead of call-chain-driven.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ── Goal events ──────────────────────────────────────────────

@dataclass
class GoalCreated:
    goal_id: str
    objective: str
    priority: int = 0
    source: str = "user"


@dataclass
class GoalCompleted:
    goal_id: str
    objective: str
    result: str = ""


@dataclass
class GoalFailed:
    goal_id: str
    objective: str
    reason: str = ""


# ── Task events ──────────────────────────────────────────────

@dataclass
class TaskCompleted:
    goal_id: str
    node_id: str
    label: str
    output: str = ""
    duration_ms: float = 0.0


@dataclass
class TaskFailed:
    goal_id: str
    node_id: str
    label: str
    error: str = ""
    duration_ms: float = 0.0


# ── Memory events ────────────────────────────────────────────

@dataclass
class MemoryStored:
    memory_type: str
    memory_id: str
    summary: str = ""


@dataclass
class MemoryRetrieved:
    memory_type: str
    query: str
    result_count: int = 0


# ── Verification events ──────────────────────────────────────

@dataclass
class VerificationPassed:
    action: str
    confidence: float = 0.0
    evidence: str = ""


@dataclass
class VerificationFailed:
    action: str
    issues: list = field(default_factory=list)
    confidence: float = 0.0


# ── User events ──────────────────────────────────────────────

@dataclass
class UserMessage:
    user_id: str = ""
    content: str = ""
    session_id: str = ""


@dataclass
class UserArrived:
    user_id: str = ""
    method: str = "unknown"


# ── File system events ───────────────────────────────────────

@dataclass
class FileCreated:
    path: str
    size_bytes: int = 0


@dataclass
class FileModified:
    path: str
    size_bytes: int = 0


@dataclass
class FileDeleted:
    path: str


# ── Communication events ─────────────────────────────────────

@dataclass
class EmailReceived:
    subject: str
    sender: str
    body_preview: str = ""
    message_id: str = ""


@dataclass
class CalendarEvent:
    summary: str
    start: str
    end: str = ""
    location: str = ""


# ── System events ────────────────────────────────────────────

@dataclass
class SystemDiskLow:
    path: str
    free_bytes: int = 0
    free_percent: float = 0.0


@dataclass
class SystemCpuHigh:
    percent: float = 0.0
    threshold: float = 90.0


@dataclass
class SystemMemoryHigh:
    percent: float = 0.0
    threshold: float = 90.0


# ── Internal events ──────────────────────────────────────────

@dataclass
class ObserverTick:
    observer_name: str
    findings: list = field(default_factory=list)


@dataclass
class LearningApplied:
    lesson_count: int = 0
    affected_subsystems: list = field(default_factory=list)


@dataclass
class GoalAutoCreated:
    goal_id: str
    objective: str
    reason: str = ""
    source_observation: str = ""
