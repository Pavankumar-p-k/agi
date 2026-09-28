"""core.desktop — desktop automation with safety-first gating.

Layout:
- safety:     SafetyManager — the single gate every action passes;
- controller: DesktopController — check -> replay -> act;
- replay:     ReplayGraph — append-only audit chain of actions;
- screen:     ScreenCapture — screenshots as artifacts;
- window:     WindowController — window focus/list/minimize;
- desktop_ai: DesktopAI — specialist facade over this package.
"""
from core.desktop.safety import (
    DesktopActionType,
    SafetyDecision,
    SafetyManager,
    safety_manager,
)
from core.desktop.controller import (
    ActionResult,
    DesktopAction,
    DesktopController,
    desktop_controller,
)
from core.desktop.replay import (
    ReplayGraph,
    ReplayNode,
    desktop_replay,
)
from core.desktop.screen import (
    CaptureResult,
    ScreenCapture,
    screen_capture,
)
from core.desktop.window import (
    WindowActionResult,
    WindowController,
    window_controller,
)

__all__ = [
    "DesktopActionType", "SafetyDecision", "SafetyManager", "safety_manager",
    "ActionResult", "DesktopAction", "DesktopController", "desktop_controller",
    "ReplayGraph", "ReplayNode", "desktop_replay",
    "CaptureResult", "ScreenCapture", "screen_capture",
    "WindowActionResult", "WindowController", "window_controller",
    "DesktopAI",
]


def __getattr__(name: str):
    # Lazy import: desktop_ai pulls in core.specialist, keeping this
    # package import-light for the pipeline.
    if name == "DesktopAI":
        from core.desktop.desktop_ai import DesktopAI
        return DesktopAI
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
