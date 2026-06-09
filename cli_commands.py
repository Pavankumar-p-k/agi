# Copyright (c) 2024-2026 JARVIS Project
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""cli_commands.py — CLI command handler functions for the JARVIS CLI."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time

from cli_helpers import build_cli_context, is_agentic_prompt, print_plan_preview
from cli_requests import (
    extract_reply,
    is_limited_mode_reply,
    poll_job,
    request_json,
    run_autonomy_cli,
    stream_chat_ws,
)
from cli_server import (
    backend_server_cmd,
    ensure_local_stack_running,
    ensure_ollama_running,
    is_ollama_reachable,
    stop_local_services,
)
from cli_slash_commands import handle_cli_slash_command
from cli_state import APPS, BACKEND, HISTORY_PATH, MODEL_PORTS, ROOT, STUDENT_MAIN, CliState
from cli_utils import IDE_PRESETS, colorize, common_env, python_exe, run_command, spawn_background
from cli_visuals import render_agents, render_boot_screen, render_design_plan, render_routing_decision


def cmd_cli(args: argparse.Namespace) -> int:
    from prompt_toolkit.formatted_text import FormattedText
    from prompt_toolkit.history import FileHistory
    from prompt_toolkit.shortcuts import PromptSession

    from cli_completer import JarvisCompleter
    from cli_utils import style_theme
    from core.session import ConversationManager, get_last_session_id

    env = common_env()
    base_url = env.get("JARVIS_SERVER", "http://127.0.0.1:8000")
    ensure_local_stack_running(env)
    cli_debug = getattr(args, "debug", False)

    cfg = __import__('cli_config').JarvisConfig.load()
    effective_debug = cli_debug or cfg.debug
    effective_debug_search = getattr(args, "debug_search", False) or cfg.debug_search

    if getattr(args, "new_session", False):
        session_id = None
        if effective_debug:
            print("[DEBUG] Starting new session")
    elif getattr(args, "session", None):
        session_id = args.session
        if effective_debug:
            print(f"[DEBUG] Resuming session: {session_id}")
    else:
        last_id = get_last_session_id()
        session_id = last_id
        if effective_debug:
            print(f"[DEBUG] Last session: {session_id or 'none — starting fresh'}")

    session = ConversationManager(session_id=session_id)
    if session_id and session.path.exists():
        session.load()
        if effective_debug:
            print(f"[DEBUG] Loaded session: {session.session_id} ({session.message_count} messages, {session.token_count} tokens)")

    state = CliState(
        session=session,
        config=cfg,
        mode=cfg.mode,
        debug=effective_debug,
        debug_search=effective_debug_search,
        show_timestamps=cfg.show_timestamps,
        current_model=cfg.default_model,
        base_url=base_url,
    )

    style = style_theme(cfg.theme == "dark")
    hist_path = HISTORY_PATH
    hist_path.parent.mkdir(parents=True, exist_ok=True)
    history = FileHistory(str(hist_path))
    completer = JarvisCompleter(lambda: state)
    prompt_session = PromptSession(
        history=history,
        completer=completer,
        style=style,
        enable_history_search=True,
        complete_while_typing=True,
    )

    render_boot_screen(animated=not state.debug, delay=0.018)
    dbg_label = colorize(" DEBUG", "yellow") if state.debug else ""
    print(f"{colorize('Session:', 'cyan')} {session.session_id[:8]}...{dbg_label}")
    print(f"{colorize('Commands:', 'cyan')} /help  /agents  /design  /boot  /frames")
    print()

    stash_capture_mode = False
    _last_command = ""

    while True:
        try:
            text = prompt_session.prompt(
                FormattedText([("class:prompt", "You > ")]),
            ).strip()
        except (KeyboardInterrupt, EOFError):
            state.session.save()
            cfg.save()
            print(f"\n{colorize('Goodbye.', 'green')}")
            return 0
        if not text and _last_command:
            text = _last_command
        elif not text:
            if stash_capture_mode:
                print(f"{colorize('JARVIS > cancelled stash capture.', 'yellow')}")
                stash_capture_mode = False
            continue
        _last_command = text

        if cfg.aliases and text.split()[0] in cfg.aliases:
            alias_cmd = cfg.aliases[text.split()[0]]
            text = alias_cmd + text[len(text.split()[0]):]

        if stash_capture_mode:
            stash_capture_mode = False
            idx = state.session.stash_prompt(text)
            print(f"{colorize(f'JARVIS > stashed as #{idx}.', 'green')}")
            continue

        if text.lower() in {"exit", "quit", "bye"}:
            state.session.save()
            cfg.save()
            return 0

        if text.startswith("/"):
            command_status = handle_cli_slash_command(text, state)
            if command_status == "handled":
                continue
            if command_status == "exit":
                state.session.save()
                cfg.save()
                return 0
            if command_status == "stash_capture":
                stash_capture_mode = True
                print(f"{colorize('JARVIS > enter text to stash:', 'cyan')}")
                continue
            if command_status == "skip":
                text = state._pending_text
                state._pending_text = ""
                if not text:
                    continue
            else:
                continue

        try:
            context = build_cli_context(text)
            context["cli_mode"] = state.mode
            if state.mode == "agent" and is_agentic_prompt(text):
                preview = request_json(
                    state.base_url,
                    "/os/agents/preview",
                    {"prompt": text, "agent_name": "auto", "context": context},
                )
                print_plan_preview(preview)
            if state.mode == "chat":
                state.session.add_message("user", text)
                payload = {
                    "message": text,
                    "tier": "local",
                    "session_id": state.session.session_id,
                }
                if state.current_model:
                    payload["model"] = state.current_model
                if state.debug:
                    payload["debug"] = True
                result = None
                if state.stream:
                    reply = stream_chat_ws(state.base_url, payload)
                    if is_limited_mode_reply(reply):
                        ensure_ollama_running(env)
                        reply = stream_chat_ws(state.base_url, payload)
                else:
                    result = request_json(state.base_url, "/api/chat", payload)
                    reply = extract_reply(result)
                    if is_limited_mode_reply(reply):
                        ensure_ollama_running(env)
                        result = request_json(state.base_url, "/api/chat", payload)
                        reply = extract_reply(result)
                state.session.add_message("assistant", reply)
                state.session.save()
            else:
                endpoint = "/os/agents/run"
                payload = {"prompt": text, "context": context, "agent_name": "auto"}
                result = request_json(state.base_url, endpoint, payload)
                reply = extract_reply(result)
                if is_limited_mode_reply(reply):
                    ensure_ollama_running(env)
                    context["retry_after_model_boot"] = True
                    result = request_json(state.base_url, endpoint, payload)
                    reply = extract_reply(result)
                specialist = result.get("specialist", {}).get("name") if result else None
                if specialist:
                    render_routing_decision(specialist, "matched prompt intent")

            ts_prefix = ""
            if state.show_timestamps:
                ts_str = __import__('datetime').datetime.now().strftime("%H:%M:%S")
                ts_prefix = f"{colorize(f'[{ts_str}]', 'timestamp')} "

            print(f"{colorize('JARVIS >', 'cyan')} {ts_prefix}{reply}")
            if result:
                specialist = result.get("specialist", {}).get("name")
                if specialist:
                    agent_str = f"[agent={specialist}]"
                    print(f"        {colorize(agent_str, 'green')}")
                lat_str = f"[{result.get('latency_ms', 0)} ms]"
                print(f"        {colorize(lat_str, 'dim')}")
        except Exception as exc:
            print(f"{colorize('JARVIS > request failed:', 'red')} {exc}")


def cmd_tui(args: argparse.Namespace) -> int:
    """Launch the production-grade JARVIS TUI built with Textual."""
    import os
    import subprocess

    from cli_server import ensure_local_stack_running
    from cli_utils import common_env

    env = common_env()
    ensure_local_stack_running(env)

    tui_path = os.path.join(os.path.dirname(__file__), "jarvis_tui", "main.py")
    if not os.path.exists(tui_path):
        print(f"JARVIS TUI not found at {tui_path}")
        return 1

    print("Launching JARVIS Production TUI...")
    # Using sys.executable to ensure we use the same environment
    # Pass common_env to the subprocess so it has access to JARVIS_SERVER etc.
    subprocess.run([sys.executable, tui_path], env=env)
    return 0


def cmd_boot(args: argparse.Namespace) -> int:
    render_boot_screen(animated=not getattr(args, "static", False), delay=0.04)
    return 0


def cmd_cli_agents(args: argparse.Namespace) -> int:
    render_agents()
    return 0


def cmd_cli_design(args: argparse.Namespace) -> int:
    render_design_plan()
    return 0


def cmd_autonomy_passthrough(args: argparse.Namespace) -> int:
    tail = getattr(args, "text", None) or getattr(args, "query", None) or []
    if isinstance(tail, list):
        return run_autonomy_cli([args.command, *tail])
    return run_autonomy_cli([args.command, str(tail)])


def cmd_status(args: argparse.Namespace) -> int:
    env = common_env()
    base_url = env.get("JARVIS_SERVER", "http://127.0.0.1:8000")
    ensure_local_stack_running(env)
    try:
        result = request_json(base_url, "/os/status", method="GET")
    except Exception as exc:
        print(f"Status request failed: {exc}")
        return 1

    components = result.get("components", {})
    world = components.get("world_model", {})
    learning = components.get("learning", {})
    tools = components.get("tools", [])
    models = components.get("models", {})
    browser = components.get("browser", {})
    skills_registry = components.get("skills_registry", {})
    supervisor = components.get("supervisor", {})
    access_manager = components.get("access_manager", {})
    mobile_sync = components.get("mobile_sync", {})
    scheduler = components.get("scheduler", {})
    gateway = components.get("gateway", {})
    safety = components.get("safety", {})
    self_improvement = components.get("self_improvement", {})

    print()
    print("JARVIS AI OS STATUS")
    print("-------------------")
    print(f"Initialized:        {result.get('initialized', False)}")
    print(f"World memories:     {world.get('memories', 0)}")
    print(f"Tracked goals:      {world.get('goals', 0)}")
    print(f"Knowledge facts:    {world.get('knowledge', 0)}")
    print(f"Experiences:        {world.get('experiences', 0)}")
    print(f"Tools registered:   {len(tools)}")
    print(f"Learning enabled:   {learning.get('enabled', False)}")
    print(f"Student AGI loaded: {learning.get('student_agi_loaded', False)}")
    print(f"Models ready:       {models.get('ready', False)}")
    print(f"Browser mode:       {browser.get('mode', 'unknown')}")
    print(f"Skill registry:     {skills_registry.get('count', 0)} skill(s)")
    print(f"Supervisor queued:  {supervisor.get('queued', 0)}")
    print(f"Access profiles:    {len(access_manager.get('grants', []))}")
    print(f"Mobile devices:     {len(mobile_sync.get('linked_devices', []))}")
    print(f"Heartbeat jobs:     {scheduler.get('count', 0)}")
    print(f"Channels online:    {sum(1 for channel in gateway.get('channels', {}).values() if channel.get('enabled'))}")
    ollama_ready = is_ollama_reachable(env)
    print(f"Safety strict:      {safety.get('strict_mode', False)}")
    print(f"Self-improve loop:  {self_improvement.get('running', False)}")
    print(f"Ollama ready:       {ollama_ready}")
    if not ollama_ready:
        print("Ollama info:        unavailable; local/fallback mode is enabled.")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    from core.diagnostics import build_diagnostic_report
    report = build_diagnostic_report()
    if getattr(args, "json", False):
        print(json.dumps(report.to_dict(), indent=2))
        return 0 if report.status in {"ok", "warning"} else 1

    print(colorize(f"JARVIS doctor: {report.status}", "green" if report.status == "ok" else "yellow"))
    print(f"Root: {report.root}")
    print(f"Python files: {report.counts.get('python_files', 0)} | tests: {report.counts.get('tests', 0)}")
    missing = [name for name, ok in report.optional_dependencies.items() if not ok]
    print("Missing optional deps: " + (", ".join(missing) if missing else "none"))
    print("Runtime flags: " + ", ".join(f"{k}={v}" for k, v in sorted(report.runtime_flags.items())))
    print("Top issues:")
    for issue in report.issues[:20]:
        print(f"- [{issue.severity}] {issue.category} {issue.path}: {issue.message}")
    if len(report.issues) > 20:
        print(f"... {len(report.issues) - 20} more issue(s). Use --json for full detail.")
    print("Capability gaps vs OpenClaw source:")
    for gap in report.capability_gaps:
        print(f"- {gap}")
    return 0 if report.status in {"ok", "warning"} else 1


def cmd_cleanup_audit(args: argparse.Namespace) -> int:
    from core.cleanup_audit import build_cleanup_audit
    audit = build_cleanup_audit()
    data = audit.to_dict()
    if getattr(args, "json", False):
        print(json.dumps(data, indent=2))
        return 0

    print(colorize("JARVIS cleanup audit", "cyan"))
    print(f"Root: {audit.root}")
    for key, value in audit.totals.items():
        print(f"{key}: {value}")
    print("\nEntrypoints:")
    for item in audit.entrypoints:
        print(f"- {item}")
    print("\nTop orphan candidates:")
    for item in audit.orphan_candidates[:30]:
        print(f"- {item}")
    if len(audit.orphan_candidates) > 30:
        print(f"... {len(audit.orphan_candidates) - 30} more. Use --json for full list.")
    print("\nRoot clutter:")
    for item in audit.root_clutter[:30]:
        print(f"- {item}")
    if len(audit.root_clutter) > 30:
        print(f"... {len(audit.root_clutter) - 30} more. Use --json for full list.")
    print("\nRecommendations:")
    for item in audit.recommendations:
        print(f"- {item}")
    return 0


def cmd_goal(args: argparse.Namespace) -> int:
    prompt = " ".join(args.text).strip()
    if not prompt:
        print("Usage: jarvis goal <prompt>")
        return 1
    env = common_env()
    base_url = env.get("JARVIS_SERVER", "http://127.0.0.1:8000")
    ensure_local_stack_running(env)
    context = build_cli_context(prompt)
    context["cli_mode"] = "agent"
    result = request_json(base_url, "/os/agents/submit", {"prompt": prompt, "agent_name": "auto", "context": context})
    print()
    specialist = result.get("specialist", {}).get("name")
    if specialist:
        print(f"Agent:   {specialist}")
    print(f"Goal ID: {result['goal']['goal_id']}")
    print(f"Job ID:  {result['job_id']}")
    print("Plan:")
    for index, step in enumerate(result["plan"]["steps"], start=1):
        print(f"  {index}. [{step['tool']}] {step['action']}")
    return 0


def cmd_plan_preview(args: argparse.Namespace) -> int:
    prompt = " ".join(args.text).strip()
    if not prompt:
        print("Usage: jarvis plan <prompt>")
        return 1
    env = common_env()
    base_url = env.get("JARVIS_SERVER", "http://127.0.0.1:8000")
    ensure_local_stack_running(env)
    context = build_cli_context(prompt)
    context["cli_mode"] = "agent"
    result = request_json(base_url, "/os/agents/preview", {"prompt": prompt, "agent_name": "auto", "context": context})
    print()
    specialist = result.get("specialist", {}).get("name")
    if specialist:
        print(f"Agent:   {specialist}")
    print(f"Goal ID: {result['goal']['goal_id']}")
    print(f"Intent:  {result['analysis'].get('intent', 'unknown')}")
    print("Plan:")
    for index, step in enumerate(result["plan"]["steps"], start=1):
        print(f"  {index}. [{step['tool']}] {step['action']}")
    return 0


def cmd_develop(args: argparse.Namespace) -> int:
    prompt = " ".join(args.text).strip()
    if not prompt:
        print("Usage: jarvis develop <prompt>")
        return 1
    env = common_env()
    base_url = env.get("JARVIS_SERVER", "http://127.0.0.1:8000")
    ensure_local_stack_running(env)
    context = build_cli_context(prompt)
    context["cli_mode"] = "agent"
    result = request_json(base_url, "/os/agents/submit", {"prompt": prompt, "agent_name": "auto", "context": context})
    job_id = result["job_id"]
    specialist = result.get("specialist", {}).get("name")
    if specialist:
        print(f"Agent: {specialist}")
    print(f"Started goal {result['goal']['goal_id']} as job {job_id}")
    print("Plan:")
    for index, step in enumerate(result["plan"]["steps"], start=1):
        print(f"  {index}. [{step['tool']}] {step['action']}")
    print()
    return poll_job(base_url, job_id)


def cmd_server(args: argparse.Namespace) -> int:
    if args.multi_model:
        for model, port in MODEL_PORTS:
            env = common_env()
            env.update(
                {
                    "OLLAMA_HOST": f"127.0.0.1:{port}",
                    "OLLAMA_NUM_GPU": env.get("OLLAMA_NUM_GPU", "99"),
                    "OLLAMA_KEEP_ALIVE": env.get("OLLAMA_KEEP_ALIVE", "300"),
                    "OLLAMA_NUM_PARALLEL": env.get("OLLAMA_NUM_PARALLEL", "1"),
                    "OLLAMA_FLASH_ATTENTION": env.get("OLLAMA_FLASH_ATTENTION", "1"),
                    "OLLAMA_KV_CACHE_TYPE": env.get("OLLAMA_KV_CACHE_TYPE", "q8_0"),
                    "OLLAMA_MAX_LOADED_MODELS": env.get("OLLAMA_MAX_LOADED_MODELS", "1"),
                    "CUDA_VISIBLE_DEVICES": env.get("CUDA_VISIBLE_DEVICES", "0"),
                }
            )
            spawn_background(f"Ollama-{model}", ["ollama", "serve"], cwd=ROOT, env=env, dry_run=args.dry_run)
        if not args.dry_run:
            time.sleep(2)

    env = common_env()
    if args.multi_model:
        env["OLLAMA_MULTI_INSTANCE"] = "1"
        env["OLLAMA_MODEL_ENDPOINTS"] = ";".join(f"{model}=http://127.0.0.1:{port}" for model, port in MODEL_PORTS)
    return run_command(
        backend_server_cmd(args.host, args.port, not args.no_reload),
        cwd=BACKEND,
        env=env,
        dry_run=args.dry_run,
    )


def cmd_restart(args: argparse.Namespace) -> int:
    stop_local_services(include_ollama=args.with_models)
    time.sleep(2)
    server_args = argparse.Namespace(
        multi_model=args.multi_model,
        host=args.host,
        port=args.port,
        no_reload=args.no_reload,
        dry_run=args.dry_run,
    )
    return cmd_server(server_args)


def cmd_gui(args: argparse.Namespace) -> int:
    api_url = args.api_url or f"http://{args.host}:{args.port}"
    ws_url = args.ws_url or f"ws://{args.host}:{args.port}/ws"
    cmd = [
        "flutter",
        "run",
        "-d",
        args.device,
        f"--dart-define=API_BASE_URL={api_url}",
        f"--dart-define=WS_URL={ws_url}",
    ]
    if args.google_api_key:
        cmd.append(f"--dart-define=GOOGLE_API_KEY={args.google_api_key}")
    if args.droq_api_key:
        cmd.append(f"--dart-define=DROQ_API_KEY={args.droq_api_key}")
    return run_command(cmd, cwd=APPS, env=common_env(), dry_run=args.dry_run)


def cmd_up(args: argparse.Namespace) -> int:
    server_args = argparse.Namespace(
        multi_model=args.multi_model,
        host=args.host,
        port=args.port,
        no_reload=args.no_reload,
        dry_run=args.dry_run,
    )
    gui_args = argparse.Namespace(
        api_url=args.api_url,
        ws_url=args.ws_url,
        host=args.host,
        port=args.port,
        device=args.device,
        google_api_key=args.google_api_key,
        droq_api_key=args.droq_api_key,
        dry_run=args.dry_run,
    )

    if args.background:
        env = common_env()
        if args.multi_model:
            env["OLLAMA_MULTI_INSTANCE"] = "1"
            env["OLLAMA_MODEL_ENDPOINTS"] = ";".join(f"{model}=http://127.0.0.1:{port}" for model, port in MODEL_PORTS)
            for model, port in MODEL_PORTS:
                ollama_env = env.copy()
                ollama_env["OLLAMA_HOST"] = f"127.0.0.1:{port}"
                spawn_background(f"Ollama-{model}", ["ollama", "serve"], cwd=ROOT, env=ollama_env, dry_run=args.dry_run)
        spawn_background(
            "JARVIS-Server",
            backend_server_cmd(args.host, args.port, not args.no_reload),
            cwd=BACKEND,
            env=env,
            dry_run=args.dry_run,
        )
        flutter_cmd = [
            "flutter",
            "run",
            "-d",
            args.device,
            f"--dart-define=API_BASE_URL={args.api_url or f'http://{args.host}:{args.port}'}",
            f"--dart-define=WS_URL={args.ws_url or f'ws://{args.host}:{args.port}/ws'}",
        ]
        if args.google_api_key:
            flutter_cmd.append(f"--dart-define=GOOGLE_API_KEY={args.google_api_key}")
        if args.droq_api_key:
            flutter_cmd.append(f"--dart-define=DROQ_API_KEY={args.droq_api_key}")
        return spawn_background(
            "JARVIS-GUI",
            flutter_cmd,
            cwd=APPS,
            env=common_env(),
            dry_run=args.dry_run,
        )

    code = cmd_server(server_args)
    if code != 0:
        return code
    return cmd_gui(gui_args)


def cmd_student(args: argparse.Namespace) -> int:
    cmd = [python_exe(), str(STUDENT_MAIN), *args.forward]
    return run_command(cmd, cwd=ROOT, env=common_env(), dry_run=args.dry_run)


def cmd_models(args: argparse.Namespace) -> int:
    if args.models_command == "list":
        for model, port in MODEL_PORTS:
            print(f"{model:18} http://127.0.0.1:{port}")
        return 0
    if args.models_command == "start":
        server_args = argparse.Namespace(
            multi_model=True,
            host=args.host,
            port=args.port,
            no_reload=args.no_reload,
            dry_run=args.dry_run,
        )
        return cmd_server(server_args)
    return 0


def cmd_extension(args: argparse.Namespace) -> int:
    if args.extension_command == "list":
        for name, description in IDE_PRESETS.items():
            print(f"{name:10} {description}")
        return 0

    ide = args.ide.lower()
    description = IDE_PRESETS.get(ide, "Generic IDE integration preset.")
    host = args.host
    port = args.port
    api_url = f"http://{host}:{port}"
    print(f"IDE preset: {ide}")
    print(description)
    print()
    print("Recommended commands:")
    print("  jarvis server")
    print("  jarvis server /m")
    print("  jarvis gui")
    print("  jarvis cli")
    print()
    print("Useful endpoints:")
    print(f"  API root:        {api_url}")
    print(f"  AI OS:           {api_url}/os")
    print(f"  Autonomy:        {api_url}/autonomy")
    print(f"  Docs:            {api_url}/docs")
    print()
    print("Environment variables:")
    print(f"  JARVIS_SERVER={api_url}")
    print("  JARVIS_AUTONOMY_PREFIX=/autonomy")
    print("  JARVIS_OS_PREFIX=/os")
    return 0


def cmd_web(args: argparse.Namespace) -> int:
    """Build (if needed) and serve the JARVIS web UI."""
    web_dir = ROOT / "web"
    out_dir = web_dir / "out"

    if not out_dir.is_dir() or args.rebuild:
        print("Building web UI...")
        ret = run_command(
            ["npm.cmd", "run", "build"] if sys.platform == "win32" else ["npm", "run", "build"],
            cwd=str(web_dir),
            dry_run=args.dry_run,
        )
        if ret != 0:
            print("Web UI build failed.", file=sys.stderr)
            return ret

    if args.build_only:
        print(f"Web UI built at {out_dir}")
        return 0

    import webbrowser
    host = args.host or "127.0.0.1"
    port = args.port or 8000
    url = f"http://{host}:{port}/chat"
    print(f"Starting JARVIS server + web UI at {url}")

    if not args.no_open:
        webbrowser.open(url)

    env = common_env()
    return run_command(
        backend_server_cmd(host, port, reload_enabled=not args.no_reload),
        cwd=BACKEND,
        env=env,
        dry_run=args.dry_run,
    )


def cmd_os(args: argparse.Namespace) -> int:
    cmd = [python_exe(), "-m", "jarvis_os.interface.cli", *args.text]
    if args.agent:
        cmd.extend(["--agent", args.agent])
    if args.as_json:
        cmd.append("--json")
    if args.tools:
        cmd.append("--tools")
    if args.memory_view:
        cmd.append("--memory")
    if args.status:
        cmd.append("--status")
    if args.jobs:
        cmd.append("--jobs")
    if args.skills:
        cmd.append("--skills")
    if args.schedules:
        cmd.append("--schedules")
    if args.telemetry:
        cmd.append("--telemetry")
    if args.daemon_status:
        cmd.append("--daemon-status")
    if args.daemon_start:
        cmd.append("--daemon-start")
    if args.daemon_stop:
        cmd.append("--daemon-stop")
    if args.daemon_tick:
        cmd.append("--daemon-tick")
    if args.submit:
        cmd.append("--submit")
    if args.preview:
        cmd.append("--preview")
    if args.run_skill:
        cmd.extend(["--run-skill", args.run_skill])
    if args.show_skill:
        cmd.extend(["--show-skill", args.show_skill])
    if args.run_due:
        cmd.append("--run-due")
    return run_command(cmd, cwd=ROOT, env=common_env(), dry_run=getattr(args, "dry_run", False))


def cmd_cognitive(args: argparse.Namespace) -> int:
    cmd = [python_exe(), "-m", "cognitive_agent.main", *args.forward]
    return run_command(cmd, cwd=BACKEND, env=common_env(), dry_run=getattr(args, "dry_run", False))


def cmd_agent_list(args):
    from core.sub_agents.registry import agent_registry
    agents = agent_registry.list_agents()
    print(f"\n{'NAME':<12} {'DESCRIPTION':<55} {'MODES'}")
    print("-" * 100)
    for a in agents:
        modes = ", ".join(a["modes"])
        print(f"{a['name']:<12} {a['description'][:54]:<55} {modes}")
    print()
    return 0


def cmd_agent_run(args):
    import asyncio

    from core.sub_agents.registry import agent_registry
    result = asyncio.run(agent_registry.run(
        args.name.upper(), args.task,
        mode=getattr(args, "mode", None),
        lang=getattr(args, "lang", "auto")
    ))
    print(f"\n[{result.agent_name}:{result.mode}] — {result.duration_s:.1f}s\n")
    print(result.output)
    if result.error:
        print(f"\nERROR: {result.error}")
    return 0 if result.success else 1


def cmd_settings(args: argparse.Namespace) -> int:
    from core.settings.store import get_settings_store
    store = get_settings_store()

    if args.settings_command == "get":
        try:
            val = store.get(args.key)
            print(val)
        except KeyError as e:
            print(f"Error: {e}")
            return 1
    elif args.settings_command == "set":
        try:
            try:
                import json as _json
                parsed_val = _json.loads(args.value)
            except json.JSONDecodeError:
                if args.value.lower() == "true": parsed_val = True
                elif args.value.lower() == "false": parsed_val = False
                elif args.value.isdigit(): parsed_val = int(args.value)
                else:
                    try:
                        parsed_val = float(args.value)
                    except ValueError:
                        parsed_val = args.value
            if store.set(args.key, parsed_val):
                print(f"Successfully set {args.key} = {parsed_val}")
            else:
                print(f"Failed to set {args.key}")
                return 1
        except Exception as e:
            print(f"Error setting {args.key}: {e}")
            return 1
    elif args.settings_command == "reset":
        store.reset(args.key)
        if args.key:
            print(f"Reset {args.key} to default.")
        else:
            print("Reset all settings to defaults.")
    elif args.settings_command == "export":
        data = store.export()
        import json as _json2
        print(_json2.dumps(data, indent=2))
    elif args.settings_command == "import":
        if store.import_from_json(args.file):
            print(f"Successfully imported settings from {args.file}")
        else:
            print(f"Failed to import settings from {args.file}")
            return 1
    else:
        data = store.export()
        print("\nJARVIS Settings:")
        print("-" * 40)

        def print_nested(d, prefix=""):
            for k, v in d.items():
                full_key = f"{prefix}{k}"
                if isinstance(v, dict):
                    print_nested(v, f"{full_key}.")
                else:
                    print(f"{full_key:<30} = {v}")

        print_nested(data)
        print("-" * 40)

    return 0


def cmd_agent_shortcut(args, agent_name: str):
    args.name = agent_name
    return cmd_agent_run(args)


def cmd_plugin(args):
    from core.plugins.loader import get_plugin_loader
    from core.plugins.registry import get_plugin_registry
    registry = get_plugin_registry()
    loader = get_plugin_loader()

    if args.plugin_action == "list":
        for p in registry.list_plugins():
            status = "E" if p.get("enabled") else "D"
            print(f"[{status}] {p['id']:30s} v{p.get('version','?'):10s} {p.get('name','')}")
        return 0
    elif args.plugin_action == "enable":
        print("Enabled" if registry.enable(args.id) else "Not found")
        return 0
    elif args.plugin_action == "disable":
        print("Disabled" if registry.disable(args.id) else "Not found")
        return 0
    elif args.plugin_action == "reload":
        print("Reloaded" if loader.reload(args.id) else "Failed")
        return 0
    elif args.plugin_action == "settings":
        import json as _j
        s = registry.get_settings(args.id)
        print(_j.dumps(s, indent=2))
        return 0
    elif args.plugin_action == "info":
        m = registry.get_manifest(args.id)
        if m:
            import json as _j2
            print(_j2.dumps(m.to_dict() if hasattr(m, 'to_dict') else vars(m), indent=2))
        else:
            print("Not found")
        return 0
    elif args.plugin_action == "install":
        pkg = args.id
        print(f"JARVIS > Installing plugin package: {pkg}")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])
            print(f"JARVIS > Successfully installed {pkg}. Restart JARVIS to discover it via entry points.")
            return 0
        except Exception as e:
            print(f"JARVIS > Installation failed: {e}")
            return 1
    elif args.plugin_action == "search":
        query = args.id
        print(f"JARVIS > Searching PyPI for 'jarvis-plugin-{query}'...")
        print(f"JARVIS > Please visit: https://pypi.org/search/?q=jarvis-plugin-{query}")
        return 0
    elif args.plugin_action == "publish":
        print("JARVIS > Plugin Publication Guide")
        print("1. Create your jarvis_plugin_sdk.Plugin subclass.")
        print("2. Define [project.entry-points.'jarvis.plugins'] in your pyproject.toml.")
        print("3. Run: python -m build && python -m twine upload dist/*")
        return 0
    return 1


def cmd_cloud(args):
    import asyncio

    from core.cloud.cloud_memory import CloudMemory
    from core.cloud.supabase_client import is_connected

    if args.cloud_action == "status":
        print("Supabase:", "Connected" if is_connected() else "Offline (SQLite mode)")
        return 0
    elif args.cloud_action == "sync":
        n = asyncio.run(CloudMemory().sync_from_local())
        print(f"Synced {n} rows to Supabase")
        return 0
    elif args.cloud_action == "pull":
        n = asyncio.run(CloudMemory().sync_to_local())
        print(f"Pulled {n} rows from Supabase")
        return 0
    return 1


def cmd_project(args):
    import asyncio

    from core.cloud.project_manager import ProjectManager
    pm = ProjectManager()

    if args.project_action == "list":
        projects = asyncio.run(pm.list_projects())
        for p in projects:
            print(f"[{p.status}] {str(p.id)[:8]}  {p.name}")
        return 0
    elif args.project_action == "create":
        p = asyncio.run(pm.create_project(args.name, goal=getattr(args, "goal", "")))
        print(f"Created: {p.id}")
        return 0
    elif args.project_action == "show":
        p = asyncio.run(pm.get_project(args.id))
        if p:
            import json as _j3
            print(_j3.dumps(p.to_dict() if hasattr(p, 'to_dict') else vars(p), indent=2))
        return 0
    elif args.project_action == "complete":
        ok = asyncio.run(pm.complete_step(args.step_id))
        print("Completed" if ok else "Step not found")
        return 0
    elif args.project_action == "delete":
        asyncio.run(pm.delete_project(args.id))
        print("Deleted")
        return 0
    return 1


def cmd_index(args: argparse.Namespace) -> int:
    from cli_state import ROOT
    from core.codebase_indexer import index_workspace
    print(f"Indexing workspace: {ROOT}...")
    try:
        import asyncio
        result = asyncio.run(index_workspace(str(ROOT)))
        if result.get("success"):
            print(f"Indexed {result.get('indexed_count', 0)} chunks successfully.")
        else:
            print(f"Indexing failed: {result.get('message', 'unknown error')}")
    except Exception as e:
        print(f"Indexing error: {e}")
    return 0


def cmd_setup(args: argparse.Namespace) -> int:
    """Interactive setup wizard for first-time JARVIS configuration."""
    print("=" * 60)
    print("  JARVIS Setup Wizard")
    print("=" * 60)
    print()

    checks = 0
    passed = 0

    # 1. Python version
    checks += 1
    py_ok = sys.version_info >= (3, 10)
    print(f"  [{chr(0x221A) if py_ok else 'x'}] Python {sys.version_info.major}.{sys.version_info.minor} {'OK' if py_ok else '(3.10+ required)'}")
    if py_ok:
        passed += 1

    # 2. Config file
    checks += 1
    try:
        from core.config_schema import JarvisConfig
        cfg = JarvisConfig.load()
        config_ok = True
        print(f"  [{chr(0x221A)}] Config loaded: {cfg.__class__.__name__}")
        passed += 1
    except Exception as e:
        config_ok = False
        print(f"  [x] Config error: {e}")

    # 3. Required packages
    checks += 1
    required = ["fastapi", "uvicorn", "httpx", "litellm", "prompt_toolkit", "pygments"]
    missing = []
    for mod in required:
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    deps_ok = len(missing) == 0
    if deps_ok:
        print(f"  [{chr(0x221A)}] All required packages installed")
        passed += 1
    else:
        print(f"  [x] Missing packages: {', '.join(missing)}")

    # 4. API keys
    checks += 1
    key_vars = {"OPENAI_API_KEY": "OpenAI", "ANTHROPIC_API_KEY": "Anthropic", "GEMINI_API_KEY": "Gemini"}
    found_keys = [v for k, v in key_vars.items() if os.getenv(k)]
    if found_keys:
        print(f"  [{chr(0x221A)}] API keys detected: {', '.join(found_keys)}")
        passed += 1
    else:
        print("  [i] No API keys found. Set OPENAI_API_KEY or ANTHROPIC_API_KEY in your environment.")
        checks -= 1

    # 5. Docker
    checks += 1
    try:
        r = subprocess.run(["docker", "info"], capture_output=True, timeout=5)
        docker_ok = r.returncode == 0
        print(f"  [{chr(0x221A) if docker_ok else 'i'}] Docker {'available' if docker_ok else 'not found (sandboxing unavailable)'}")
        if docker_ok:
            passed += 1
    except (FileNotFoundError, subprocess.TimeoutExpired):
        print("  [i] Docker not found (sandboxing unavailable)")

    # 6. Git repo
    checks += 1
    try:
        r = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], capture_output=True, timeout=5)
        git_ok = r.returncode == 0
        print(f"  [{chr(0x221A) if git_ok else 'i'}] Git repository {'detected' if git_ok else 'not detected'}")
        if git_ok:
            passed += 1
    except (FileNotFoundError, subprocess.TimeoutExpired):
        print("  [i] Git not found")

    # Summary
    print()
    print("-" * 60)
    print(f"  {passed}/{checks} checks passed")
    if passed < checks:
        print()
        print("  Quick fixes:")
        if missing:
            print(f"    pip install {' '.join(missing)}")
        if not found_keys:
            print("    set OPENAI_API_KEY=your_key_here")
    print("=" * 60)
    return 0 if passed >= min(checks, 4) else 1


def cmd_debug(args: argparse.Namespace) -> int:
    try:
        from core.debugger import runtime_snapshot
        snap = runtime_snapshot()
    except Exception as e:
        print(f"[Debug] Could not collect snapshot: {e}")
        return 1

    print(colorize("=== Runtime Snapshot ===", "cyan"))
    for section, data in snap.items():
        print(colorize(f"\n{section.upper()}:", "yellow"))
        if isinstance(data, list):
            for item in data:
                print(f"  {item}")
        elif isinstance(data, dict):
            for k, v in data.items():
                print(f"  {k}: {v}")
        else:
            print(f"  {data}")
    return 0
