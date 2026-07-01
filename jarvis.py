#!/usr/bin/env python3
# JARVIS — Autonomous Coding Agent
# Primary commands: chat, code, build, run, understand, workspace, doctor, models, settings, advanced, tui, web, gui, server

from __future__ import annotations
import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Any, Callable

if sys.stdout.encoding and sys.stdout.encoding.lower() in ("cp1252", "latin-1", "ansi"):
    os.environ["PYTHONIOENCODING"] = "utf-8"
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cli_commands import (
    cmd_cli, cmd_doctor, cmd_models, cmd_settings,
    cmd_understand, cmd_workspace, cmd_code, cmd_build, cmd_run,
    cmd_advanced, cmd_activity, cmd_provider, cmd_orchestrate,
    cmd_tui, cmd_web, cmd_gui, cmd_server, cmd_setup,
    cmd_demo, cmd_version,
)
from core.version import VERSION
from core.setup.detector import is_first_run
from core.setup.engine import SetupEngine


def _promote(handler: Callable, **defaults: Any) -> Callable:
    """Promote an advanced sub-command handler to a top-level command
    by filling in default attribute values the handler expects."""
    def wrapper(args: argparse.Namespace) -> int:
        for k, v in defaults.items():
            if not hasattr(args, k):
                setattr(args, k, v)
        return handler(args)
    return wrapper


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jarvis",
        description="JARVIS — Autonomous Coding Agent\n\nPrimary commands:\n  chat          Interactive terminal session\n  code <task>   Autonomous coding: plan -> build -> test -> repair -> verify\n  build         Build project with auto-repair\n  run           Run the project\n  server        Start the backend server\n  web           Build & serve web UI\n  gui           Launch Flutter desktop GUI\n  tui           Launch Textual TUI\n  understand    Analyze repository structure\n  workspace     Show workspace status\n  doctor        Run diagnostics\n  models        Manage AI models\n  settings      Manage configuration\n  setup         Interactive first-run setup wizard\n  activity      View & manage the activity graph\n  provider      Manage execution providers\n  orchestrate   Multi-provider orchestration\n  advanced      All other commands (agents, voice, etc.)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="subcommand")

    p = subparsers.add_parser("chat", help="Interactive terminal session")
    p.add_argument("--new-session", action="store_true")
    p.add_argument("--session", default=None)
    p.add_argument("--debug", action="store_true")
    p.set_defaults(func=cmd_cli)

    p = subparsers.add_parser("code", help="Autonomous coding: plan -> build -> test -> repair -> verify")
    p.add_argument("task", nargs="?", default="Understand and improve this project")
    p.add_argument("--path", default=str(Path.cwd()))
    p.set_defaults(func=cmd_code)

    p = subparsers.add_parser("build", help="Build project with auto-repair on failure")
    p.add_argument("path", nargs="?", default=str(Path.cwd()))
    p.add_argument("--command", help="Override build command")
    p.set_defaults(func=cmd_build)

    p = subparsers.add_parser("run", help="Run the project")
    p.add_argument("path", nargs="?", default=str(Path.cwd()))
    p.set_defaults(func=cmd_run)

    p = subparsers.add_parser("understand", help="Analyze repository structure")
    p.add_argument("path", nargs="?", default=str(Path.cwd()))
    p.add_argument("--aspect", default="all", help="Specific aspect: imports, tests, api, auth, database, dead_code, pipeline")
    p.add_argument("--output", help="Write markdown report to file")
    p.set_defaults(func=cmd_understand)

    p = subparsers.add_parser("workspace", help="Show workspace status")
    p.add_argument("path", nargs="?", default=str(Path.cwd()))
    p.set_defaults(func=cmd_workspace)

    p = subparsers.add_parser("doctor", help="Run system diagnostics")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_doctor)

    p = subparsers.add_parser("models", help="Manage AI models")
    p.add_argument("action", nargs="?", default="list", choices=["list", "test", "benchmark", "switch", "start", "apikeys"])
    p.add_argument("args", nargs=argparse.REMAINDER)
    p.set_defaults(func=cmd_models)

    p = subparsers.add_parser("settings", help="Manage configuration")
    p.add_argument("action", nargs="?", default="", choices=["get", "set", "reset", "export", "import"])
    p.add_argument("key", nargs="?")
    p.add_argument("value", nargs="?")
    p.set_defaults(func=cmd_settings)

    # --- Promoted advanced commands ---
    p = subparsers.add_parser("server", help="Start the FastAPI backend server")
    p.add_argument("--host", default="127.0.0.1", help="Bind address")
    p.add_argument("--port", type=int, default=8000, help="Port number")
    p.add_argument("--no-reload", action="store_true", help="Disable auto-reload")
    p.add_argument("--multi-model", action="store_true", help="Start multi-model instances")
    p.add_argument("--dry-run", action="store_true", help="Print commands without running")
    p.set_defaults(func=_promote(cmd_server))

    p = subparsers.add_parser("web", help="Build & serve the JARVIS web UI")
    p.add_argument("--host", default="127.0.0.1", help="Bind address")
    p.add_argument("--port", type=int, default=8000, help="Port number")
    p.add_argument("--rebuild", action="store_true", help="Force rebuild")
    p.add_argument("--build-only", action="store_true", help="Build without serving")
    p.add_argument("--no-open", action="store_true", help="Don't open browser")
    p.add_argument("--no-reload", action="store_true", help="Disable auto-reload")
    p.add_argument("--dry-run", action="store_true", help="Print commands without running")
    p.set_defaults(func=_promote(cmd_web))

    p = subparsers.add_parser("gui", help="Launch the Flutter Windows GUI")
    p.add_argument("--host", default="127.0.0.1", help="Backend host")
    p.add_argument("--port", type=int, default=8000, help="Backend port")
    p.add_argument("--device", default="windows", help="Flutter device")
    p.add_argument("--api-url", help="Override API URL")
    p.add_argument("--ws-url", help="Override WebSocket URL")
    p.add_argument("--dry-run", action="store_true", help="Print commands without running")
    p.set_defaults(func=_promote(cmd_gui))

    p = subparsers.add_parser("tui", help="Launch the Textual TUI")
    p.set_defaults(func=_promote(cmd_tui))

    p = subparsers.add_parser("advanced", help="Access advanced commands (agents, voice, automation, etc.)")
    p.add_argument("args", nargs=argparse.REMAINDER, help="Advanced command and its arguments")
    p.set_defaults(func=cmd_advanced)

    p = subparsers.add_parser("activity", help="View and manage the activity graph")
    p.add_argument("action", nargs="?", default="list",
                   choices=["list", "tree", "get", "summary", "watch"])
    p.add_argument("args", nargs=argparse.REMAINDER)
    p.set_defaults(func=cmd_activity)

    p = subparsers.add_parser("provider", help="Manage execution providers")
    p.add_argument("action", nargs="?", default="list",
                   choices=["list", "enable", "disable", "set-priority",
                            "doctor", "install", "benchmark", "info", "search"])
    p.add_argument("args", nargs=argparse.REMAINDER)
    p.set_defaults(func=cmd_provider)

    p = subparsers.add_parser("setup", help="Run the interactive setup wizard (re-runs safely)")
    p.set_defaults(func=cmd_setup)

    p = subparsers.add_parser("version", help="Show version information")
    p.set_defaults(func=cmd_version)

    p = subparsers.add_parser("demo", help="Run quick system demo (smoke test)")
    p.set_defaults(func=cmd_demo)

    p = subparsers.add_parser("orchestrate", help="Multi-provider orchestration: compose teams of providers")
    p.add_argument("goal", nargs="?", default="",
                   help="The goal to orchestrate across multiple providers")
    p.add_argument("--plan-only", action="store_true",
                   help="Show the orchestration plan without executing")
    p.add_argument("--language", default="",
                   help="Primary language for the task")
    p.add_argument("--framework", default="",
                   help="Framework for the task")
    p.set_defaults(func=cmd_orchestrate)

    return parser


def _run_cli_setup(engine: SetupEngine | None = None) -> bool:
    """Run the interactive CLI setup wizard."""
    if engine is None:
        engine = SetupEngine()

    def on_message(msg: str) -> None:
        print(msg)

    def on_confirm(prompt: str) -> bool:
        response = input(f"{prompt} ").strip().lower()
        return not response or response.startswith("y")

    def on_choice(question: str, options: list[str]) -> str | None:
        print(f"\n{question}")
        for i, opt in enumerate(options, 1):
            print(f"  {i}. {opt}")
        try:
            idx = int(input(f"Choice (1-{len(options)}): ").strip())
            if 1 <= idx <= len(options):
                return options[idx - 1]
        except (ValueError, EOFError):
            pass
        return None

    return engine.run_full_setup(on_message=on_message, on_confirm=on_confirm, on_choice=on_choice)


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    _SETUP_SKIP = {"version", "demo", "doctor", "setup", None}
    if args.subcommand not in _SETUP_SKIP:
        engine = SetupEngine()

        if is_first_run():
            print("\n" + "=" * 46)
            print("  Welcome to JARVIS! First-run setup")
            print("=" * 46)
            _run_cli_setup(engine)

        elif engine.resume_needed():
            print("\n" + "=" * 46)
            print("  Previous setup was interrupted.")
            print("=" * 46)
            if _run_cli_setup(engine):
                pass

    if not args.subcommand:
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
