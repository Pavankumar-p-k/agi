from __future__ import annotations

from core.legacy.control_loop import control_loop


class JarvisDaemon:
    def __init__(self) -> None:
        self.running = False

    async def _check_projects(self) -> list[str]:
        return await control_loop.run_pending()
