"""Desktop AI specialist module implementing the standard SpecialistModule contract.

Provides native Windows desktop interaction, window control, application launching,
and UI automation with deterministic verification and safety guardrails.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

from core.specialist import SpecialistModule, SpecialistResult
from tools.base_tool import (
    CapabilityDefinition,
    CapabilityHealth,
    CapabilityStatus,
    CapabilityType,
    RiskTier,
    VerificationSpec,
)

logger = logging.getLogger(__name__)


class DesktopAI(SpecialistModule):
    """Encapsulated Desktop AI specialist."""

    def __init__(
        self,
        *,
        controller: Any | None = None,
        window_controller: Any | None = None,
        user_actions: Any | None = None,
        adapter_registry: Any | None = None,
    ) -> None:
        if controller is None:
            from core.desktop.controller import desktop_controller
            self.controller = desktop_controller
        else:
            self.controller = controller

        if window_controller is None:
            from core.desktop.window import window_controller as wc
            self.window_controller = wc
        else:
            self.window_controller = window_controller

        if user_actions is None:
            from core.desktop.user_actions import user_actions as ua
            self.user_actions = ua
        else:
            self.user_actions = user_actions

        if adapter_registry is None:
            from core.desktop.adapters import AdapterRegistry, FileExplorerAdapter
            self.adapter_registry = AdapterRegistry([FileExplorerAdapter()])
        else:
            self.adapter_registry = adapter_registry

    @property
    def name(self) -> str:
        return "Desktop AI"

    @property
    def description(self) -> str:
        return (
            "Native Windows automation specialist: window management, UI automation, "
            "keyboard/mouse input, application launching, and desktop state introspection."
        )

    def health_check(self) -> dict[str, Any]:
        """Probes display availability and OS environment."""
        details: dict[str, Any] = {"os": os.name}
        is_healthy = True

        try:
            import pyautogui
            size = pyautogui.size()
            details["display"] = f"{size.width}x{size.height}"
        except Exception as ex:
            details["display_error"] = str(ex)
            is_healthy = False

        try:
            windows = self.window_controller.list_windows()
            details["active_windows_count"] = len(windows)
        except Exception as ex:
            details["window_error"] = str(ex)

        status = CapabilityHealth.HEALTHY if is_healthy else CapabilityHealth.DEGRADED
        return {
            "status": status.value,
            "details": details,
        }

    def get_capabilities(self) -> list[CapabilityDefinition]:
        """Authoritative list of capabilities exported by Desktop AI."""
        return [
            CapabilityDefinition(
                name="desktop.open_project",
                type=CapabilityType.SPECIALIST_ACTION,
                owner_module=self.name,
                description="Open a project directory or file in Explorer or specified application",
                inputs={
                    "path": {"type": "string", "description": "Absolute or relative path to open"},
                    "app": {"type": "string", "description": "Optional application executable/alias"},
                },
                outputs={"success": {"type": "boolean"}, "path": {"type": "string"}},
                requirements=["filesystem", "display"],
                risk=RiskTier.LOW,
                verification=VerificationSpec(method="explorer_or_app_launched"),
                health=CapabilityHealth.HEALTHY,
                health_check=lambda: bool(self.health_check()["status"] in ("healthy", "degraded")),
                handler=self._handle_open_project,
            ),
            CapabilityDefinition(
                name="desktop.launch_app",
                type=CapabilityType.SPECIALIST_ACTION,
                owner_module=self.name,
                description="Launch or focus a desktop application by name or executable alias",
                inputs={"app_name": {"type": "string", "description": "Application name or alias (e.g. 'notepad', 'calc')"}},
                outputs={"success": {"type": "boolean"}, "action": {"type": "string"}},
                requirements=["display"],
                risk=RiskTier.MEDIUM,
                verification=VerificationSpec(method="process_or_window_active"),
                health=CapabilityHealth.HEALTHY,
                handler=self._handle_launch_app,
            ),
            CapabilityDefinition(
                name="desktop.open_url",
                type=CapabilityType.SPECIALIST_ACTION,
                owner_module=self.name,
                description="Open a web URL in the system browser",
                inputs={"url": {"type": "string", "description": "Full HTTP/HTTPS URL"}},
                outputs={"success": {"type": "boolean"}},
                requirements=["network", "browser"],
                risk=RiskTier.LOW,
                verification=VerificationSpec(method="browser_invoked"),
                health=CapabilityHealth.HEALTHY,
                handler=self._handle_open_url,
            ),
            CapabilityDefinition(
                name="desktop.click",
                type=CapabilityType.SPECIALIST_ACTION,
                owner_module=self.name,
                description="Click at screen coordinates (x, y) with safety bounds",
                inputs={
                    "x": {"type": "integer"},
                    "y": {"type": "integer"},
                    "button": {"type": "string", "default": "left"},
                },
                outputs={"success": {"type": "boolean"}},
                requirements=["display", "mouse"],
                risk=RiskTier.MEDIUM,
                risk_tags=["input", "ui"],
                verification=VerificationSpec(method="action_executed"),
                health=CapabilityHealth.HEALTHY,
                handler=self._handle_click,
            ),
            CapabilityDefinition(
                name="desktop.type_text",
                type=CapabilityType.SPECIALIST_ACTION,
                owner_module=self.name,
                description="Type text into the currently active application window",
                inputs={
                    "text": {"type": "string"},
                    "interval": {"type": "number", "default": 0.05},
                },
                outputs={"success": {"type": "boolean"}},
                requirements=["display", "keyboard"],
                risk=RiskTier.MEDIUM,
                risk_tags=["input", "ui"],
                verification=VerificationSpec(method="action_executed"),
                health=CapabilityHealth.HEALTHY,
                handler=self._handle_type_text,
            ),
            CapabilityDefinition(
                name="desktop.press_key",
                type=CapabilityType.SPECIALIST_ACTION,
                owner_module=self.name,
                description="Press a keyboard key or hotkey combination",
                inputs={"key": {"type": "string"}},
                outputs={"success": {"type": "boolean"}},
                requirements=["display", "keyboard"],
                risk=RiskTier.MEDIUM,
                risk_tags=["input", "ui"],
                verification=VerificationSpec(method="action_executed"),
                health=CapabilityHealth.HEALTHY,
                handler=self._handle_press_key,
            ),
            CapabilityDefinition(
                name="desktop.focus_window",
                type=CapabilityType.SPECIALIST_ACTION,
                owner_module=self.name,
                description="Focus an application window matching the title pattern",
                inputs={"window_title": {"type": "string"}},
                outputs={"success": {"type": "boolean"}},
                requirements=["display"],
                risk=RiskTier.LOW,
                verification=VerificationSpec(method="window_active"),
                health=CapabilityHealth.HEALTHY,
                handler=self._handle_focus_window,
            ),
            CapabilityDefinition(
                name="desktop.get_state",
                type=CapabilityType.SPECIALIST_ACTION,
                owner_module=self.name,
                description="Get current desktop snapshot (active window, open windows, processes)",
                inputs={},
                outputs={"windows": {"type": "array"}, "active_window": {"type": "object"}},
                requirements=["display"],
                risk=RiskTier.LOW,
                verification=VerificationSpec(method="state_non_empty"),
                health=CapabilityHealth.HEALTHY,
                handler=self._handle_get_state,
            ),
            CapabilityDefinition(
                name="desktop.discover_controls",
                type=CapabilityType.SPECIALIST_ACTION,
                owner_module=self.name,
                description="Discover accessible UI controls within a target window",
                inputs={"window_title": {"type": "string", "default": ""}},
                outputs={"controls": {"type": "array"}},
                requirements=["display", "pywinauto"],
                risk=RiskTier.LOW,
                verification=VerificationSpec(method="controls_enumerated"),
                health=CapabilityHealth.HEALTHY,
                handler=self._handle_discover_controls,
            ),
        ]

    # Handlers
    def _handle_open_project(self, path: str, app: str | None = None) -> dict[str, Any]:
        explorer = self.adapter_registry.get("explorer")
        if explorer:
            res = explorer.open(path, self.user_actions, app=app)
            return res
        return {"success": False, "error": "No file explorer adapter found"}

    def _handle_launch_app(self, app_name: str) -> dict[str, Any]:
        res = self.controller.launch_app(app_name)
        return {"success": getattr(res, "success", bool(res)), "error": getattr(res, "error", "")}

    def _handle_open_url(self, url: str) -> dict[str, Any]:
        res = self.controller.open_url(url)
        return {"success": getattr(res, "success", bool(res)), "error": getattr(res, "error", "")}

    def _handle_click(self, x: int, y: int, button: str = "left") -> dict[str, Any]:
        res = self.controller.click(x, y, button=button)
        return {"success": getattr(res, "success", bool(res)), "error": getattr(res, "error", "")}

    def _handle_type_text(self, text: str, interval: float = 0.05) -> dict[str, Any]:
        res = self.controller.type_text(text, interval=interval)
        return {"success": getattr(res, "success", bool(res)), "error": getattr(res, "error", "")}

    def _handle_press_key(self, key: str) -> dict[str, Any]:
        res = self.controller.press_key(key)
        return {"success": getattr(res, "success", bool(res)), "error": getattr(res, "error", "")}

    def _handle_focus_window(self, window_title: str) -> dict[str, Any]:
        res = self.controller.focus_window(window_title)
        return {"success": getattr(res, "success", bool(res)), "error": getattr(res, "error", "")}

    def _handle_get_state(self) -> dict[str, Any]:
        windows = self.window_controller.list_windows()
        active = self.window_controller.get_active_window()
        return {
            "success": True,
            "windows": windows,
            "active_window": active,
        }

    def _handle_discover_controls(self, window_title: str = "") -> dict[str, Any]:
        from core.desktop.discovery import create_desktop_discovery
        discovery = create_desktop_discovery(self.window_controller)
        controls = discovery.find_controls(window_title=window_title) if hasattr(discovery, "find_controls") else []
        return {"success": True, "controls": controls}

    def execute_capability(
        self,
        capability_name: str,
        params: dict[str, Any],
        context: Optional[dict[str, Any]] = None,
    ) -> SpecialistResult:
        caps = {cap.name: cap for cap in self.get_capabilities()}
        if capability_name not in caps:
            return SpecialistResult(
                success=False,
                error=f"Capability '{capability_name}' not owned by {self.name}. Available: {list(caps.keys())}",
            )

        cap = caps[capability_name]
        try:
            output = cap.handler(**params) if cap.handler else None
            success = bool(output.get("success", True)) if isinstance(output, dict) else True
            err = output.get("error") if isinstance(output, dict) else None

            res = SpecialistResult(
                success=success,
                output=output,
                error=err,
            )
            verified, reason = self.verify(capability_name, res)
            res.verified = verified
            res.verification_reason = reason
            return res
        except Exception as ex:
            return SpecialistResult(
                success=False,
                error=f"Execution of {capability_name} failed: {ex}",
                verified=False,
                verification_reason="Exception raised during execution",
            )

    def verify(self, capability_name: str, result: SpecialistResult) -> tuple[bool, str]:
        if not result.success:
            return False, f"Execution returned failure: {result.error}"

        if capability_name == "desktop.open_project":
            return True, "Project directory/file opened via adapter"
        elif capability_name in ("desktop.click", "desktop.type_text", "desktop.press_key"):
            return True, "Input action dispatched without safety violation"
        elif capability_name == "desktop.get_state":
            has_data = isinstance(result.output, dict) and "windows" in result.output
            return has_data, "Desktop state retrieved with windows list"
        elif capability_name == "desktop.focus_window":
            return True, "Window focus attempted and reported success"
        elif capability_name == "desktop.launch_app":
            return True, "Application launch dispatched"
        elif capability_name == "desktop.open_url":
            return True, "URL dispatch successful"

        return True, "Verified by default specialist rule"
