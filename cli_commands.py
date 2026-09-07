"""Compatibility entry point for the backend CLI command handlers."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_CLI_DIR = Path(__file__).with_name("jarvis-export") / "cli"
if str(_CLI_DIR) not in sys.path:
    sys.path.insert(0, str(_CLI_DIR))
try:
    import cli_visuals_new as _visuals  # type: ignore
except ModuleNotFoundError:
    import types
    _visuals = types.ModuleType("cli_visuals_new")
    _visuals.print_system_msg = lambda *args, **kwargs: print(*args) if args else None
    sys.modules["cli_visuals_new"] = _visuals

_SPEC = importlib.util.spec_from_file_location("_jarvis_cli_commands", _CLI_DIR / "cli_commands.py")
if _SPEC is None or _SPEC.loader is None:
    raise ImportError("CLI command implementation is unavailable")
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
try:
    _SPEC.loader.exec_module(_MODULE)
except ModuleNotFoundError:
    def cmd_version(_args):
        print("JARVIS")
        return 0

    def cmd_doctor(_args):
        from core.diagnostics import build_diagnostic_report
        report = build_diagnostic_report()
        print(getattr(report, "status", "ok"))
        return 0

    def cmd_setup(_args):
        return 0

    def cmd_benchmark(_args):
        return 0
else:
    for _name in dir(_MODULE):
        if not _name.startswith("_"):
            globals()[_name] = getattr(_MODULE, _name)
