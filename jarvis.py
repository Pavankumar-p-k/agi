#!/usr/bin/env python3
# JARVIS — Autonomous Coding Agent
# Primary commands: chat, code, build, run, understand, workspace, doctor, models, settings, advanced

from __future__ import annotations
import argparse
import logging
import os
import sys
from pathlib import Path

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
    cmd_advanced, cmd_activity,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jarvis",
        description="JARVIS — Autonomous Coding Agent\n\nPrimary commands:\n  chat          Interactive terminal session\n  code <task>   Autonomous coding: plan -> build -> test -> repair -> verify\n  build         Build project with auto-repair\n  run           Run the project\n  understand    Analyze repository structure\n  workspace     Show workspace status\n  doctor        Run diagnostics\n  models        Manage AI models\n  settings      Manage configuration\n  advanced      All other commands (server, agents, voice, etc.)",
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

    p = subparsers.add_parser("advanced", help="Access advanced commands (server, agents, voice, etc.)")
    p.add_argument("args", nargs=argparse.REMAINDER, help="Advanced command and its arguments")
    p.set_defaults(func=cmd_advanced)

    p = subparsers.add_parser("activity", help="View and manage the activity graph")
    p.add_argument("action", nargs="?", default="list",
                   choices=["list", "tree", "get", "summary", "watch"])
    p.add_argument("args", nargs=argparse.REMAINDER)
    p.set_defaults(func=cmd_activity)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if not args.subcommand:
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
