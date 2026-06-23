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
"""core/schemas.py — Pydantic + dataclass models for JARVIS"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

# ---- Brain dataclasses (Phase 1) ----

@dataclass
class ReasonResult:
    answer: str
    thinking_trace: str = ""
    confidence: float = 0.0
    steps_taken: int = 0
    provenance: dict[str, str] = field(default_factory=dict)
    model_group: str = "reasoning"

    def to_dict(self) -> dict:
        return {
            "conclusion": self.answer,
            "trace": [t for t in self.thinking_trace.split("\n") if t.strip()] if self.thinking_trace else [],
            "confidence": self.confidence,
            "model_group": self.model_group,
        }


@dataclass
class CritiqueResult:
    flaws: list[str] = field(default_factory=list)
    severity: str = "minor"
    revised_output: str = ""


@dataclass
class Step:
    id: str = ""
    description: str = ""
    depends_on: list[str] = field(default_factory=list)
    agent_type: str = "general"
    tools_allowed: list[str] = field(default_factory=lambda: ["*"])


@dataclass
class ToolCall:
    name: str = ""
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class LoopStep:
    thought: str = ""
    action: ToolCall | None = None
    observation: str = ""


@dataclass
class LoopResult:
    done: bool = False
    answer: str = ""
    history: list[LoopStep] = field(default_factory=list)
    steps: int = 0


# ---- Memory schemas (Phase 1) ----

@dataclass
class MemoryEntry:
    """Base memory entry with importance scoring."""
    id: str = ""
    text: str = ""
    importance: float = 0.0
    created_at: str = ""
    accessed_at: str = ""
    access_count: int = 0
    tags: list[str] = field(default_factory=list)


@dataclass
class GoalSchema:
    """Persistent goal with progress tracking."""
    id: str = ""
    objective: str = ""
    status: str = "active"
    progress: float = 0.0
    priority: int = 0
    parent_goal_id: str | None = None
    blockers: list[str] = field(default_factory=list)
    next_action: str = ""
    tags: list[str] = field(default_factory=list)
    result: str = ""
    deadline: str = ""
    created_at: str = ""
    updated_at: str = ""


@dataclass
class TaskNodeSchema:
    """A node in a DAG-based task graph."""
    id: str = ""
    label: str = ""
    description: str = ""
    status: str = "pending"
    depends_on: list[str] = field(default_factory=list)
    agent_type: str = "general"
    result: str = ""
    error: str = ""


@dataclass
class AutomationStatus:
    """Status of the autonomous execution loop."""
    running: bool = False
    paused: bool = False
    iterations: int = 0
    uptime_seconds: float = 0.0
    active_goals: int = 0
    poll_interval: float = 5.0


COMPLEX_TASK_TYPES = {"website", "code", "email", "report", "analysis", "research"}

class ChatRequest(BaseModel):
    message: str
    context: str | None = ""
    tier: str | None = None
    session_id: str | None = None
    task_type: str | None = None
    platform: str | None = None


class BrowserActionRequest(BaseModel):
    action: str
    url: str | None = None
    selector: str | None = None
    value: str | None = None
    script: str | None = None


class ReminderCreate(BaseModel):
    title: str
    remind_at: datetime
    description: str | None = ""
    repeat: str | None = "none"


class NoteCreate(BaseModel):
    title: str
    content: str
    tags: str | None = ""


class NoteUpdate(BaseModel):
    title: str | None = None
    content: str | None = None


class MessageRequest(BaseModel):
    platform: str
    recipient: str
    message: str


class FaceRegisterRequest(BaseModel):
    person_name: str
    relation: str | None = "unknown"
    info: str | None = ""
    access_level: str | None = "visitor"


class IntentResult(BaseModel):
    intent: Literal[
        "play_media", "open_url", "open_app",
        "web_search", "reminder", "pc_control", "browser_task", "message",
        "weather", "news", "stocks", "sports", "time",
        "build", "chat", "code_task"
    ]
    target: str = ""
    parameters: dict = {}


class SkillRunRequest(BaseModel):
    variables: dict = {}


class BuildRequest(BaseModel):
    goal: str
    output_dir: str = "."


class TaskAddRequest(BaseModel):
    task_id: str
    schedule: str
    action_type: str = "custom"
    params: dict = {}


class CodeReviewRequest(BaseModel):
    code: str
    language: str | None = "python"
    context: str | None = ""


class HorizonGoalRequest(BaseModel):
    goal: str
    domain: str = "general"
    horizon: str = "weekly"
    deadline: str = ""


class HorizonStatusUpdate(BaseModel):
    status: str

class QualityGradeRequest(BaseModel):
    type: str
    content: str

@dataclass
class MultiFormatResponse:
    prose: str
    json_data: dict | None = None
    html: str | None = None
    artifact_type: str | None = None
    artifact_code: str | None = None
    format_used: str = "prose"
