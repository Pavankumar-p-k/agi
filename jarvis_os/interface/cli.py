from __future__ import annotations

import argparse
import json
from typing import Any

from ..bootstrap import build_jarvis_os


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jarvis-os", description="Phase 7 Mythos Omega - JARVIS OS CLI.")
    parser.add_argument("prompt", nargs="*", help="Prompt to execute. If omitted, starts interactive mode.")

    # Core options
    parser.add_argument("--agent", default="auto", help="Agent to route through.")
    parser.add_argument("--json", action="store_true", dest="as_json", help="Print raw JSON output.")
    parser.add_argument("--preview", action="store_true", help="Only build the plan preview.")

    # Information commands
    parser.add_argument("--tools", action="store_true", help="Show the tool catalog and exit.")
    parser.add_argument("--memory", action="store_true", help="Show recent memory and exit.")
    parser.add_argument("--agents", action="store_true", help="Show agent runtime state and exit.")
    parser.add_argument("--config", action="store_true", help="Show effective runtime config and exit.")
    parser.add_argument("--status", action="store_true", help="Show runtime status and exit.")
    parser.add_argument("--monitor", action="store_true", help="Show runtime monitor summary and exit.")
    parser.add_argument("--compat", action="store_true", help="Show legacy compatibility bridge status and exit.")
    parser.add_argument("--jobs", action="store_true", help="Show background jobs and exit.")
    parser.add_argument("--skills", action="store_true", help="Show learned skills and exit.")
    parser.add_argument("--plugins", action="store_true", help="Show discovered plugins and exit.")
    parser.add_argument("--schedules", action="store_true", help="Show schedules and exit.")
    parser.add_argument("--telemetry", action="store_true", help="Show telemetry and exit.")

    # Extension management commands
    parser.add_argument("--extensions", action="store_true", help="List all extensions and exit.")
    parser.add_argument("--ext-info", default="", help="Show info about a specific extension.")
    parser.add_argument("--ext-enable", default="", help="Enable an extension by name.")
    parser.add_argument("--ext-disable", default="", help="Disable an extension by name.")
    parser.add_argument("--ext-install", default="", help="Install an extension from path or URL.")
    parser.add_argument("--ext-uninstall", default="", help="Uninstall an extension by name.")
    parser.add_argument("--ext-list-commands", action="store_true", help="List all commands from extensions.")

    # Route management
    parser.add_argument("--routes", action="store_true", help="List all API routes and exit.")
    parser.add_argument("--route-info", default="", help="Show info about a specific route.")

    # Link management
    parser.add_argument("--links", action="store_true", help="List all resource links and exit.")
    parser.add_argument("--link-add", nargs=2, metavar=("NAME", "URL"), help="Add a named resource link.")
    parser.add_argument("--link-remove", default="", help="Remove a resource link by name.")
    parser.add_argument("--link-open", default="", help="Open a resource link by name.")

    # Serving process
    parser.add_argument("--serve", action="store_true", help="Start the API server (blocking).")
    parser.add_argument("--serve-host", default="127.0.0.1", help="API server host (default: 127.0.0.1).")
    parser.add_argument("--serve-port", type=int, default=8011, help="API server port (default: 8011).")
    parser.add_argument("--serve-detached", action="store_true", help="Start API server as detached process.")
    parser.add_argument("--serve-stop", action="store_true", help="Stop the detached API server.")
    parser.add_argument("--serve-status", action="store_true", help="Show API server status.")

    # Daemon management
    parser.add_argument("--daemon-status", action="store_true", help="Show daemon status and exit.")
    parser.add_argument("--daemon-start", action="store_true", help="Start the daemon and exit.")
    parser.add_argument("--daemon-stop", action="store_true", help="Stop the daemon and exit.")
    parser.add_argument("--daemon-tick", action="store_true", help="Run one daemon tick and exit.")

    # Job management
    parser.add_argument("--submit", action="store_true", help="Submit the prompt as a background job.")
    parser.add_argument("--pause-job", default="", help="Pause a background job by id.")
    parser.add_argument("--resume-job", default="", help="Resume a background job by id.")

    # Skill/Plugin execution
    parser.add_argument("--run-skill", default="", help="Run a learned skill by name.")
    parser.add_argument("--show-skill", default="", help="Show one learned skill by name.")
    parser.add_argument("--run-plugin-workflow", nargs=2, metavar=("PLUGIN", "WORKFLOW"), help="Run a plugin workflow by plugin and workflow name.")
    parser.add_argument("--run-due", action="store_true", help="Run due scheduled tasks and exit.")

    # Security options
    parser.add_argument("--approve-tool", action="append", default=[], help="Approve one tool for this run. Repeat as needed.")
    parser.add_argument("--approve-action", action="append", default=[], help="Approve one exact action string for this run. Repeat as needed.")
    parser.add_argument("--unsafe", action="store_true", help="Allow dangerous shell operations for this run.")
    parser.add_argument("--allow-workspace-escape", action="store_true", help="Allow paths outside the agent workspace.")

    return parser


def render(result: dict[str, Any]) -> str:
    if "skill" in result and "plan" in result and "execution" in result:
        lines = [
            f"Skill: {result['skill']['name']}",
            "Plan:",
        ]
        for index, step in enumerate(result["plan"]["steps"], start=1):
            lines.append(f"  {index}. [{step['tool']}] {step['action']}")
        lines.append("Execution:")
        for item in result["execution"]["results"]:
            status = "ok" if item["success"] else "fail"
            detail = item["output"] if item["success"] else item["error"]
            lines.append(f"  - {status}: {item['tool']} -> {str(detail)[:120]}")
        return "\n".join(lines)
    if "job" in result and "preview" in result:
        return "\n".join(
            [
                f"Job: {result['job']['job_id']} ({result['job']['status']})",
                f"Agent: {result['preview']['specialist']['name']}",
                f"Intent: {result['preview']['intent']['name']}",
                "Plan:",
                *[f"  {index}. [{step['tool']}] {step['action']}" for index, step in enumerate(result["preview"]["plan"]["steps"], start=1)],
            ]
        )
    lines = [
        f"Agent: {result['specialist']['name']}",
        f"Intent: {result['intent']['name']} ({result['intent']['confidence']:.2f})",
        "Plan:",
    ]
    for index, step in enumerate(result["plan"]["steps"], start=1):
        lines.append(f"  {index}. [{step['tool']}] {step['action']}")
    if "execution" not in result:
        return "\n".join(lines)
    lines.append("Execution:")
    for item in result["execution"]["results"]:
        status = "ok" if item["success"] else "fail"
        detail = item["output"] if item["success"] else item["error"]
        lines.append(f"  - {status}: {item['tool']} -> {str(detail)[:120]}")
    lines.append(f"Reply: {result['reply']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    os_runtime = build_jarvis_os()

    # Extensions management
    if args.extensions:
        print(json.dumps(os_runtime.list_extensions(), indent=2))
        return 0
    if args.ext_info:
        print(json.dumps(os_runtime.get_extension_info(args.ext_info), indent=2))
        return 0
    if args.ext_enable:
        result = os_runtime.enable_extension(args.ext_enable)
        print(json.dumps(result, indent=2))
        return 0
    if args.ext_disable:
        result = os_runtime.disable_extension(args.ext_disable)
        print(json.dumps(result, indent=2))
        return 0
    if args.ext_install:
        result = os_runtime.install_extension(args.ext_install)
        print(json.dumps(result, indent=2))
        return 0
    if args.ext_uninstall:
        result = os_runtime.uninstall_extension(args.ext_uninstall)
        print(json.dumps(result, indent=2))
        return 0
    if args.ext_list_commands:
        print(json.dumps(os_runtime.list_extension_commands(), indent=2))
        return 0

    # Routes
    if args.routes:
        print(json.dumps(os_runtime.list_routes(), indent=2))
        return 0
    if args.route_info:
        print(json.dumps(os_runtime.get_route_info(args.route_info), indent=2))
        return 0

    # Links
    if args.links:
        print(json.dumps(os_runtime.list_links(), indent=2))
        return 0
    if args.link_add:
        name, url = args.link_add
        result = os_runtime.add_link(name, url)
        print(json.dumps(result, indent=2))
        return 0
    if args.link_remove:
        result = os_runtime.remove_link(args.link_remove)
        print(json.dumps(result, indent=2))
        return 0
    if args.link_open:
        result = os_runtime.open_link(args.link_open)
        print(json.dumps(result, indent=2))
        return 0

    # Serving process
    if args.serve:
        os_runtime.serve_api(host=args.serve_host, port=args.serve_port, detached=False)
        return 0
    if args.serve_detached:
        result = os_runtime.serve_api(host=args.serve_host, port=args.serve_port, detached=True)
        print(json.dumps(result, indent=2))
        return 0
    if args.serve_stop:
        result = os_runtime.stop_api_server()
        print(json.dumps(result, indent=2))
        return 0
    if args.serve_status:
        print(json.dumps(os_runtime.api_server_status(), indent=2))
        return 0

    # Original commands
    if args.tools:
        print(json.dumps(os_runtime.tools.catalog(), indent=2))
        return 0
    if args.memory:
        print(json.dumps(os_runtime.memory.recent(), indent=2))
        return 0
    if args.config:
        print(json.dumps(os_runtime.config_summary(), indent=2))
        return 0
    if args.monitor:
        print(json.dumps(os_runtime.monitor_summary(), indent=2))
        return 0
    if args.compat:
        print(json.dumps(os_runtime.compat_summary(), indent=2))
        return 0
    if args.agents:
        print(json.dumps(os_runtime.list_agents(), indent=2))
        return 0
    if args.status:
        print(json.dumps(os_runtime.status(), indent=2))
        return 0
    if args.jobs:
        print(json.dumps(os_runtime.list_jobs(), indent=2))
        return 0
    if args.skills:
        print(json.dumps(os_runtime.list_skills(), indent=2))
        return 0
    if args.plugins:
        print(json.dumps(os_runtime.list_plugins(), indent=2))
        return 0
    if args.schedules:
        print(json.dumps(os_runtime.list_schedules(), indent=2))
        return 0
    if args.telemetry:
        print(json.dumps(os_runtime.telemetry_summary(), indent=2))
        return 0
    if args.daemon_status:
        print(json.dumps(os_runtime.daemon_status(), indent=2))
        return 0
    if args.daemon_start:
        print(json.dumps(os_runtime.daemon_start(), indent=2))
        return 0
    if args.daemon_stop:
        print(json.dumps(os_runtime.daemon_stop(), indent=2))
        return 0
    if args.daemon_tick:
        print(json.dumps(os_runtime.daemon_tick(), indent=2))
        return 0
    if args.run_due:
        print(json.dumps(os_runtime.run_due_schedules(), indent=2))
        return 0
    if args.show_skill:
        print(json.dumps(os_runtime.get_skill(args.show_skill), indent=2))
        return 0
    if args.run_skill:
        result = os_runtime.run_skill(args.run_skill)
        print(json.dumps(result, indent=2) if args.as_json else render(result))
        return 0
    if args.run_plugin_workflow:
        plugin_name, workflow_name = args.run_plugin_workflow
        result = os_runtime.run_plugin_workflow(plugin_name, workflow_name)
        print(json.dumps(result, indent=2) if args.as_json else json.dumps(result, indent=2))
        return 0
    if args.pause_job:
        result = os_runtime.pause_job(args.pause_job)
        print(json.dumps(result, indent=2))
        return 0
    if args.resume_job:
        result = os_runtime.resume_job(args.resume_job)
        print(json.dumps(result, indent=2))
        return 0

    # Handle prompt
    context = _context_from_args(args)
    if args.prompt:
        prompt = " ".join(args.prompt)
        if args.preview:
            result = os_runtime.preview_prompt(prompt, context=context, agent_name=args.agent)
        elif args.submit:
            result = os_runtime.submit_prompt(prompt, context=context, agent_name=args.agent)
        else:
            result = os_runtime.handle_prompt(prompt, context=context, agent_name=args.agent)
        print(json.dumps(result, indent=2) if args.as_json else render(result))
        return 0

    return _interactive(os_runtime, args.agent, args.as_json, context)


def _interactive(os_runtime, agent_name: str, as_json: bool, session_context: dict[str, Any]) -> int:
    print("JARVIS OS CLI - Phase 7 Mythos Omega")
    print("Type 'exit' to quit, '/help' for commands.")
    while True:
        try:
            prompt = input("You > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not prompt:
            continue
        if prompt.lower() in {"exit", "quit"}:
            return 0

        # Built-in commands
        if prompt.lower() == "/help":
            _print_help()
            continue
        if prompt.lower() == "/status":
            print(json.dumps(os_runtime.status(), indent=2))
            continue
        if prompt.lower() == "/agents":
            print(json.dumps(os_runtime.list_agents(), indent=2))
            continue
        if prompt.lower() == "/config":
            print(json.dumps(os_runtime.config_summary(), indent=2))
            continue
        if prompt.lower() == "/monitor":
            print(json.dumps(os_runtime.monitor_summary(), indent=2))
            continue
        if prompt.lower() == "/compat":
            print(json.dumps(os_runtime.compat_summary(), indent=2))
            continue
        if prompt.lower() == "/jobs":
            print(json.dumps(os_runtime.list_jobs(), indent=2))
            continue
        if prompt.lower() == "/skills":
            print(json.dumps(os_runtime.list_skills(), indent=2))
            continue
        if prompt.lower() == "/plugins":
            print(json.dumps(os_runtime.list_plugins(), indent=2))
            continue
        if prompt.lower() == "/schedules":
            print(json.dumps(os_runtime.list_schedules(), indent=2))
            continue
        if prompt.lower() == "/telemetry":
            print(json.dumps(os_runtime.telemetry_summary(), indent=2))
            continue
        if prompt.lower() == "/daemon":
            print(json.dumps(os_runtime.daemon_status(), indent=2))
            continue
        if prompt.lower() == "/policy":
            print(json.dumps(os_runtime.status()["policy"], indent=2))
            continue

        # Extension commands
        if prompt.lower() == "/extensions":
            print(json.dumps(os_runtime.list_extensions(), indent=2))
            continue
        if prompt.lower().startswith("/ext-info "):
            ext_name = prompt.split(" ", 1)[1].strip()
            print(json.dumps(os_runtime.get_extension_info(ext_name), indent=2))
            continue
        if prompt.lower().startswith("/ext-enable "):
            ext_name = prompt.split(" ", 1)[1].strip()
            print(json.dumps(os_runtime.enable_extension(ext_name), indent=2))
            continue
        if prompt.lower().startswith("/ext-disable "):
            ext_name = prompt.split(" ", 1)[1].strip()
            print(json.dumps(os_runtime.disable_extension(ext_name), indent=2))
            continue
        if prompt.lower().startswith("/ext-install "):
            ext_path = prompt.split(" ", 1)[1].strip()
            print(json.dumps(os_runtime.install_extension(ext_path), indent=2))
            continue
        if prompt.lower().startswith("/ext-uninstall "):
            ext_name = prompt.split(" ", 1)[1].strip()
            print(json.dumps(os_runtime.uninstall_extension(ext_name), indent=2))
            continue
        if prompt.lower() == "/ext-commands":
            print(json.dumps(os_runtime.list_extension_commands(), indent=2))
            continue

        # Route commands
        if prompt.lower() == "/routes":
            print(json.dumps(os_runtime.list_routes(), indent=2))
            continue
        if prompt.lower().startswith("/route-info "):
            route = prompt.split(" ", 1)[1].strip()
            print(json.dumps(os_runtime.get_route_info(route), indent=2))
            continue

        # Link commands
        if prompt.lower() == "/links":
            print(json.dumps(os_runtime.list_links(), indent=2))
            continue
        if prompt.lower().startswith("/link-add "):
            parts = prompt.split(" ", 2)[1:]
            if len(parts) >= 2:
                name, url = parts[0].strip(), parts[1].strip()
                print(json.dumps(os_runtime.add_link(name, url), indent=2))
            else:
                print("Usage: /link-add NAME URL")
            continue
        if prompt.lower().startswith("/link-remove "):
            name = prompt.split(" ", 1)[1].strip()
            print(json.dumps(os_runtime.remove_link(name), indent=2))
            continue
        if prompt.lower().startswith("/link-open "):
            name = prompt.split(" ", 1)[1].strip()
            print(json.dumps(os_runtime.open_link(name), indent=2))
            continue

        # Serving commands
        if prompt.lower() == "/serve":
            os_runtime.serve_api(detached=False)
            continue
        if prompt.lower() == "/serve-start":
            result = os_runtime.serve_api(detached=True)
            print(json.dumps(result, indent=2))
            continue
        if prompt.lower() == "/serve-stop":
            print(json.dumps(os_runtime.stop_api_server(), indent=2))
            continue
        if prompt.lower() == "/serve-status":
            print(json.dumps(os_runtime.api_server_status(), indent=2))
            continue

        if prompt.lower().startswith("/approve "):
            tool_name = prompt.split(" ", 1)[1].strip()
            session_context.setdefault("approved_tools", [])
            if tool_name and tool_name not in session_context["approved_tools"]:
                session_context["approved_tools"].append(tool_name)
            print(json.dumps({"approved_tools": session_context.get("approved_tools", [])}, indent=2))
            continue
        if prompt.lower().startswith("/unsafe "):
            state = prompt.split(" ", 1)[1].strip().lower()
            session_context["allow_unsafe"] = state in {"1", "on", "true", "yes"}
            print(json.dumps({"allow_unsafe": session_context["allow_unsafe"]}, indent=2))
            continue
        if prompt.lower().startswith("/escape "):
            state = prompt.split(" ", 1)[1].strip().lower()
            session_context["allow_workspace_escape"] = state in {"1", "on", "true", "yes"}
            print(json.dumps({"allow_workspace_escape": session_context["allow_workspace_escape"]}, indent=2))
            continue

        # Handle prompt
        result = os_runtime.handle_prompt(prompt, context=session_context, agent_name=agent_name)
        print(json.dumps(result, indent=2) if as_json else render(result))


def _print_help():
    """Print help for interactive mode."""
    help_text = """
JARVIS OS CLI - Available Commands:

Core:
  /status        - Show runtime status
  /config        - Show configuration
  /monitor       - Show monitor summary
  /agents        - List agents
  /jobs          - List background jobs
  /skills        - List learned skills
  /plugins       - List plugins
  /schedules     - List schedules
  /telemetry     - Show telemetry
  /daemon        - Show daemon status
  /policy        - Show policy

Extensions:
  /extensions    - List all extensions
  /ext-info NAME - Show extension info
  /ext-enable NAME   - Enable an extension
  /ext-disable NAME  - Disable an extension
  /ext-install PATH - Install extension
  /ext-uninstall NAME - Uninstall extension
  /ext-commands  - List extension commands

Routes:
  /routes        - List API routes
  /route-info ROUTE - Show route info

Links:
  /links         - List resource links
  /link-add NAME URL   - Add a link
  /link-remove NAME    - Remove a link
  /link-open NAME      - Open a link

Serving:
  /serve          - Start API server (blocking)
  /serve-start    - Start API server (detached)
  /serve-stop     - Stop API server
  /serve-status   - Show server status

Security:
  /approve TOOL  - Approve a tool
  /unsafe on|off  - Toggle unsafe mode
  /escape on|off - Toggle workspace escape

General:
  /help          - Show this help
  exit, quit     - Exit CLI
"""
    print(help_text)


def _context_from_args(args: Any) -> dict[str, Any]:
    return {
        "approved_tools": list(args.approve_tool),
        "approved_actions": list(args.approve_action),
        "allow_unsafe": bool(args.unsafe),
        "allow_workspace_escape": bool(args.allow_workspace_escape),
    }


if __name__ == "__main__":
    raise SystemExit(main())
