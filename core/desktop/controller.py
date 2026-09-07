"""
Module: core.desktop.controller
Real desktop automation controller using pyautogui.
"""
from __future__ import annotations
from typing import Any
from dataclasses import dataclass, field
import logging
import pyautogui

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
        logger.info("DesktopController initialized")

    def click(self, x: int, y: int, button: str = "left") -> DesktopAction:
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
        try:
            import subprocess
            subprocess.Popen(app_name, shell=True)
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
