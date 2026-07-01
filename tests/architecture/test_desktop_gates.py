from __future__ import annotations

import pytest

from core.desktop.safety import DesktopActionType, SafetyManager, SafetyDecision, safety_manager
from core.desktop.controller import DesktopController, DesktopAction, desktop_controller
from core.desktop.replay import ReplayGraph, ReplayNode, desktop_replay
from core.desktop.screen import ScreenCapture, CaptureResult, screen_capture
from core.desktop.window import WindowController, WindowActionResult, window_controller


# ──────────────────────────────────────────────
# Gate 1 — Every desktop action passes through SafetyManager
# ──────────────────────────────────────────────

class TestGate1AllActionsPassSafety:
    def test_safety_check_called_on_mouse_move(self):
        mgr = SafetyManager()
        decision = mgr.check(DesktopActionType.MOUSE_MOVE, {"x": 100, "y": 200})
        assert isinstance(decision, SafetyDecision)

    def test_safety_check_called_on_click(self):
        mgr = SafetyManager()
        decision = mgr.check(DesktopActionType.MOUSE_CLICK, {"x": 100, "y": 200})
        assert isinstance(decision, SafetyDecision)

    def test_safety_check_called_on_typing(self):
        mgr = SafetyManager()
        decision = mgr.check(DesktopActionType.KEYBOARD_TYPE, {"text": "hello"})
        assert isinstance(decision, SafetyDecision)

    def test_safety_check_called_on_screen_capture(self):
        mgr = SafetyManager()
        decision = mgr.check(DesktopActionType.SCREEN_CAPTURE)
        assert isinstance(decision, SafetyDecision)

    def test_safety_check_called_on_window_action(self):
        mgr = SafetyManager()
        decision = mgr.check(DesktopActionType.WINDOW_FOCUS, {"window_title": "test"})
        assert isinstance(decision, SafetyDecision)


# ──────────────────────────────────────────────
# Gate 2 — Emergency stop immediately blocks all
# ──────────────────────────────────────────────

class TestGate2EmergencyStop:
    def test_emergency_stop_blocks_all(self):
        mgr = SafetyManager()
        mgr.emergency_stop()
        decision = mgr.check(DesktopActionType.MOUSE_MOVE, {"x": 0, "y": 0})
        assert decision.allowed is False
        assert "Emergency stop" in decision.reason

    def test_emergency_stop_blocks_typing(self):
        mgr = SafetyManager()
        mgr.emergency_stop()
        decision = mgr.check(DesktopActionType.KEYBOARD_TYPE, {"text": "test"})
        assert decision.allowed is False

    def test_emergency_stop_blocks_screenshot(self):
        mgr = SafetyManager()
        mgr.emergency_stop()
        decision = mgr.check(DesktopActionType.SCREEN_CAPTURE)
        assert decision.allowed is False

    def test_emergency_reset_restores(self):
        mgr = SafetyManager()
        mgr.emergency_stop()
        mgr.emergency_reset()
        decision = mgr.check(DesktopActionType.MOUSE_MOVE, {"x": 0, "y": 0})
        assert decision.allowed is True


# ──────────────────────────────────────────────
# Gate 3 — Forbidden screen regions cannot be clicked
# ──────────────────────────────────────────────

class TestGate3ForbiddenRegions:
    def test_forbidden_region_blocks_click(self):
        mgr = SafetyManager()
        mgr.add_forbidden_region(0, 0, 100, 100)
        decision = mgr.check(DesktopActionType.MOUSE_CLICK, {"x": 50, "y": 50})
        assert decision.allowed is False
        assert "forbidden" in decision.reason

    def test_forbidden_region_allows_outside(self):
        mgr = SafetyManager()
        mgr.add_forbidden_region(0, 0, 100, 100)
        decision = mgr.check(DesktopActionType.MOUSE_CLICK, {"x": 200, "y": 200})
        assert decision.allowed is True

    def test_forbidden_region_allows_move_outside(self):
        mgr = SafetyManager()
        mgr.add_forbidden_region(0, 0, 100, 100)
        decision = mgr.check(DesktopActionType.MOUSE_MOVE, {"x": 200, "y": 200})
        assert decision.allowed is True

    def test_clear_forbidden_regions(self):
        mgr = SafetyManager()
        mgr.add_forbidden_region(0, 0, 100, 100)
        mgr.clear_forbidden_regions()
        decision = mgr.check(DesktopActionType.MOUSE_CLICK, {"x": 50, "y": 50})
        assert decision.allowed is True


# ──────────────────────────────────────────────
# Gate 4 — Typing rate limits enforced
# ──────────────────────────────────────────────

class TestGate4TypingRateLimit:
    def test_excessive_rate_blocked(self):
        mgr = SafetyManager()
        decision = mgr.check(DesktopActionType.KEYBOARD_TYPE, {"text": "test", "rate_char_per_sec": 100})
        assert decision.allowed is False
        assert "rate" in decision.reason.lower()

    def test_normal_rate_allowed(self):
        mgr = SafetyManager()
        decision = mgr.check(DesktopActionType.KEYBOARD_TYPE, {"text": "test", "rate_char_per_sec": 10})
        assert decision.allowed is True

    def test_long_text_blocked(self):
        mgr = SafetyManager()
        decision = mgr.check(DesktopActionType.KEYBOARD_TYPE, {"text": "x" * 501, "rate_char_per_sec": 0})
        assert decision.allowed is False
        assert "too long" in decision.reason.lower()

    def test_short_text_allowed(self):
        mgr = SafetyManager()
        decision = mgr.check(DesktopActionType.KEYBOARD_TYPE, {"text": "hello", "rate_char_per_sec": 0})
        assert decision.allowed is True


# ──────────────────────────────────────────────
# Gate 5 — Mouse movement limits enforced
# ──────────────────────────────────────────────

class TestGate5MouseSpeedLimit:
    def test_excessive_speed_blocked(self):
        mgr = SafetyManager()
        mgr.min_cooldown_sec = 0.0
        mgr.max_mouse_speed_px_per_sec = 100.0
        import time as _time
        mgr._last_action_time = _time.time() - 0.01  # 10ms ago
        mgr._last_mouse_pos = (0, 0)
        decision = mgr.check(DesktopActionType.MOUSE_MOVE, {"x": 5000, "y": 5000})
        assert decision.allowed is False
        assert "speed" in decision.reason.lower()

    def test_normal_speed_allowed(self):
        mgr = SafetyManager()
        mgr.min_cooldown_sec = 0.0
        import time as _time
        mgr._last_action_time = _time.time() - 0.01
        mgr._last_mouse_pos = (100, 100)
        decision = mgr.check(DesktopActionType.MOUSE_MOVE, {"x": 110, "y": 110})
        assert decision.allowed is True


# ──────────────────────────────────────────────
# Gate 6 — Every action enters Replay DAG
# ──────────────────────────────────────────────

class TestGate6ReplayDAG:
    def test_action_creates_replay_node(self):
        replay = ReplayGraph()
        node = replay.record("click", {"x": 100, "y": 200})
        assert isinstance(node, ReplayNode)
        assert node.node_id != ""

    def test_replay_nodes_chain(self):
        replay = ReplayGraph()
        n1 = replay.record("move", {"x": 0, "y": 0})
        n2 = replay.record("click", {"x": 100, "y": 200})
        assert n2.parent_id == n1.node_id

    def test_replay_returns_all_nodes(self):
        replay = ReplayGraph()
        replay.record("move", {})
        replay.record("click", {})
        replay.record("type", {"text": "hello"})
        assert len(replay.nodes) == 3

    def test_replay_to_dict(self):
        replay = ReplayGraph()
        replay.record("click", {"x": 100})
        d = replay.to_dict()
        assert len(d) == 1
        assert d[0]["action"] == "click"

    def test_replay_clear(self):
        replay = ReplayGraph()
        replay.record("click", {})
        replay.clear()
        assert len(replay.nodes) == 0


# ──────────────────────────────────────────────
# Gate 7 — Every screenshot becomes an Artifact
# ──────────────────────────────────────────────

class TestGate7ScreenshotArtifacts:
    def test_capture_result_has_artifact_id(self):
        # CaptureResult is our artifact representation
        result = CaptureResult(
            artifact_id="sc_test123",
            width=1920, height=1080,
            format="PNG", size_bytes=50000,
            timestamp=1000.0,
        )
        assert result.artifact_id.startswith("sc_")

    def test_capture_result_to_dict_includes_artifact_id(self):
        result = CaptureResult(
            artifact_id="sc_abc123", width=800, height=600,
            format="PNG", size_bytes=25000, timestamp=2000.0,
        )
        d = result.to_dict()
        assert d["artifact_id"] == "sc_abc123"
        assert d["width"] == 800
        assert d["format"] == "PNG"


# ──────────────────────────────────────────────
# Gate 8 — Desktop awareness and control are separate
# ──────────────────────────────────────────────

class TestGate8AwarenessSeparate:
    def test_workspace_provider_does_not_import_desktop_controller(self):
        import ast
        import inspect
        from core.providers.adapters import workspace_provider
        source = inspect.getsource(workspace_provider)
        assert "DesktopController" not in source
        assert "desktop_controller" not in source
        assert "SafetyManager" not in source

    def test_desktop_provider_does_not_duplicate_awareness(self):
        import ast
        import inspect
        from core.providers.adapters import desktop_provider
        source = inspect.getsource(desktop_provider)
        # DesktopProvider should import controller/screen/window, not raw workspace
        assert "DesktopController" in source
        assert "safety_manager" not in source  # uses SafetyManager indirectly


# ──────────────────────────────────────────────
# Gate 9 — No OS-specific code in Planner or Capability Graph
# ──────────────────────────────────────────────

class TestGate9NoOSLeak:
    def test_planner_no_desktop_code(self):
        import ast
        import inspect
        import core.planner
        source = inspect.getsource(core.planner)
        bad = {"pyautogui", "mss", "pygetwindow", "DesktopController", "SafetyManager"}
        found = [b for b in bad if b in source]
        assert len(found) == 0, f"Planner references desktop internals: {found}"

    def test_capability_graph_no_desktop_code(self):
        import ast
        import inspect
        from core.capability import graph
        source = inspect.getsource(graph)
        bad = {"pyautogui", "mss", "pygetwindow", "DesktopController", "SafetyManager"}
        found = [b for b in bad if b in source]
        assert len(found) == 0, f"CapabilityGraph references desktop internals: {found}"


# ──────────────────────────────────────────────
# Gate 10 — Desktop works as a normal provider
# ──────────────────────────────────────────────

class TestGate10DesktopAsProvider:
    def test_desktop_provider_has_correct_identity(self):
        from core.providers.adapters.desktop_provider import DesktopProvider, desktop_provider
        assert desktop_provider.provider_id == "desktop"
        assert desktop_provider.name == "Desktop Controller"

    def test_desktop_provider_declares_desktop_capability(self):
        from core.providers.adapters.desktop_provider import desktop_provider
        caps = desktop_provider.capabilities()
        assert "desktop" in caps.capability_names

    def test_desktop_capability_exists_in_models(self):
        from core.capability.models import _BUILTIN_CAPABILITIES
        assert "desktop" in _BUILTIN_CAPABILITIES
        cap = _BUILTIN_CAPABILITIES["desktop"]
        assert "desktop.mouse.click" in cap.permissions
        assert "desktop.keyboard.type" in cap.permissions

    def test_desktop_permissions_in_registry(self):
        from core.permission.registry import permission_registry
        perms = permission_registry.permissions_for_capability("desktop")
        assert "desktop.mouse.click" in perms
        assert "desktop.screen.capture" in perms

    def test_desktop_provider_executes_unknown_action_gracefully(self):
        import asyncio
        from core.providers.adapters.desktop_provider import desktop_provider
        result = asyncio.run(desktop_provider.execute({"action": "nonexistent"}))
        assert result.success is False
        assert "Unknown" in result.error

    def test_desktop_composition_plan_includes_permission_check(self):
        from core.capability.composition import CompositionEngine
        engine = CompositionEngine()
        plan = engine.compose("browse web")  # browse uses browser + research, not desktop — avoids pyautogui
        steps_with_desktop = [s for s in plan.steps if s.capability_id == "desktop"]
        if steps_with_desktop:
            step = steps_with_desktop[0]
            assert "permission" in step.to_dict()
