"""
Module: core.desktop.safety
Desktop safety enforcement: forbidden regions, rate gates, emergency stop.
"""
from __future__ import annotations
from typing import Any, Optional
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timezone
import time as _time
import logging
import math

logger = logging.getLogger(__name__)


class SafetyVerdict(Enum):
    PASS = "pass"
    BLOCK = "block"
    ESCALATE = "escalate"
    EMERGENCY_STOP = "emergency_stop"


class DesktopActionType(Enum):
    MOUSE_MOVE = "mouse_move"
    MOUSE_CLICK = "mouse_click"
    MOUSE_DOUBLE_CLICK = "mouse_double_click"
    MOUSE_DRAG = "mouse_drag"
    KEYBOARD_TYPE = "keyboard_type"
    KEYBOARD_HOTKEY = "keyboard_hotkey"
    SCREEN_CAPTURE = "screen_capture"
    WINDOW_MANAGE = "window_manage"
    WINDOW_FOCUS = "window_focus"
    REPLAY_EXECUTE = "replay_execute"


ActionType = DesktopActionType


@dataclass
class Rect:
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0

    def contains(self, px: int, py: int) -> bool:
        return self.x <= px < self.x + self.width and self.y <= py < self.y + self.height

    def to_dict(self) -> dict[str, int]:
        return {"x": self.x, "y": self.y, "width": self.width, "height": self.height}


@dataclass
class SafetyDecision:
    verdict: SafetyVerdict = SafetyVerdict.PASS
    action_type: DesktopActionType = DesktopActionType.MOUSE_MOVE
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def allowed(self) -> bool:
        return self.verdict == SafetyVerdict.PASS

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "action_type": self.action_type.value,
            "reason": self.reason,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
            "allowed": self.allowed,
        }


@dataclass
class SafetyConfig:
    forbidden_regions: list[Rect] = field(default_factory=list)
    allowed_regions: list[Rect] = field(default_factory=list)
    max_mouse_speed_px_per_sec: float = 5000.0
    max_typing_chars_per_sec: float = 100.0
    max_typing_text_length: int = 500
    max_hotkey_combo_length: int = 5
    emergency_stop_enabled: bool = False
    blocked_action_types: set[DesktopActionType] = field(default_factory=set)
    blocked_requesters: set[str] = field(default_factory=set)

    def to_dict(self) -> dict[str, Any]:
        return {
            "forbidden_regions": [r.to_dict() for r in self.forbidden_regions],
            "allowed_regions": [r.to_dict() for r in self.allowed_regions],
            "max_mouse_speed_px_per_sec": self.max_mouse_speed_px_per_sec,
            "max_typing_chars_per_sec": self.max_typing_chars_per_sec,
            "max_typing_text_length": self.max_typing_text_length,
            "max_hotkey_combo_length": self.max_hotkey_combo_length,
            "emergency_stop_enabled": self.emergency_stop_enabled,
            "blocked_action_types": [a.value for a in self.blocked_action_types],
        }


@dataclass
class SafetyManager:
    config: SafetyConfig = field(default_factory=SafetyConfig)
    _action_timestamps: dict[str, list[str]] = field(default_factory=dict)
    _violation_log: list[dict[str, Any]] = field(default_factory=list)

    min_cooldown_sec: float = 0.0
    max_mouse_speed_px_per_sec: float = 5000.0
    _last_action_time: float = field(default_factory=_time.time)
    _last_mouse_action_time: float = field(default_factory=_time.time)
    _last_mouse_pos: tuple[int, int] = (0, 0)

    def check(
        self,
        action_type: DesktopActionType,
        params: dict[str, Any] | None = None,
        *,
        update_state: bool = True,
    ) -> SafetyDecision:
        params = params or {}

        if self.config.emergency_stop_enabled:
            return self._emergency_stop(action_type, params)

        requester = params.get("requester", "")
        if requester and requester in self.config.blocked_requesters:
            return self._deny(action_type, f"Requester '{requester}' is blocked", params)

        if action_type in self.config.blocked_action_types:
            return self._deny(action_type, f"Action type '{action_type.value}' is blocked", params)

        now = _time.time()
        if self.min_cooldown_sec > 0 and now - self._last_action_time < self.min_cooldown_sec:
            return self._deny(action_type, "Minimum action cooldown has not elapsed", params)

        x = params.get("x")
        y = params.get("y")
        position = (x, y) if x is not None and y is not None else None

        if position:
            region_check = self._check_forbidden_regions(*position)
            if region_check:
                return self._deny(action_type, region_check, params)

        if position and self.config.allowed_regions:
            allowed = any(r.contains(*position) for r in self.config.allowed_regions)
            if not allowed:
                return self._deny(action_type, f"Position {position} not in any allowed region", params)

        if action_type in (DesktopActionType.MOUSE_MOVE, DesktopActionType.MOUSE_DRAG):
            if position:
                speed = self._compute_mouse_speed(position)
                max_speed = min(self.max_mouse_speed_px_per_sec, self.config.max_mouse_speed_px_per_sec)
                if speed > max_speed:
                    return self._deny(action_type, f"Mouse speed {speed:.0f} exceeds max {max_speed:.0f} px/sec", params)
                if update_state:
                    self._last_mouse_pos = position
                    self._last_mouse_action_time = _time.time()

        if action_type == DesktopActionType.KEYBOARD_TYPE:
            text = params.get("text", "")
            rate = params.get("rate_char_per_sec", 0)
            if len(text) > self.config.max_typing_text_length:
                return self._deny(action_type, f"Text too long: {len(text)} chars (max {self.config.max_typing_text_length})", params)
            if rate >= self.config.max_typing_chars_per_sec:
                return self._deny(action_type, f"Typing rate {rate} chars/sec exceeds max {self.config.max_typing_chars_per_sec}", params)

        if action_type == DesktopActionType.KEYBOARD_HOTKEY:
            text = params.get("text", "")
            if len(text) > self.config.max_hotkey_combo_length:
                return self._deny(action_type, f"Hotkey combo length {len(text)} exceeds max {self.config.max_hotkey_combo_length}", params)

        if update_state:
            self._last_action_time = now
        return SafetyDecision(verdict=SafetyVerdict.PASS, action_type=action_type, reason="All safety checks passed", metadata=params)

    def _compute_mouse_speed(self, current_pos: tuple[int, int]) -> float:
        now = _time.time()
        timestamp = self._last_mouse_action_time
        # Preserve compatibility with callers that seed _last_action_time directly.
        if self._last_action_time < timestamp:
            timestamp = self._last_action_time
        dt = now - timestamp
        if dt <= 0:
            return 0.0
        dx = current_pos[0] - self._last_mouse_pos[0]
        dy = current_pos[1] - self._last_mouse_pos[1]
        dist = math.sqrt(dx * dx + dy * dy)
        return dist / dt

    def sync_mouse_position(self, position: tuple[int, int] | None = None) -> None:
        """Synchronize safety state after the user or another app moves the cursor."""
        if position is None:
            return
        self._last_mouse_pos = position
        self._last_mouse_action_time = _time.time()

    def _check_forbidden_regions(self, x: int, y: int) -> str | None:
        for region in self.config.forbidden_regions:
            if region.contains(x, y):
                return f"Position ({x}, {y}) is in forbidden region {region.to_dict()}"
        return None

    def _emergency_stop(self, action_type: DesktopActionType, params: dict[str, Any]) -> SafetyDecision:
        reason = f"Emergency stop active; action '{action_type.value}' blocked"
        self._violation_log.append({
            "action_type": action_type.value,
            "reason": reason,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        logger.critical("EMERGENCY STOP: %s", action_type.value)
        return SafetyDecision(verdict=SafetyVerdict.EMERGENCY_STOP, action_type=action_type, reason=reason, metadata=params)

    def _deny(self, action_type: DesktopActionType, reason: str, params: dict[str, Any]) -> SafetyDecision:
        self._violation_log.append({
            "action_type": action_type.value,
            "reason": reason,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        logger.warning("Safety DENY: %s - %s", action_type.value, reason)
        return SafetyDecision(verdict=SafetyVerdict.BLOCK, action_type=action_type, reason=reason, metadata=params)

    def emergency_stop(self) -> None:
        self.config.emergency_stop_enabled = True
        logger.critical("Emergency stop ACTIVATED")

    def emergency_reset(self) -> None:
        self.config.emergency_stop_enabled = False
        logger.info("Emergency stop DEACTIVATED")

    trigger_emergency_stop = emergency_stop
    reset_emergency_stop = emergency_reset

    def add_forbidden_region(self, x: int, y: int, width: int, height: int) -> Rect:
        region = Rect(x=x, y=y, width=width, height=height)
        self.config.forbidden_regions.append(region)
        return region

    def remove_forbidden_region(self, x: int, y: int, width: int, height: int) -> bool:
        before = len(self.config.forbidden_regions)
        self.config.forbidden_regions = [
            r for r in self.config.forbidden_regions
            if not (r.x == x and r.y == y and r.width == width and r.height == height)
        ]
        return len(self.config.forbidden_regions) < before

    def clear_forbidden_regions(self) -> int:
        count = len(self.config.forbidden_regions)
        self.config.forbidden_regions.clear()
        return count

    def block_requester(self, requester: str) -> None:
        self.config.blocked_requesters.add(requester)

    def unblock_requester(self, requester: str) -> bool:
        before = len(self.config.blocked_requesters)
        self.config.blocked_requesters.discard(requester)
        return len(self.config.blocked_requesters) < before

    def block_action_type(self, action_type: DesktopActionType) -> None:
        self.config.blocked_action_types.add(action_type)

    def unblock_action_type(self, action_type: DesktopActionType) -> bool:
        before = len(self.config.blocked_action_types)
        self.config.blocked_action_types.discard(action_type)
        return len(self.config.blocked_action_types) < before

    def violation_log(self, limit: int = 50) -> list[dict[str, Any]]:
        return self._violation_log[-limit:]

    def to_dict(self) -> dict[str, Any]:
        return {
            "config": self.config.to_dict(),
            "violations_count": len(self._violation_log),
            "recent_violations": self._violation_log[-5:],
        }


def safety_manager(**kwargs: Any) -> SafetyManager:
    return SafetyManager(**kwargs)
