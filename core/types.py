# backend/core/types.py
"""
Shared type definitions for hybrid automation system
Breaks circular dependency between orchestrator and executor modules
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, TYPE_CHECKING
from enum import Enum
import time

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
    memory_context: Dict[str, Any] = field(default_factory=dict)
    variables: Dict[str, Any] = field(default_factory=dict)
    permissions: List[str] = field(default_factory=lambda: ["read", "execute"])
    working_directory: Optional[str] = None
    timeout: int = 300  # 5 minutes default
    max_retries: int = 3


@dataclass
class Task:
    """Task definition for hybrid orchestration"""
    id: str
    description: str
    goal: str
    state: ExecutionState = ExecutionState.PENDING
    subtasks: List['Task'] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    result: Optional[Any] = None
    error: Optional[str] = None
    attempts: int = 0
    max_attempts: int = 3  # Will be overridden by orchestrator config
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    execution_time: float = 0.0
    model_used: Optional[str] = None
    confidence: float = 0.0


@dataclass
class ExecutionResult:
    """Result from command execution"""
    success: bool
    output: str
    error: Optional[str] = None
    exit_code: Optional[int] = None
    execution_time: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SafetyCheck:
    """Safety check result"""
    allowed: bool
    reason: str
    risk_level: str  # "low", "medium", "high", "critical"


@dataclass
class ModelResult:
    """Result from model inference"""
    provider: 'ModelProvider'  # Will be enum value from hybrid_models
    model: str
    response: str
    confidence: float
    latency_ms: int
    tokens_used: int
    fallback_reason: Optional[str] = None
    error: Optional[str] = None
