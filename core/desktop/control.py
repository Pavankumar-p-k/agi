"""SemanticControlService — find and invoke native controls by name.

Fail-closed: ambiguous matches are refused, unavailable UIA backends
refuse to invoke, and every invocation reports whether the interaction
was verified (no drift recovery was needed).
"""
from __future__ import annotations

from typing import Any, Callable, Optional


class SemanticControlService:
    """Semantic (name-addressed) control access over UI Automation."""

    def __init__(self, discovery: Any,
                 executor: Optional[Callable] = None) -> None:
        self._discovery = discovery
        self._executor = executor

    def find(self, title: str, name: str,
             control_type: Optional[str] = None) -> list:
        """Controls of the window whose name contains *name*."""
        window = self._discovery.discover_window(title)
        if window is None:
            return []
        wanted = str(name).lower()
        matches = [c for c in (getattr(window, "controls", ()) or ())
                   if wanted in str(getattr(c, "name", "")).lower()]
        if control_type:
            matches = [c for c in matches
                       if str(getattr(c, "control_type", "")) == control_type]
        return matches

    def invoke(self, title: str, name: str,
               control_type: Optional[str] = None) -> dict:
        """Invoke a uniquely-matched control; refuse ambiguity."""
        matches = self.find(title, name, control_type)
        if not matches:
            return {"success": False, "verified": False,
                    "error": f"no control matching '{name}' in '{title}'"}
        if len(matches) > 1:
            names = [m.name for m in matches[:5]]
            return {"success": False, "verified": False,
                    "error": f"ambiguous control match ({len(matches)}): {names}"}

        control = matches[0]
        if self._executor is None:
            return {"success": False, "verified": False,
                    "error": "no UIA executor configured"}

        result = self._executor(title, control, "invoke")
        if not isinstance(result, dict):
            result = {"success": False, "verified": False,
                      "error": "executor returned no dict"}
        result.setdefault("control", control.name)
        return result


__all__ = ["SemanticControlService"]
