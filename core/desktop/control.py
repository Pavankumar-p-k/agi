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
        return self._discovery.find_control(title, name, control_type)

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
