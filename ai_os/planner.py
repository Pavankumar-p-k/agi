from __future__ import annotations

from typing import Any

from jarvis_os.core.planner import PlanningEngine


class Planner:
    """
    Legacy adapter that delegates planning authority to canonical planner.
    """

    def __init__(self, planner: PlanningEngine | None = None, **_: Any) -> None:
        self._planner = planner

    def build_plan(self, *args: Any, **kwargs: Any) -> Any:
        if self._planner is None:
            raise RuntimeError("Canonical planner is required for ai_os Planner adapter.")
        return self._planner.build_plan(*args, **kwargs)


__all__ = ["Planner"]