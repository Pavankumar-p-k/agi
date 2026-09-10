"""
Module: core.desktop.controller
Real desktop automation controller using pyautogui.
"""
from __future__ import annotations
from typing import Any
from dataclasses import dataclass, field
import logging
import pyautogui
from core.desktop.safety import DesktopActionType, SafetyManager

logger = logging.getLogger(__name__)

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.05


@dataclass
class DesktopAction:
    action_type: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    success: bool = False
    error: str = ""
    details: dict[str, Any] = field(default_factory=dict)


class DesktopController:
    def __init__(self) -> None:
        self._mouse_position = (0, 0)
        self.safety = SafetyManager()
        logger.info("DesktopController initialized")

    def _guard(self, action_type: DesktopActionType, params: dict[str, Any]) -> DesktopAction | None:
        if action_type in (
            DesktopActionType.MOUSE_MOVE,
            DesktopActionType.MOUSE_CLICK,
            DesktopActionType.MOUSE_DOUBLE_CLICK,
            DesktopActionType.MOUSE_DRAG,
        ):
            try:
                self.safety.sync_mouse_position(tuple(pyautogui.position()))
            except Exception:
                pass
        decision = self.safety.check(action_type, params)
        if not decision.allowed:
            return DesktopAction(action_type=action_type.value, params=params, error=decision.reason)
        return None

    def click(self, x: int, y: int, button: str = "left") -> DesktopAction:
        if not isinstance(x, int) or not isinstance(y, int):
            return DesktopAction(action_type="click", error="x and y must be integers")
        blocked = self._guard(DesktopActionType.MOUSE_CLICK, {"x": x, "y": y, "button": button})
        if blocked:
            return blocked
        try:
            pyautogui.click(x=x, y=y, button=button)
            self._mouse_position = (x, y)
            return DesktopAction(
                action_type="click",
                params={"x": x, "y": y, "button": button},
                success=True,
                details={"clicked": True},
            )
        except Exception as e:
            return DesktopAction(action_type="click", error=str(e))

    def double_click(self, x: int, y: int) -> DesktopAction:
        blocked = self._guard(DesktopActionType.MOUSE_DOUBLE_CLICK, {"x": x, "y": y})
        if blocked:
            return blocked
        try:
            pyautogui.doubleClick(x=x, y=y)
            self._mouse_position = (x, y)
            return DesktopAction(
                action_type="double_click",
                params={"x": x, "y": y},
                success=True,
                details={"double_clicked": True},
            )
        except Exception as e:
            return DesktopAction(action_type="double_click", error=str(e))

    def right_click(self, x: int, y: int) -> DesktopAction:
        blocked = self._guard(DesktopActionType.MOUSE_CLICK, {"x": x, "y": y, "button": "right"})
        if blocked:
            return blocked
        try:
            pyautogui.rightClick(x=x, y=y)
            self._mouse_position = (x, y)
            return DesktopAction(
                action_type="right_click",
                params={"x": x, "y": y},
                success=True,
                details={"right_clicked": True},
            )
        except Exception as e:
            return DesktopAction(action_type="right_click", error=str(e))

    def move_mouse(self, x: int, y: int) -> DesktopAction:
        if not isinstance(x, int) or not isinstance(y, int):
            return DesktopAction(action_type="move_mouse", error="x and y must be integers")
        blocked = self._guard(DesktopActionType.MOUSE_MOVE, {"x": x, "y": y})
        if blocked:
            return blocked
        try:
            pyautogui.moveTo(x=x, y=y)
            self._mouse_position = (x, y)
            return DesktopAction(
                action_type="move_mouse",
                params={"x": x, "y": y},
                success=True,
                details={"moved": True},
            )
        except Exception as e:
            return DesktopAction(action_type="move_mouse", error=str(e))

    def drag(self, from_x: int, from_y: int, to_x: int, to_y: int, duration: float = 0.5) -> DesktopAction:
        if not all(isinstance(value, int) for value in (from_x, from_y, to_x, to_y)):
            return DesktopAction(action_type="drag", error="drag coordinates must be integers")
        if not isinstance(duration, (int, float)) or duration < 0:
            return DesktopAction(action_type="drag", error="duration must be non-negative")
        distance = ((to_x - from_x) ** 2 + (to_y - from_y) ** 2) ** 0.5
        max_speed = min(self.safety.max_mouse_speed_px_per_sec,
                        self.safety.config.max_mouse_speed_px_per_sec)
        if max_speed > 0 and duration < distance / max_speed:
            return DesktopAction(
                action_type="drag",
                error=f"Drag duration {duration:.3f}s is too short for {distance:.0f}px at the safety limit",
            )
        self.safety.sync_mouse_position((from_x, from_y))
        origin = self.safety.check(
            DesktopActionType.MOUSE_DRAG,
            {"x": from_x, "y": from_y, "from_x": from_x, "from_y": from_y},
            update_state=False,
        )
        if not origin.allowed:
            return DesktopAction(action_type="drag", error=origin.reason)
        # The OS cursor is moved to the drag origin by pyautogui immediately
        # before the gesture; validate the gesture speed using its duration.
        self.safety.sync_mouse_position((to_x, to_y))
        destination = self.safety.check(
            DesktopActionType.MOUSE_DRAG,
            {"x": to_x, "y": to_y, "from_x": from_x, "from_y": from_y},
        )
        if not destination.allowed:
            return DesktopAction(action_type="drag", error=destination.reason)
        try:
            pyautogui.moveTo(from_x, from_y)
            pyautogui.drag(to_x - from_x, to_y - from_y, duration=duration)
            self._mouse_position = (to_x, to_y)
            return DesktopAction(
                action_type="drag",
                params={"from_x": from_x, "from_y": from_y, "to_x": to_x, "to_y": to_y},
                success=True,
                details={"dragged": True},
            )
        except Exception as e:
            return DesktopAction(action_type="drag", error=str(e))

    def type_text(self, text: str, interval: float = 0.05) -> DesktopAction:
        if not isinstance(text, str) or not isinstance(interval, (int, float)) or interval < 0:
            return DesktopAction(action_type="type_text", error="text must be a string and interval must be non-negative")
        rate = 1.0 / interval if interval > 0 else float("inf")
        blocked = self._guard(DesktopActionType.KEYBOARD_TYPE, {"text": text, "rate_char_per_sec": rate})
        if blocked:
            return blocked
        try:
            pyautogui.typewrite(text, interval=interval)
            return DesktopAction(
                action_type="type_text",
                params={"text_length": len(text)},
                success=True,
                details={"typed": True},
            )
        except Exception as e:
            return DesktopAction(action_type="type_text", error=str(e))

    def press_key(self, key: str) -> DesktopAction:
        if not isinstance(key, str) or not key:
            return DesktopAction(action_type="press_key", error="key must be a non-empty string")
        blocked = self._guard(DesktopActionType.KEYBOARD_HOTKEY, {"text": [key]})
        if blocked:
            return blocked
        try:
            pyautogui.press(key)
            return DesktopAction(
                action_type="press_key",
                params={"key": key},
                success=True,
                details={"pressed": True},
            )
        except Exception as e:
            return DesktopAction(action_type="press_key", error=str(e))

    def hotkey(self, *keys: str) -> DesktopAction:
        blocked = self._guard(DesktopActionType.KEYBOARD_HOTKEY, {"text": list(keys)})
        if blocked:
            return blocked
        try:
            pyautogui.hotkey(*keys)
            return DesktopAction(
                action_type="hotkey",
                params={"keys": list(keys)},
                success=True,
                details={"hotkey": True},
            )
        except Exception as e:
            return DesktopAction(action_type="hotkey", error=str(e))

    def scroll(self, clicks: int, x: int | None = None, y: int | None = None) -> DesktopAction:
        blocked = self._guard(DesktopActionType.MOUSE_MOVE, {"x": x, "y": y} if x is not None and y is not None else {})
        if blocked:
            return blocked
        try:
            pyautogui.scroll(clicks, x=x, y=y)
            return DesktopAction(
                action_type="scroll",
                params={"clicks": clicks, "x": x, "y": y},
                success=True,
                details={"scrolled": True},
            )
        except Exception as e:
            return DesktopAction(action_type="scroll", error=str(e))

    def open_url(self, url: str) -> DesktopAction:
        blocked = self._guard(DesktopActionType.WINDOW_MANAGE, {"url": url})
        if blocked:
            return blocked
        try:
            import webbrowser
            webbrowser.open(url)
            return DesktopAction(
                action_type="open_url",
                params={"url": url},
                success=True,
                details={"opened": True},
            )
        except Exception as e:
            return DesktopAction(action_type="open_url", error=str(e))

    def launch_app(self, app_name: str) -> DesktopAction:
        blocked = self._guard(DesktopActionType.WINDOW_MANAGE, {"app_name": app_name})
        if blocked:
            return blocked
        try:
            import subprocess
            import os
            if os.name == "nt" and hasattr(os, "startfile") and not __import__("shutil").which(app_name):
                os.startfile(app_name)
            else:
                subprocess.Popen([app_name], shell=False)
            return DesktopAction(
                action_type="launch_app",
                params={"app_name": app_name},
                success=True,
                details={"launched": True},
            )
        except Exception as e:
            return DesktopAction(action_type="launch_app", error=str(e))

    def desktop_state(self) -> DesktopAction:
        try:
            screen_w, screen_h = pyautogui.size()
            mx, my = pyautogui.position()
            return DesktopAction(
                action_type="desktop_state",
                success=True,
                details={
                    "screen_width": screen_w,
                    "screen_height": screen_h,
                    "mouse_x": mx,
                    "mouse_y": my,
                },
            )
        except Exception as e:
            return DesktopAction(action_type="desktop_state", error=str(e))

    def focus_window(self, title: str) -> DesktopAction:
        blocked = self._guard(DesktopActionType.WINDOW_FOCUS, {"window_title": title})
        if blocked:
            return blocked
        try:
            import pygetwindow as gw
            windows = gw.getWindowsWithTitle(title)
            if not windows:
                return DesktopAction(
                    action_type="focus_window",
                    params={"window_title": title},
                    error=f"No window found with title: {title}",
                )
            win = windows[0]
            if win.isMinimized:
                win.restore()
            win.activate()
            return DesktopAction(
                action_type="focus_window",
                params={"window_title": title},
                success=True,
                details={"focused": True, "window_title": win.title},
            )
        except Exception as e:
            return DesktopAction(action_type="focus_window", error=str(e))

    def get_mouse_position(self) -> tuple[int, int]:
        return pyautogui.position()

    def get_screen_size(self) -> tuple[int, int]:
        return pyautogui.size()


desktop_controller = DesktopController()
