"""DesktopDiscovery — inspect native windows and their UIA controls.

Wraps the UserActions UIA helpers behind a small API with a backend
name, so the agent can honestly report whether UI Automation is
available before promising semantic control access.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class DiscoveredControl:
    name: str = ""
    control_type: str = ""
    automation_id: str = ""
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "control_type": self.control_type,
            "automation_id": self.automation_id,
            "x": self.x, "y": self.y,
            "width": self.width, "height": self.height,
        }


@dataclass
class DiscoveredWindow:
    title: str = ""
    backend: str = ""
    controls: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "backend": self.backend,
            "controls": [c.to_dict() if isinstance(c, DiscoveredControl)
                         else dict(c) for c in self.controls],
        }


class DesktopDiscovery:
    """Window + control discovery through the UserActions UIA layer."""

    def __init__(self, user_actions: Optional[Any] = None,
                 backend_name: str = "uia") -> None:
        if user_actions is None:
            from core.desktop.user_actions import UserActions
            user_actions = UserActions
        self._ua = user_actions
        self.backend_name = backend_name

    def discover_window(self, title: str,
                        include_controls: bool = True) -> Optional[DiscoveredWindow]:
        """Find a window by substring and optionally enumerate controls."""
        wins = self._ua.list_running_apps().get("apps", [])
        match = next((w for w in wins
                      if str(title).lower() in str(w.get("Title", "")).lower()
                      and w.get("Title")), None)
        if match is None:
            return None

        window = DiscoveredWindow(title=str(match["Title"]),
                                  backend=self.backend_name)
        if include_controls:
            snapshot = self.capability_snapshot(match["Title"])
            for ctl in snapshot.get("controls", []):
                window.controls.append(DiscoveredControl(
                    name=str(ctl.get("name", "")),
                    control_type=str(ctl.get("type", "")),
                    automation_id=str(ctl.get("id", "")),
                    x=int(ctl.get("x", 0)), y=int(ctl.get("y", 0)),
                    width=int(ctl.get("width", 0)),
                    height=int(ctl.get("height", 0)),
                ))
        return window

    def capability_snapshot(self, title: str) -> dict:
        """All UIA controls for the best-matching window."""
        wins = self._ua.list_running_apps().get("apps", [])
        match = next((w for w in wins
                      if str(title).lower() in str(w.get("Title", "")).lower()
                      and w.get("Title")), None)
        if match is None:
            return {"success": False,
                    "error": f"no window matching '{title}'"}
        controls = self._ua.list_ui_controls(match["Title"])
        return {
            "success": True,
            "window": match["Title"],
            "backend": self.backend_name,
            "controls": controls.get("controls", []),
        }

    def find_control(self, title: str, name: str,
                     control_type: Optional[str] = None) -> list:
        """Controls whose name matches; unique matches are usable."""
        snapshot = self.capability_snapshot(title)
        wanted = str(name).lower()
        matches = []
        for ctl in snapshot.get("controls", []):
            if wanted not in str(ctl.get("name", "")).lower():
                continue
            if control_type and str(ctl.get("type", "")) != control_type:
                continue
            matches.append(DiscoveredControl(
                name=str(ctl.get("name", "")),
                control_type=str(ctl.get("type", "")),
                automation_id=str(ctl.get("id", "")),
            ))
        return matches


def create_desktop_discovery(window_controller=None) -> DesktopDiscovery:
    """Factory used by the desktop agent; WC is accepted for symmetry."""
    return DesktopDiscovery()


__all__ = ["DesktopDiscovery", "DiscoveredWindow", "DiscoveredControl",
           "create_desktop_discovery"]
