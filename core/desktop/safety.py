"""SafetyManager — the single gate every desktop action must pass.

Gates 1-5 (tests/architecture/test_desktop_gates.py):
- every action type is checked and returns a SafetyDecision;
- emergency stop blocks everything until reset;
- forbidden screen regions cannot be clicked;
- typing rate and text length are limited;
- mouse speed between consecutive moves is limited.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class DesktopActionType(str, Enum):
    MOUSE_MOVE = "mouse_move"
    MOUSE_CLICK = "mouse_click"
    KEYBOARD_TYPE = "keyboard_type"
    SCREEN_CAPTURE = "screen_capture"
    WINDOW_FOCUS = "window_focus"
    WINDOW_MANAGE = "window_manage"


@dataclass
class SafetyDecision:
    allowed: bool
    reason: str = ""

    def __bool__(self) -> bool:  # convenience: `if decision.allowed`
        return self.allowed


# Safety limits (deliberately conservative defaults).
MAX_TYPING_RATE_CHAR_PER_SEC = 30.0
MAX_TYPING_TEXT_LENGTH = 500
DEFAULT_MAX_MOUSE_SPEED_PX_PER_SEC = 5000.0


@dataclass
class _Region:
    x1: int
    y1: int
    x2: int
    y2: int

    def contains(self, x: float, y: float) -> bool:
        return self.x1 <= x <= self.x2 and self.y1 <= y <= self.y2


class SafetyManager:
    """Stateful safety gate for desktop automation."""

    def __init__(self) -> None:
        self.min_cooldown_sec: float = 0.0
        self.max_mouse_speed_px_per_sec: float = DEFAULT_MAX_MOUSE_SPEED_PX_PER_SEC
        self.max_typing_rate_char_per_sec: float = MAX_TYPING_RATE_CHAR_PER_SEC
        self.max_typing_text_length: int = MAX_TYPING_TEXT_LENGTH
        self._forbidden_regions: list[_Region] = []
        self._emergency_stopped: bool = False
        self._last_action_time: Optional[float] = None
        self._last_mouse_pos: Optional[tuple] = None
        # Named limit bundle mirrored on the instance so callers can read
        # the active configuration as `safety.config.max_mouse_speed_px_per_sec`.
        self.config = self

    def get_limits(self) -> dict:
        return {
            "max_mouse_speed_px_per_sec": self.max_mouse_speed_px_per_sec,
            "max_typing_rate_char_per_sec": self.max_typing_rate_char_per_sec,
            "max_typing_text_length": self.max_typing_text_length,
            "min_cooldown_sec": self.min_cooldown_sec,
        }

    # ── emergency control ────────────────────────────────────────────
    def emergency_stop(self) -> None:
        self._emergency_stopped = True

    def emergency_reset(self) -> None:
        self._emergency_stopped = False

    @property
    def emergency_stopped(self) -> bool:
        return self._emergency_stopped

    # ── forbidden regions ────────────────────────────────────────────
    def add_forbidden_region(self, x1: int, y1: int, x2: int, y2: int) -> None:
        self._forbidden_regions.append(_Region(x1, y1, x2, y2))

    def clear_forbidden_regions(self) -> None:
        self._forbidden_regions.clear()

    # ── the gate ─────────────────────────────────────────────────────
    def check(self, action_type: DesktopActionType,
              params: Optional[dict] = None,
              update_state: bool = True) -> SafetyDecision:
        params = dict(params or {})

        if self._emergency_stopped:
            return SafetyDecision(
                allowed=False, reason="Emergency stop is active")

        if action_type in (DesktopActionType.MOUSE_MOVE,
                           DesktopActionType.MOUSE_CLICK):
            return self._check_mouse(action_type, params,
                                     update_state=update_state)
        if action_type is DesktopActionType.KEYBOARD_TYPE:
            return self._check_typing(params, update_state=update_state)
        # SCREEN_CAPTURE / WINDOW_FOCUS / WINDOW_MANAGE carry no rate
        # limits; the permissive branch only updates state when asked.
        if update_state:
            self._mark_action()
        return SafetyDecision(allowed=True, reason="ok")

    # ── per-action checks ────────────────────────────────────────────
    def _check_mouse(self, action_type: DesktopActionType, params: dict,
                     update_state: bool = True) -> SafetyDecision:
        x = params.get("x")
        y = params.get("y")

        if x is not None and y is not None:
            # Gate 3: forbidden regions cannot be clicked (moves pass so
            # the cursor can travel around a protected area).
            if action_type is DesktopActionType.MOUSE_CLICK:
                for region in self._forbidden_regions:
                    if region.contains(x, y):
                        return SafetyDecision(
                            allowed=False,
                            reason="click target is inside a forbidden region")

            # Gate 5: limit cursor speed between consecutive actions.
            decision = self._check_mouse_speed(x, y)
            if not decision.allowed:
                return decision

        if update_state:
            self._mark_action()
            if x is not None and y is not None:
                self._last_mouse_pos = (x, y)
        return SafetyDecision(allowed=True, reason="ok")

    def _check_mouse_speed(self, x: float, y: float) -> SafetyDecision:
        if self._last_mouse_pos is None or self._last_action_time is None:
            return SafetyDecision(allowed=True, reason="ok")
        now = time.time()
        dt = now - self._last_action_time
        lx, ly = self._last_mouse_pos
        distance = math.hypot(x - lx, y - ly)
        speed = distance / dt if dt > 0 else math.inf
        if speed > self.max_mouse_speed_px_per_sec:
            return SafetyDecision(
                allowed=False,
                reason=f"mouse speed {speed:.0f}px/s exceeds limit "
                       f"{self.max_mouse_speed_px_per_sec:.0f}px/s")
        return SafetyDecision(allowed=True, reason="ok")

    def _check_typing(self, params: dict,
                      update_state: bool = True) -> SafetyDecision:
        text = str(params.get("text", ""))
        rate = params.get("rate_char_per_sec") or 0

        if rate and float(rate) > self.max_typing_rate_char_per_sec:
            return SafetyDecision(
                allowed=False,
                reason=f"typing rate {rate} chars/s exceeds limit "
                       f"{self.max_typing_rate_char_per_sec:.0f}")

        if len(text) > self.max_typing_text_length:
            return SafetyDecision(
                allowed=False,
                reason=f"text too long: {len(text)} chars exceeds limit "
                       f"{self.max_typing_text_length}")

        if update_state:
            self._mark_action()
        return SafetyDecision(allowed=True, reason="ok")

    def _mark_action(self) -> None:
        self._last_action_time = time.time()


# Module-level singleton.
safety_manager = SafetyManager()


__all__ = ["DesktopActionType", "SafetyDecision", "SafetyManager",
           "safety_manager"]
