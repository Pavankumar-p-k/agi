import logging
from typing import Any, Optional, Dict
from importlib import import_module


def _optional_import(module_path: str, symbol: str):
    try:
        module = import_module(module_path, package=__name__)
        return getattr(module, symbol)
    except (ImportError, AttributeError):
        return None


from .execution_context import BrainExecutionContext
from .reasoning_engine import ReasoningEngine
from .cognitive_patterns import PATTERNS
from .UnifiedBrain import UnifiedBrain

# Autonomous OS subsystems
from .memory import MemoryManager, EpisodicMemory, SemanticMemory, TaskMemory, DecisionMemory
from .goals import Goal, GoalStatus, GoalManager
from .planner import TaskGraph, TaskNode, Planner
from .executor import Executor, ActionResult, Verifier, VerificationResult
from .automation import AutomationLoop

# Event-driven architecture
from .events import (
    EventBus, Event, Subscription, PluginEventBus, global_event_bus,
    subscribe_event, unsubscribe_event, fire_event, get_task_scheduler,
    GoalCreated, GoalCompleted, GoalFailed,
    TaskCompleted, TaskFailed,
    MemoryStored, MemoryRetrieved,
    VerificationPassed, VerificationFailed,
    FileCreated, FileModified, FileDeleted,
    SystemDiskLow, SystemCpuHigh, SystemMemoryHigh,
    UserMessage, UserArrived,
    ObserverTick, LearningApplied, GoalAutoCreated,
)

# Environment observers
from .observers import ObserverManager, FileSystemObserver, SystemMonitor, TimeObserver

# Advanced subsystems
from .world_model import WorldModel, WorldState
from .learning_engine import LearningEngine, learning_engine
from .goal_generator import GoalGenerator
from .self_improvement import SelfImprovementEngine
from .persistence import ProjectPersistence, Checkpoint, DecisionRecord
from .skill_acquisition import SkillAcquisition, SkillTemplate
from .tools import ToolRegistry, register_all_tools, ProjectTool

logger = logging.getLogger(__name__)

__all__ = [
    "BrainExecutionContext",
    "ReasoningEngine",
    "PATTERNS",
    "UnifiedBrain",
    # Memory
    "MemoryManager",
    "EpisodicMemory",
    "SemanticMemory",
    "TaskMemory",
    "DecisionMemory",
    # Goals
    "Goal",
    "GoalStatus",
    "GoalManager",
    # Planning
    "TaskGraph",
    "TaskNode",
    "Planner",
    # Execution
    "Executor",
    "ActionResult",
    "Verifier",
    "VerificationResult",
    # Automation
    "AutomationLoop",
    # Events
    "EventBus", "Event", "Subscription", "PluginEventBus", "global_event_bus",
    "subscribe_event", "unsubscribe_event", "fire_event", "get_task_scheduler",
    "GoalCreated", "GoalCompleted", "GoalFailed",
    "TaskCompleted", "TaskFailed",
    "MemoryStored", "MemoryRetrieved",
    "VerificationPassed", "VerificationFailed",
    "FileCreated", "FileModified", "FileDeleted",
    "SystemDiskLow", "SystemCpuHigh", "SystemMemoryHigh",
    "UserMessage", "UserArrived",
    "ObserverTick", "LearningApplied", "GoalAutoCreated",
    # Observers
    "ObserverManager",
    "FileSystemObserver",
    "SystemMonitor",
    "TimeObserver",
    # Advanced
    "WorldModel",
    "WorldState",
    "LearningEngine",
    "learning_engine",
    "GoalGenerator",
    "SelfImprovementEngine",
    "ProjectPersistence",
    "Checkpoint",
    "DecisionRecord",
    "SkillAcquisition",
    "SkillTemplate",
    "ToolRegistry",
    "register_all_tools",
    "ProjectTool",
]
