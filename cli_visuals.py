# Root shim — canonical implementation: jarvis-export/cli/cli_visuals.py
# Loaded under a private module name to avoid the circular self-import that a
# plain `from cli_visuals import ...` inside a same-named shim would cause.
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_CANONICAL = Path(__file__).resolve().parent / "jarvis-export" / "cli" / "cli_visuals.py"
_SPEC = importlib.util.spec_from_file_location("_jarvis_cli_visuals", _CANONICAL)
assert _SPEC is not None and _SPEC.loader is not None
_canonical = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _canonical  # required before exec (dataclasses introspection)
_SPEC.loader.exec_module(_canonical)

AGENT_CARDS = _canonical.AGENT_CARDS
render_agents = _canonical.render_agents
render_boot_screen = _canonical.render_boot_screen
render_control_loop = _canonical.render_control_loop
render_design_plan = _canonical.render_design_plan
render_routing_decision = _canonical.render_routing_decision
render_state_frames = _canonical.render_state_frames
spinner_for = _canonical.spinner_for
terminal_supports_animation = _canonical.terminal_supports_animation

__all__ = [
    "AGENT_CARDS", "render_agents", "render_boot_screen", "render_control_loop",
    "render_design_plan", "render_routing_decision", "render_state_frames",
    "spinner_for", "terminal_supports_animation",
]
