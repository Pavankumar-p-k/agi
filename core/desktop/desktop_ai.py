"""DesktopAI — desktop automation specialist facade.

Exposes desktop.* capabilities over the core.desktop stack. Follows
the same contract as BrowserAI: handlers, deterministic verification,
honest results. ``desktop.get_state`` verifies against the OS (a
window enumeration must return a list) so the specialist proves it is
really running on a desktop.
"""
from __future__ import annotations

from typing import Any, Optional

from core.specialist import SpecialistModule, SpecialistResult
from tools.base_tool import (
    CapabilityDefinition,
    CapabilityHealth,
    CapabilityType,
    RiskTier,
    VerificationSpec,
)


class DesktopAI(SpecialistModule):
    name = "Desktop AI"
    description = ("Controls the local desktop: state inspection, app launch, "
                   "mouse/keyboard actions with safety gating.")
    requirements = ["filesystem"]

    def __init__(self) -> None:
        super().__init__()
        from core.desktop.controller import desktop_controller
        from core.desktop.safety import safety_manager
        from core.desktop.window import window_controller
        self.controller = desktop_controller
        self.safety = safety_manager
        self.windows = window_controller

        self._register("desktop.get_state", self._cap_get_state)
        self._register("desktop.launch_app", self._cap_launch_app)
        self._register("desktop.open_project", self._cap_open_project)
        self._register("desktop.open_url", self._cap_open_url)
        self._register("desktop.screenshot", self._cap_screenshot)
        self._register("desktop.click", self._cap_click)
        self._register("desktop.type", self._cap_type)

    # ── contract ─────────────────────────────────────────────────────
    def get_capabilities(self) -> list:
        def cap(name: str, description: str,
                risk: RiskTier = RiskTier.LOW) -> CapabilityDefinition:
            return CapabilityDefinition(
                name=name,
                type=CapabilityType.SPECIALIST_ACTION,
                owner_module=self.name,
                description=description,
                risk=risk,
                requirements=["filesystem"],
                verification=VerificationSpec(method=f"verify:{name}"),
                health=CapabilityHealth.HEALTHY,
            )

        return [
            cap("desktop.get_state", "Inspect desktop state"),
            cap("desktop.launch_app", "Focus or launch an application",
                RiskTier.MEDIUM),
            cap("desktop.open_project", "Open a project folder in the file manager"),
            cap("desktop.open_url", "Open a URL in the default browser",
                RiskTier.MEDIUM),
            cap("desktop.screenshot", "Capture the screen"),
            cap("desktop.click", "Click at coordinates", RiskTier.HIGH),
            cap("desktop.type", "Type text", RiskTier.MEDIUM),
        ]

    def verify(self, output: Any) -> bool:
        if not isinstance(output, dict):
            return False
        return output.get("success") is True

    def health_check(self) -> dict:
        try:
            state = self._cap_get_state()
            return {"status": "healthy" if state.get("success") else "unhealthy",
                    "specialist": self.name}
        except Exception:  # noqa: BLE001
            return {"status": "unknown", "specialist": self.name}

    def execute_capability(self, name, params=None) -> SpecialistResult:
        result = super().execute_capability(name, params)
        # Desktop actions must be verified against the OS, not just the
        # handler dict: a state query is only verified when the window
        # enumeration actually returns a list.
        if name == "desktop.get_state" and result.success:
            result.verified = isinstance(
                (result.output or {}).get("windows"), list)
        return result

    # ── capability handlers ──────────────────────────────────────────
    def _cap_get_state(self) -> dict:
        windows = self.windows.list_windows()
        return {
            "success": True,
            "windows": windows,
            "window_count": len(windows),
            "os": self._os_name(),
            "emergency_stopped": getattr(self.safety, "emergency_stopped", False),
        }

    @staticmethod
    def _os_name() -> str:
        import platform
        return platform.system().lower()

    def _cap_launch_app(self, app: str) -> dict:
        from core.desktop.controller import DesktopAction
        from core.desktop.safety import DesktopActionType
        result = self.controller.perform(DesktopAction(
            DesktopActionType.WINDOW_MANAGE, {"window_title": str(app)}))
        return {"success": result.success, "app": str(app),
                "error": result.reason if not result.success else ""}

    def _cap_open_project(self, path: str) -> dict:
        try:
            import subprocess
            subprocess.Popen(["explorer", str(path)])
            return {"success": True, "path": str(path)}
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "error": str(exc)}

    def _cap_open_url(self, url: str) -> dict:
        from core.desktop.controller import DesktopAction
        from core.desktop.safety import DesktopActionType
        result = self.controller.perform(DesktopAction(
            DesktopActionType.WINDOW_MANAGE, {"window_title": str(url)}))
        if result.success:
            import webbrowser
            webbrowser.open(str(url))
        return {"success": result.success, "url": str(url),
                "error": result.reason if not result.success else ""}

    def _cap_screenshot(self, path: Optional[str] = None) -> dict:
        from core.desktop.controller import DesktopAction
        from core.desktop.safety import DesktopActionType
        result = self.controller.perform(DesktopAction(
            DesktopActionType.SCREEN_CAPTURE, {"path": path or ""}))
        return {"success": result.success, "error": result.reason}

    def _cap_click(self, x: int, y: int) -> dict:
        result = self.controller.click(int(x), int(y))
        return {"success": result.success, "error": result.error or result.reason}

    def _cap_type(self, text: str) -> dict:
        result = self.controller.type_text(str(text))
        return {"success": result.success, "error": result.error or result.reason}


__all__ = ["DesktopAI"]
