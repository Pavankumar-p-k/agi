#!/usr/bin/env python3
"""Unified JARVIS launcher for CLI, server, GUI, models, and IDE integrations.

Thin entry point — all logic lives in the cli_* modules.
"""
from __future__ import annotations
import logging

import argparse
import sys
from pathlib import Path
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cli_utils import IDE_PRESETS
from cli_commands import (
    cmd_cli, cmd_setup, cmd_status, cmd_doctor, cmd_cleanup_audit,
    cmd_goal, cmd_develop, cmd_server, cmd_restart, cmd_gui, cmd_up, cmd_student,
    cmd_models, cmd_extension, cmd_web, cmd_os, cmd_cognitive, cmd_agent_list,
    cmd_agent_run, cmd_settings, cmd_agent_shortcut, cmd_plugin, cmd_cloud,
    cmd_project, cmd_debug, cmd_index, cmd_tui,
    cmd_boot, cmd_cli_agents, cmd_cli_design,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jarvis",
        description="Unified JARVIS launcher for CLI, server, GUI, models, and IDE integrations.",
        prefix_chars="-/",
    )
    subparsers = parser.add_subparsers(dest="subcommand")

    try:
        from core.governance.cli_commands import register_governance_commands
        register_governance_commands(subparsers)
    except Exception as e:
        logger.warning("[jarvis] build_parser_website_commands failed: %s", e)

    agent_parser = subparsers.add_parser("agent", help="Run JARVIS sub-agents", prefix_chars="-/")
    agent_sub = agent_parser.add_subparsers(dest="agent_command")
    agent_list = agent_sub.add_parser("list", help="List all agents", prefix_chars="-/")
    agent_list.set_defaults(func=cmd_agent_list)
    agent_run = agent_sub.add_parser("run", help="Run an agent", prefix_chars="-/")
    agent_run.add_argument("name", help="Agent name (NEXUS, FORGE, ORACLE, etc.)")
    agent_run.add_argument("task", help="Task for the agent")
    agent_run.add_argument("--mode", "-m", default=None, help="Agent mode")
    agent_run.add_argument("--lang", default="auto", help="Language (for FORGE)")
    agent_run.set_defaults(func=cmd_agent_run)

    for shortname in ["nexus", "forge", "oracle", "cipher", "herald", "atlas", "scribe", "sentinel", "maestro"]:
        p = subparsers.add_parser(shortname, help=f"Run {shortname.upper()} agent", prefix_chars="-/")
        p.add_argument("task", help="Task to run")
        p.add_argument("--mode", "-m", default=None)
        p.add_argument("--lang", default="auto")
        p.set_defaults(func=lambda args, n=shortname: cmd_agent_shortcut(args, n))

    try:
        from tools.jarvis_website_cli import _add_website_commands, cmd_website
        _add_website_commands(subparsers)
        wp = subparsers.choices.get("website")
        if wp:
            wp.set_defaults(func=cmd_website)
    except Exception as e:
        logger.warning("[jarvis] could not register website commands: %s", e)

    for name in ("cli", "chat"):
        p = subparsers.add_parser(name, help=f"Start the interactive JARVIS terminal chat.", prefix_chars="-/")
        p.add_argument("--new-session", action="store_true")
        p.add_argument("--session", default=None)
        p.add_argument("--debug", action="store_true")
        p.add_argument("--debug-search", action="store_true")
        p.set_defaults(func=cmd_cli)

    tui = subparsers.add_parser("tui", help="Launch the production-grade JARVIS AI TUI.", prefix_chars="-/")
    tui.set_defaults(func=cmd_tui)

    boot = subparsers.add_parser("boot", help="Show the animated JARVIS CLI diamond boot screen.", prefix_chars="-/")
    boot.add_argument("--static", action="store_true", help="Render without animation")
    boot.set_defaults(func=cmd_boot)

    agents_screen = subparsers.add_parser("agents", help="Show the 9-agent terminal overview.", prefix_chars="-/")
    agents_screen.set_defaults(func=cmd_cli_agents)

    design = subparsers.add_parser("design", help="Show the CLI animation and build plan.", prefix_chars="-/")
    design.set_defaults(func=cmd_cli_design)

    status = subparsers.add_parser("status", help="Show current JARVIS autonomous status.", prefix_chars="-/")
    status.set_defaults(func=cmd_status)

    doctor = subparsers.add_parser("doctor", help="Run dependency, crash-risk, and degraded-response diagnostics.", prefix_chars="-/")
    doctor.add_argument("--json", action="store_true")
    doctor.set_defaults(func=cmd_doctor)

    cleanup_audit = subparsers.add_parser("cleanup-audit", help="Map active modules, orphan candidates, and root clutter.", prefix_chars="-/")
    cleanup_audit.add_argument("--json", action="store_true")
    cleanup_audit.set_defaults(func=cmd_cleanup_audit)

    server = subparsers.add_parser("server", help="Start the FastAPI backend server.", prefix_chars="-/")
    server.add_argument("/m", "--multi-model", action="store_true", dest="multi_model")
    server.add_argument("--host", default="0.0.0.0")
    server.add_argument("--port", type=int, default=8000)
    server.add_argument("--no-reload", action="store_true")
    server.add_argument("--dry-run", action="store_true")
    server.set_defaults(func=cmd_server)

    restart = subparsers.add_parser("restart", help="Restart the local backend stack.", prefix_chars="-/")
    restart.add_argument("/m", "--multi-model", action="store_true", dest="multi_model")
    restart.add_argument("--with-models", action="store_true")
    restart.add_argument("--host", default="0.0.0.0")
    restart.add_argument("--port", type=int, default=8000)
    restart.add_argument("--no-reload", action="store_true")
    restart.add_argument("--dry-run", action="store_true")
    restart.set_defaults(func=cmd_restart)

    gui = subparsers.add_parser("gui", help="Start the Flutter Windows GUI.", prefix_chars="-/")
    gui.add_argument("--device", default="windows")
    gui.add_argument("--host", default="127.0.0.1")
    gui.add_argument("--port", type=int, default=8000)
    gui.add_argument("--api-url")
    gui.add_argument("--ws-url")
    gui.add_argument("--google-api-key", default="")
    gui.add_argument("--droq-api-key", default="")
    gui.add_argument("--dry-run", action="store_true")
    gui.set_defaults(func=cmd_gui)

    web = subparsers.add_parser("web", help="Build & serve the JARVIS web UI.", prefix_chars="-/")
    web.add_argument("-b", "--build-only", action="store_true", help="Only build the web UI, don't serve")
    web.add_argument("-r", "--rebuild", action="store_true", help="Force rebuild even if already built")
    web.add_argument("--host", default="127.0.0.1")
    web.add_argument("--port", type=int, default=8000)
    web.add_argument("--no-open", action="store_true", help="Don't open browser automatically")
    web.add_argument("--no-reload", action="store_true", help="Disable hot-reload")
    web.add_argument("--dry-run", action="store_true")
    web.set_defaults(func=cmd_web)

    up = subparsers.add_parser("up", help="Start JARVIS desktop stack (server + GUI).", prefix_chars="-/")
    up.add_argument("/m", "--multi-model", action="store_true", dest="multi_model")
    up.add_argument("--background", action="store_true")
    up.add_argument("--host", default="127.0.0.1")
    up.add_argument("--port", type=int, default=8000)
    up.add_argument("--device", default="windows")
    up.add_argument("--api-url")
    up.add_argument("--ws-url")
    up.add_argument("--google-api-key", default="")
    up.add_argument("--droq-api-key", default="")
    up.add_argument("--no-reload", action="store_true")
    up.add_argument("--dry-run", action="store_true")
    up.set_defaults(func=cmd_up)

    student = subparsers.add_parser("student", help="Run the Student AGI service or commands.", prefix_chars="-/")
    student.add_argument("forward", nargs=argparse.REMAINDER)
    student.add_argument("--dry-run", action="store_true")
    student.set_defaults(func=cmd_student)

    models = subparsers.add_parser("models", help="List or start configured model servers.", prefix_chars="-/")
    models_sub = models.add_subparsers(dest="models_command")
    models_sub.add_parser("list", help="List multi-model endpoint mapping.", prefix_chars="-/").set_defaults(func=cmd_models)
    models_start = models_sub.add_parser("start", help="Start multi-model backend stack.", prefix_chars="-/")
    models_start.add_argument("--host", default="0.0.0.0")
    models_start.add_argument("--port", type=int, default=8000)
    models_start.add_argument("--no-reload", action="store_true")
    models_start.add_argument("--dry-run", action="store_true")
    models_start.set_defaults(func=cmd_models)

    extension = subparsers.add_parser("extension", help="Show IDE/extension integration commands.", prefix_chars="-/")
    extension_sub = extension.add_subparsers(dest="extension_command")
    extension_sub.add_parser("list", help="List supported IDE presets.", prefix_chars="-/").set_defaults(func=cmd_extension)
    extension_show = extension_sub.add_parser("show", help="Show setup commands for one IDE preset.", prefix_chars="-/")
    extension_show.add_argument("ide", choices=sorted(IDE_PRESETS.keys()))
    extension_show.add_argument("--host", default="127.0.0.1")
    extension_show.add_argument("--port", type=int, default=8000)
    extension_show.set_defaults(func=cmd_extension)

    plugin_cmd = subparsers.add_parser("plugin", help="Manage plugins", prefix_chars="-/")
    plugin_sub = plugin_cmd.add_subparsers(dest="plugin_action")
    for action in ("list", "enable", "disable", "reload", "settings", "info", "install", "search", "publish"):
        pp = plugin_sub.add_parser(action, help=f"{action.capitalize()} a plugin", prefix_chars="-/")
        if action in ("enable", "disable", "reload", "settings", "info"):
            pp.add_argument("id")
        if action == "install":
            pp.add_argument("id", help="Plugin package name")
        if action == "search":
            pp.add_argument("id", help="Search query")
        pp.set_defaults(func=cmd_plugin)

    cloud_cmd = subparsers.add_parser("cloud", help="Cloud/Supabase commands", prefix_chars="-/")
    cloud_sub = cloud_cmd.add_subparsers(dest="cloud_action")
    for action in ("status", "sync", "pull"):
        cloud_sub.add_parser(action, help=f"{action.capitalize()} cloud data", prefix_chars="-/").set_defaults(func=cmd_cloud)

    subparsers.add_parser("setup", help="Run setup wizard for first-time configuration", prefix_chars="-/").set_defaults(func=cmd_setup)

    subparsers.add_parser("debug", help="Inspect runtime state", prefix_chars="-/").set_defaults(func=cmd_debug)

    subparsers.add_parser("index", help="Index workspace files for codebase search", prefix_chars="-/").set_defaults(func=cmd_index)

    proj_cmd = subparsers.add_parser("project", help="Manage projects", prefix_chars="-/")
    proj_sub = proj_cmd.add_subparsers(dest="project_action")
    proj_sub.add_parser("list", help="List projects", prefix_chars="-/").set_defaults(func=cmd_project)
    pc = proj_sub.add_parser("create", help="Create a project", prefix_chars="-/")
    pc.add_argument("name"); pc.add_argument("--goal", default=""); pc.set_defaults(func=cmd_project)
    ps2 = proj_sub.add_parser("show", help="Show project details", prefix_chars="-/")
    ps2.add_argument("id"); ps2.set_defaults(func=cmd_project)
    pco = proj_sub.add_parser("complete", help="Complete a step", prefix_chars="-/")
    pco.add_argument("step_id"); pco.set_defaults(func=cmd_project)
    pdel = proj_sub.add_parser("delete", help="Delete a project", prefix_chars="-/")
    pdel.add_argument("id"); pdel.set_defaults(func=cmd_project)

    return parser


def main() -> int:
    raw_args = sys.argv[1:]
    if raw_args and raw_args[0] == "student" and not any(flag in raw_args[1:] for flag in ("-h", "--help", "/?")):
        dry_run = False
        forward: list[str] = []
        for item in raw_args[1:]:
            if item == "--dry-run":
                dry_run = True
            else:
                forward.append(item)
        return cmd_student(argparse.Namespace(forward=forward, dry_run=dry_run))
    if raw_args and raw_args[0] == "cognitive" and not any(flag in raw_args[1:] for flag in ("-h", "--help", "/?")):
        dry_run = False
        forward: list[str] = []
        for item in raw_args[1:]:
            if item == "--dry-run":
                dry_run = True
            else:
                forward.append(item)
        return cmd_cognitive(argparse.Namespace(forward=forward, dry_run=dry_run))

    parser = build_parser()
    subparsers = None
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            subparsers = action
            break

    if subparsers:
        p_settings = subparsers.add_parser("settings", help="Manage JARVIS settings")
        p_settings.set_defaults(func=cmd_settings)
        settings_subs = p_settings.add_subparsers(dest="settings_command")
        settings_subs.add_parser("get", help="Get a setting value").add_argument("key")
        p_set = settings_subs.add_parser("set", help="Set a setting value")
        p_set.add_argument("key"); p_set.add_argument("value")
        settings_subs.add_parser("reset", help="Reset settings to defaults").add_argument("key", nargs="?")
        settings_subs.add_parser("export", help="Export settings to JSON")
        settings_subs.add_parser("import", help="Import settings from JSON").add_argument("file")

    args = parser.parse_args()
    if not getattr(args, "subcommand", None):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
