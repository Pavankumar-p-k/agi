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
# backend/core/types.py
"""
Shared type definitions for hybrid automation system
Breaks circular dependency between orchestrator and executor modules
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from models.hybrid_models import ModelProvider


class ExecutionState(Enum):
    """Task execution state enum"""
    PENDING = "pending"
    PLANNING = "planning"
    EXECUTING = "executing"
    VALIDATING = "validating"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"


@dataclass
class ExecutionContext:
    """Context for executing tasks - shared between orchestrator and executor"""
    user_id: str
    session_id: str
    platform: str = "system"
    memory_context: dict[str, Any] = field(default_factory=dict)
    variables: dict[str, Any] = field(default_factory=dict)
    permissions: list[str] = field(default_factory=lambda: ["read", "execute"])
    working_directory: str | None = None
    timeout: int = 300  # 5 minutes default
    max_retries: int = 3


@dataclass
class Task:
    """Task definition for hybrid orchestration"""
    id: str
    description: str
    goal: str
    state: ExecutionState = ExecutionState.PENDING
    subtasks: list[Task] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    result: Any | None = None
    error: str | None = None
    attempts: int = 0
    max_attempts: int = 3  # Will be overridden by orchestrator config
    created_at: float = field(default_factory=time.time)
    completed_at: float | None = None
    execution_time: float = 0.0
    model_used: str | None = None
    confidence: float = 0.0


@dataclass
class ExecutionResult:
    """Result from command execution"""
    success: bool
    output: str
    error: str | None = None
    exit_code: int | None = None
    execution_time: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SafetyCheck:
    """Safety check result"""
    allowed: bool
    reason: str
    risk_level: str  # "low", "medium", "high", "critical"


@dataclass
class ModelResult:
    """Result from model inference"""
    provider: ModelProvider  # Will be enum value from hybrid_models
    model: str
    response: str
    confidence: float
    latency_ms: int
    tokens_used: int
    fallback_reason: str | None = None
    error: str | None = None
