from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


class DesktopActionType(StrEnum):
    MOUSE_MOVE = "mouse_move"
    MOUSE_CLICK = "mouse_click"
    MOUSE_DOUBLE_CLICK = "mouse_double_click"
    MOUSE_SCROLL = "mouse_scroll"
    MOUSE_DRAG = "mouse_drag"
    KEYBOARD_TYPE = "keyboard_type"
    KEYBOARD_PRESS = "keyboard_press"
    KEYBOARD_HOTKEY = "keyboard_hotkey"
    SCREEN_CAPTURE = "screen_capture"
    WINDOW_FOCUS = "window_focus"
    WINDOW_MINIMIZE = "window_minimize"
    WINDOW_MAXIMIZE = "window_maximize"
    WINDOW_RESTORE = "window_restore"
    WINDOW_CLOSE = "window_close"


@dataclass(frozen=True)
class SafetyDecision:
    allowed: bool
    reason: str
    cooldown_remaining: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "cooldown_remaining": self.cooldown_remaining,
            "details": dict(self.details),
        }


@dataclass
class _ActionRecord:
    action_type: DesktopActionType
    timestamp: float
    details: dict[str, Any]


@dataclass
class _Region:
    x: int
    y: int
    width: int
    height: int

    def contains(self, px: int, py: int) -> bool:
        return self.x <= px <= self.x + self.width and self.y <= py <= self.y + self.height


class SafetyManager:
    def __init__(self) -> None:
        self._emergency_stop = False
        self._history: list[_ActionRecord] = []
        self._audit_log: list[dict] = []

        # Limits
        self.max_mouse_speed_px_per_sec: float = 2000.0
        self.max_typing_rate_char_per_sec: float = 30.0
        self.min_cooldown_sec: float = 0.05
        self.max_screenshots_per_min: int = 10
        self.max_clicks_per_min: int = 60

        # Forbidden regions (screen areas that cannot be clicked)
        self._forbidden_regions: list[_Region] = []

        # Cooldown tracking
        self._last_action_time: float = 0.0
        self._last_mouse_pos: tuple[int, int] | None = None

        # Rate tracking
        self._screenshot_times: list[float] = []
        self._click_times: list[float] = []

        # Active window validation (optional)
        self._allowed_window_titles: set[str] | None = None

    # ── Emergency Stop ────────────────────────────────────────────────────

    @property
    def is_emergency_stop(self) -> bool:
        return self._emergency_stop

    def emergency_stop(self) -> None:
        self._emergency_stop = True
        logger.warning("[SafetyManager] EMERGENCY STOP ACTIVATED")
        self._audit("EMERGENCY_STOP", "global", "Emergency stop activated")

    def emergency_reset(self) -> None:
        self._emergency_stop = False
        logger.info("[SafetyManager] Emergency stop reset")
        self._audit("EMERGENCY_RESET", "global", "Emergency stop reset")

    # ── Forbidden Regions ─────────────────────────────────────────────────

    def add_forbidden_region(self, x: int, y: int, width: int, height: int) -> None:
        self._forbidden_regions.append(_Region(x, y, width, height))

    def clear_forbidden_regions(self) -> None:
        self._forbidden_regions.clear()

    # ── Active Window Validation ──────────────────────────────────────────

    def set_allowed_windows(self, titles: set[str] | None) -> None:
        self._allowed_window_titles = titles

    # ── Core Check ────────────────────────────────────────────────────────

    def check(
        self,
        action_type: DesktopActionType,
        details: dict[str, Any] | None = None,
    ) -> SafetyDecision:
        details = details or {}

        # Gate 2: Emergency stop blocks everything
        if self._emergency_stop:
            return SafetyDecision(
                allowed=False,
                reason="Emergency stop is active",
                details={"emergency_stop": True},
            )

        # Cooldown enforcement
        now = time.time()
        elapsed = now - self._last_action_time
        if elapsed < self.min_cooldown_sec and self._last_action_time > 0:
            remaining = round(self.min_cooldown_sec - elapsed, 3)
            return SafetyDecision(
                allowed=False,
                reason=f"Cooldown active: {remaining}s remaining",
                cooldown_remaining=remaining,
                details={"min_cooldown_sec": self.min_cooldown_sec, "elapsed": round(elapsed, 3)},
            )

        # Per-action-type checks
        if action_type in (DesktopActionType.MOUSE_MOVE, DesktopActionType.MOUSE_CLICK,
                           DesktopActionType.MOUSE_DOUBLE_CLICK, DesktopActionType.MOUSE_DRAG):
            result = self._check_mouse(action_type, details)
            if not result.allowed:
                return result

        if action_type in (DesktopActionType.KEYBOARD_TYPE,):
            result = self._check_typing(details)
            if not result.allowed:
                return result

        if action_type == DesktopActionType.SCREEN_CAPTURE:
            result = self._check_screenshot_rate()
            if not result.allowed:
                return result

        if action_type == DesktopActionType.MOUSE_CLICK:
            result = self._check_click_rate()
            if not result.allowed:
                return result

        # Record and audit
        self._history.append(_ActionRecord(
            action_type=action_type,
            timestamp=now,
            details=dict(details),
        ))
        self._last_action_time = now
        self._audit("ALLOW", action_type.value, str(details))

        return SafetyDecision(allowed=True, reason="Allowed by SafetyManager")

    # ── Mouse Checks ──────────────────────────────────────────────────────

    def _check_mouse(
        self,
        action_type: DesktopActionType,
        details: dict[str, Any],
    ) -> SafetyDecision:
        x = details.get("x", -1)
        y = details.get("y", -1)

        # Gate 3: Forbidden screen regions
        for region in self._forbidden_regions:
            if region.contains(x, y):
                return SafetyDecision(
                    allowed=False,
                    reason=f"Position ({x},{y}) is in forbidden region",
                    details={"region": {"x": region.x, "y": region.y,
                                        "width": region.width, "height": region.height}},
                )

        # Gate 5: Mouse movement speed limit
        if action_type == DesktopActionType.MOUSE_MOVE and self._last_mouse_pos:
            prev_x, prev_y = self._last_mouse_pos
            dx = x - prev_x
            dy = y - prev_y
            distance = (dx * dx + dy * dy) ** 0.5
            delta_t = time.time() - self._last_action_time if self._last_action_time > 0 else 0.1
            speed = distance / delta_t if delta_t > 0 else 0
            if speed > self.max_mouse_speed_px_per_sec:
                return SafetyDecision(
                    allowed=False,
                    reason=f"Mouse speed {speed:.0f}px/s exceeds limit {self.max_mouse_speed_px_per_sec}px/s",
                    details={"speed": round(speed), "limit": self.max_mouse_speed_px_per_sec},
                )

        if action_type == DesktopActionType.MOUSE_MOVE:
            self._last_mouse_pos = (x, y)

        return SafetyDecision(allowed=True, reason="Mouse check passed")

    # ── Typing Checks ─────────────────────────────────────────────────────

    def _check_typing(self, details: dict[str, Any]) -> SafetyDecision:
        text = details.get("text", "")
        rate = details.get("rate_char_per_sec", 0)
        if rate > 0 and rate > self.max_typing_rate_char_per_sec:
            return SafetyDecision(
                allowed=False,
                reason=f"Typing rate {rate} char/s exceeds limit {self.max_typing_rate_char_per_sec}",
                details={"rate": rate, "limit": self.max_typing_rate_char_per_sec},
            )
        if len(text) > 500:
            return SafetyDecision(
                allowed=False,
                reason=f"Typing text too long: {len(text)} chars",
                details={"text_length": len(text), "max_length": 500},
            )
        return SafetyDecision(allowed=True, reason="Typing check passed")

    # ── Rate Checks ───────────────────────────────────────────────────────

    def _check_screenshot_rate(self) -> SafetyDecision:
        now = time.time()
        cutoff = now - 60
        self._screenshot_times = [t for t in self._screenshot_times if t > cutoff]
        if len(self._screenshot_times) >= self.max_screenshots_per_min:
            return SafetyDecision(
                allowed=False,
                reason=f"Screenshot rate limit: {self.max_screenshots_per_min}/min",
                details={"count": len(self._screenshot_times), "limit": self.max_screenshots_per_min},
            )
        self._screenshot_times.append(now)
        return SafetyDecision(allowed=True, reason="Screenshot rate OK")

    def _check_click_rate(self) -> SafetyDecision:
        now = time.time()
        cutoff = now - 60
        self._click_times = [t for t in self._click_times if t > cutoff]
        if len(self._click_times) >= self.max_clicks_per_min:
            return SafetyDecision(
                allowed=False,
                reason=f"Click rate limit: {self.max_clicks_per_min}/min",
                details={"count": len(self._click_times), "limit": self.max_clicks_per_min},
            )
        self._click_times.append(now)
        return SafetyDecision(allowed=True, reason="Click rate OK")

    # ── Audit ─────────────────────────────────────────────────────────────

    def _audit(self, result: str, action: str, detail: str) -> None:
        entry = {
            "timestamp": time.time(),
            "result": result,
            "action": action,
            "detail": detail,
        }
        self._audit_log.append(entry)
        logger.debug("[SafetyManager] %s: %s — %s", result, action, detail)

    def get_audit_log(self, limit: int = 100) -> list[dict]:
        return self._audit_log[-limit:]

    def recent_actions(self, limit: int = 20) -> list[dict]:
        return [
            {"type": r.action_type.value, "timestamp": r.timestamp, "details": r.details}
            for r in self._history[-limit:]
        ]

    def clear(self) -> None:
        self._emergency_stop = False
        self._history.clear()
        self._audit_log.clear()
        self._screenshot_times.clear()
        self._click_times.clear()
        self._last_action_time = 0.0
        self._last_mouse_pos = None


safety_manager = SafetyManager()
