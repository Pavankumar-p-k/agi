from __future__ import annotations

from core.project_state import ProjectState, list_projects


class ControlLoop:
    def __init__(self) -> None:
        self.running_builds: dict[str, ProjectState] = {}

    async def run_pending(self) -> list[str]:
        pending: list[str] = []
        for state in list_projects():
            if state.status in {"building", "fixing", "paused", "running"}:
                state.status = "running"
                state.save()
                self.running_builds[state.project_name] = state
                pending.append(state.project_name)
        return pending

    async def resume_build(self, project_name: str) -> ProjectState | None:
        state = ProjectState.load(project_name)
        if state is None:
            return None
        state.status = "running"
        state.save()
        self.running_builds[project_name] = state
        return state


control_loop = ControlLoop()
