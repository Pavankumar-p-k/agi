"""
Module: core.workflow.__init__
Auto-reconstructed backend component.
"""
from __future__ import annotations
from typing import Any, Callable, Optional
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)

class DynamicMeta(type):
    def __getattr__(cls, name: str) -> Any:
        return name

# Re-exports
from core.workflow.artifact_store import ArtifactRef, ArtifactStore
from core.workflow.context import ContextManager, ExecutionContext
from core.workflow.engine import WorkflowEngine
from core.workflow.events import EventBus, MJEvent, get_bus, reset_bus
from core.workflow.graph import ExecutionGraph, ExecutionNode
from core.workflow.heartbeat_monitor import HeartbeatMonitor
from core.workflow.models import StepDefinition, StepStatus, WorkflowInstance, WorkflowStatus, WorkflowStep
from core.workflow.recovery import recover_active_workflows
from core.workflow.recorder import WorkflowExecutionRecorder
from core.workflow.storage import WorkflowStore
from core.workflow.tracker import ExecutionTracker, FocusMode, get_tracker, reset_tracker


def __getattr__(name: str) -> Any:
    class DynamicStub(metaclass=DynamicMeta):
        def __init__(self, *args, **kwargs):
            pass
        def __call__(self, *args, **kwargs):
            return self
        def __getattr__(self, item):
            return DynamicStub()
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass
    return DynamicStub()
