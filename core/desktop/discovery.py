"""DesktopDiscovery — inspect native windows and their UIA controls.

Windows are enumerated through an injected window controller or, by
default, pygetwindow. Control metadata comes from the UserActions UIA
layer behind a backend name, so the agent can honestly report whether
UI Automation is available before promising semantic control access.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Tuple


@dataclass
class ControlInfo:
    """A single UIA control with the patterns it supports."""

    name: str = ""
    control_type: str = ""
    automation_id: str = ""
    patterns: Tuple[str, ...] = ()
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "control_type": self.control_type,
            "automation_id": self.automation_id,
            "patterns": self.patterns,
            "x": self.x, "y": self.y,
            "width": self.width, "height": self.height,
        }


@dataclass
class WindowInfo:
    """A discovered native window and its controls."""

    title: str = ""
    backend: str = "uia"
    bounds: dict = field(default_factory=lambda: {"left": 0, "top": 0,
                                                  "width": 0, "height": 0})
    controls: Tuple[ControlInfo, ...] = ()
    is_active: bool = False

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "backend": self.backend,
            "bounds": dict(self.bounds),
            "controls": [c.to_dict() for c in self.controls],
            "is_active": self.is_active,
        }


class DesktopDiscovery:
    """Window + control discovery with an injectable window controller."""

    def __init__(self, user_actions: Optional[Any] = None,
                 backend_name: str = "uia",
                 max_controls: int = 50,
                 window_controller: Optional[Any] = None) -> None:
        if max_controls <= 0:
            raise ValueError("max_controls must be a positive integer")
        self._ua = user_actions
        self.backend_name = backend_name
        self.max_controls = max_controls
        self._window_controller = window_controller

    # ── window enumeration ───────────────────────────────────────────
    def _iter_windows(self) -> list:
        """Normalized window dicts: title/left/top/width/height/isActive."""
        if self._window_controller is not None:
            try:
                raw = self._window_controller.list_windows()
            except Exception:  # noqa: BLE001 - controller failure = no windows
                return []
            return [dict(w) for w in raw if str(w.get("title", "")).strip()]
        return self._pygetwindow_windows()

    @staticmethod
    def _pygetwindow_windows() -> list:
        try:
            import pygetwindow as gw
            raw = gw.getAllWindows()
        except ImportError:
            return []
        except Exception:  # noqa: BLE001 - enumeration failure = no windows
            return []
        windows: list = []
        for w in raw:
            title = str(getattr(w, "title", "") or "")
            if not title.strip():
                continue
            windows.append({
                "title": title,
                "left": int(getattr(w, "left", 0) or 0),
                "top": int(getattr(w, "top", 0) or 0),
                "width": int(getattr(w, "width", 0) or 0),
                "height": int(getattr(w, "height", 0) or 0),
                "isActive": bool(getattr(w, "isActive", False)),
            })
        return windows

    @staticmethod
    def _match_window(windows: list, title: str) -> Optional[dict]:
        needle = str(title).lower()
        return next((w for w in windows
                     if needle in str(w.get("title", "")).lower()), None)

    # ── public API ───────────────────────────────────────────────────
    def discover_window(self, title: str,
                        include_controls: bool = True) -> Optional[WindowInfo]:
        """Find a window by substring and optionally enumerate controls."""
        match = self._match_window(self._iter_windows(), title)
        if match is None:
            return None

        window = WindowInfo(
            title=str(match.get("title", "")),
            backend=self.backend_name,
            bounds={
                "left": int(match.get("left", 0) or 0),
                "top": int(match.get("top", 0) or 0),
                "width": int(match.get("width", 0) or 0),
                "height": int(match.get("height", 0) or 0),
            },
            is_active=bool(match.get("isActive", False)),
        )
        if include_controls:
            snapshot = self.capability_snapshot(window.title)
            window.controls = tuple(
                ControlInfo(
                    name=str(ctl.get("name", "")),
                    control_type=str(ctl.get("type", "")),
                    automation_id=str(ctl.get("id", "")),
                )
                for ctl in snapshot.get("controls", [])[: self.max_controls]
            )
        return window

    def capability_snapshot(self, title: str) -> dict:
        """All UIA controls for the best-matching window."""
        match = self._match_window(self._iter_windows(), title)
        if match is None:
            return {"found": False,
                    "success": False,
                    "error": f"no window matching '{title}'"}
        controls = self._enumerate_controls(str(match.get("title", "")))
        return {
            "found": True,
            "success": True,
            "window": match.get("title", ""),
            "backend": self.backend_name,
            "controls": controls,
        }

    def _enumerate_controls(self, window_title: str) -> list:
        if self._ua is None:
            try:
                from core.desktop.user_actions import UserActions
                self._ua = UserActions
            except Exception:  # noqa: BLE001 - UIA unavailable = no controls
                return []
        try:
            return list(self._ua.list_ui_controls(window_title)
                        .get("controls", []))[: self.max_controls]
        except Exception:  # noqa: BLE001 - UIA failure = no controls
            return []

    def find_control(self, title: str, name: str,
                     control_type: Optional[str] = None) -> list:
        """Controls whose name matches; unique matches are usable."""
        snapshot = self.capability_snapshot(title)
        wanted = str(name).lower()
        matches: list = []
        for ctl in snapshot.get("controls", []):
            if wanted not in str(ctl.get("name", "")).lower():
                continue
            if control_type and str(ctl.get("type", "")) != control_type:
                continue
            matches.append(ControlInfo(
                name=str(ctl.get("name", "")),
                control_type=str(ctl.get("type", "")),
                automation_id=str(ctl.get("id", "")),
            ))
        return matches


def create_desktop_discovery(window_controller=None) -> DesktopDiscovery:
    """Factory used by the desktop agent."""
    return DesktopDiscovery(window_controller=window_controller)


__all__ = ["DesktopDiscovery", "WindowInfo", "ControlInfo",
           "create_desktop_discovery"]
