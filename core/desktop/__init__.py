"""
Module: core.desktop.__init__
Desktop subsystem re-exports.
"""
from __future__ import annotations
from typing import Any
import logging

logger = logging.getLogger(__name__)

from core.desktop.safety import SafetyManager, SafetyDecision, SafetyConfig, SafetyVerdict, DesktopActionType, ActionType, Rect, safety_manager
from core.desktop.controller import DesktopController, DesktopAction, desktop_controller
from core.desktop.screen import ScreenCapture, CaptureResult, CaptureRegion, screen_capture
from core.desktop.window import WindowController, WindowActionResult, window_controller
from core.desktop.replay import ReplayNode, ReplayGraph, ReplayEdge, NodeType, desktop_replay
from core.desktop.desktop_ai import DesktopAI
from core.desktop.specialist import (
    DesktopActionRecord,
    DesktopExecutionRequest,
    DesktopExecutionResult,
    DesktopExecutionStatus,
    DesktopRecoveryAttempt,
    DesktopSpecialist,
    DesktopVerification,
)
from core.desktop.specialist_state import DesktopLocalState
from core.desktop.tool_bridge import register_desktop_tools


def __getattr__(name: str) -> Any:
    _exports = {
        "SafetyManager": SafetyManager,
        "SafetyDecision": SafetyDecision,
        "SafetyConfig": SafetyConfig,
        "SafetyVerdict": SafetyVerdict,
        "DesktopActionType": DesktopActionType,
        "ActionType": ActionType,
        "Rect": Rect,
        "safety_manager": safety_manager,
        "DesktopController": DesktopController,
        "DesktopAction": DesktopAction,
        "desktop_controller": desktop_controller,
        "ScreenCapture": ScreenCapture,
        "CaptureResult": CaptureResult,
        "CaptureRegion": CaptureRegion,
        "screen_capture": screen_capture,
        "WindowController": WindowController,
        "WindowActionResult": WindowActionResult,
        "window_controller": window_controller,
        "ReplayNode": ReplayNode,
        "ReplayGraph": ReplayGraph,
        "ReplayEdge": ReplayEdge,
        "NodeType": NodeType,
        "desktop_replay": desktop_replay,
        "DesktopAI": DesktopAI,
        "DesktopActionRecord": DesktopActionRecord,
        "DesktopExecutionRequest": DesktopExecutionRequest,
        "DesktopExecutionResult": DesktopExecutionResult,
        "DesktopExecutionStatus": DesktopExecutionStatus,
        "DesktopRecoveryAttempt": DesktopRecoveryAttempt,
        "DesktopSpecialist": DesktopSpecialist,
        "DesktopVerification": DesktopVerification,
        "DesktopLocalState": DesktopLocalState,
        "register_desktop_tools": register_desktop_tools,
    }
    if name in _exports:
        return _exports[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
