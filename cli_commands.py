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
import logging
import os
import subprocess
import sys
import time

from cli_helpers import build_cli_context, is_agentic_prompt, print_plan_preview

logger = logging.getLogger(__name__)
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
    is_server_reachable,
    stop_local_services,
)
from cli_slash_commands import handle_cli_slash_command
from cli_state import APPS, BACKEND, HISTORY_PATH, MODEL_PORTS, ROOT, STUDENT_MAIN, CliState
from cli_utils import IDE_PRESETS, colorize, common_env, python_exe, run_command, spawn_background
from cli_visuals import render_agents, render_boot_screen, render_design_plan, render_routing_decision
from pathlib import Path


def cmd_cli(args: argparse.Namespace) -> int:
    from prompt_toolkit.formatted_text import FormattedText
    from prompt_toolkit.history import FileHistory
    from prompt_toolkit.shortcuts import PromptSession
    from prompt_toolkit.styles import Style as PtStyle

    from cli_completer import JarvisCompleter
    from cli_visuals_new import (
        JARVISTheme,
        print_ai_reply,
        print_system_msg,
        render_agent_status,
        render_banner,
        render_step_progress,
        show_cmd_menu,
        show_theme_menu,
    )
    from core.session import ConversationManager, get_last_session_id

    env = common_env()
    base_url = env.get("JARVIS_SERVER", "http://127.0.0.1:8000")
    ensure_local_stack_running(env)
    cli_debug = getattr(args, "debug", False)

    cfg = __import__("cli_config").JarvisConfig.load()
    JARVISTheme.set(cfg.theme)
    
    effective_debug = cli_debug or cfg.debug
    effective_debug_search = getattr(args, "debug_search", False) or cfg.debug_search

    if getattr(args, "new_session", False):
        session_id = None
    elif getattr(args, "session", None):
        session_id = args.session
    else:
        session_id = get_last_session_id()

    session = ConversationManager(session_id=session_id)
    if session_id and session.path.exists():
        session.load()

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

    # Initial UI Render
    os.system("cls" if os.name == "nt" else "clear")
    render_banner()
    print_system_msg(f"Connected to {base_url}", "success")
    print_system_msg(f"Active Session: [bold]{session.session_id}[/]")

    hist_path = HISTORY_PATH
    hist_path.parent.mkdir(parents=True, exist_ok=True)
    history = FileHistory(str(hist_path))
    completer = JarvisCompleter(lambda: state)

    # PtStyle for the input area
    from cli_visuals_new import get_pt_style
    pt_style = get_pt_style()

    prompt_session = PromptSession(
        history=history,
        completer=completer,
        style=pt_style,
        enable_history_search=True,
        complete_while_typing=True,
    )

    _last_command = ""

    while True:
        try:
            # Custom prompt rendering
            prompt_text = [
                ("class:prompt", "\n ◈ JARVIS "),
                ("class:continuation", "❯ "),
            ]
            text = prompt_session.prompt(prompt_text).strip()
        except (KeyboardInterrupt, EOFError):
            state.session.save()
            cfg.save()
            print_system_msg("Session saved. Powering down...", "info")
            return 0

        if not text and _last_command:
            text = _last_command
        elif not text:
            continue
        _last_command = text

        # Intercept Redesigned Commands
        if text.lower() == "/cmds":
            cmd = show_cmd_menu()
            if cmd:
                # If it's a slash command, handle it. If it's a text command, treat as input.
                text = cmd if cmd.startswith("/") else f"/{cmd}"
                print_system_msg(f"Invoking {text}...", "info")
            else:
                continue

        if text.lower() == "/themes":
            new_theme = show_theme_menu()
            if new_theme:
                cfg.theme = new_theme
                cfg.save()
                # Refresh styles
                from cli_visuals_new import get_pt_style
                prompt_session.style = get_pt_style()
            continue

        if text.lower() in {"exit", "quit", "bye"}:
            state.session.save()
            cfg.save()
            return 0

        # Handle Slash Commands (Backend & Logic)
        if text.startswith("/"):
            if handle_cli_slash_command(text, state):
                continue

        # Unified Agent Stream Execution
        try:
            from cli_requests import stream_agent_ws, get_project_context_dict
            payload = {
                "type": "chat",
                "text": text,
                "session_id": state.session.session_id,
            }
            project_ctx = get_project_context_dict()
            stream_agent_ws(state.base_url, payload, project_context=project_ctx)
        except Exception as e:
            print_system_msg(f"Core execution error: {e}", "error")

    return 0


def cmd_server(args: argparse.Namespace) -> int:
    from cli_server import ensure_server_running
    check_host = "127.0.0.1" if args.host == "0.0.0.0" else args.host
    base_url = f"http://{check_host}:{args.port}"
    if is_server_reachable(base_url):
        print(f"JARVIS backend already running at {base_url}")
        return 0
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
        env["OLLAMA_MULTI_INSTANCE"] = "1"
        env["OLLAMA_MODEL_ENDPOINTS"] = ";".join(f"{model}=http://127.0.0.1:{port}" for model, port in MODEL_PORTS)
        return run_command(
            backend_server_cmd(args.host, args.port, not args.no_reload),
            cwd=BACKEND, env=env, dry_run=args.dry_run,
        )

    ensure_server_running(base_url, str(args.host), int(args.port))
    print(f"JARVIS backend ready at {base_url}")
    return 0


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
    from cli_server import ensure_server_running
    api_url = args.api_url or f"http://{args.host}:{args.port}"
    ws_url = args.ws_url or f"ws://{args.host}:{args.port}/ws"
    ensure_server_running(api_url, str(args.host), int(args.port))
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
        check_host = "127.0.0.1" if args.host == "0.0.0.0" else args.host
        if not is_server_reachable(f"http://{check_host}:{args.port}"):
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
    import asyncio

    models_cmd = getattr(args, "action", "list")
    if models_cmd == "list":
        from core.model_providers.hybrid import get_platform
        from rich.console import Console
        from rich.table import Table
        console = Console()
        platform = get_platform()
        models = asyncio.run(platform.list_models())
        mode = platform.mode.value.upper()
        table = Table(title=f"Model Providers [{mode} MODE]", border_style="cyan")
        table.add_column("Provider", style="bold")
        table.add_column("Model")
        table.add_column("Status")
        table.add_column("Latency")
        table.add_column("Cost")
        for m in models:
            status_style = {"healthy": "green", "down": "red", "error": "red", "unknown": "yellow"}
            s = status_style.get(m.status, "white")
            table.add_row(m.provider, m.model, f"[{s}]{m.status}[/]",
                          f"{m.latency_ms:.0f}ms" if m.latency_ms else "—", m.cost_estimate)
        console.print(table)
        return 0

    if models_cmd == "test":
        from core.model_providers.hybrid import get_platform
        from cli_visuals_new import print_system_msg
        platform = get_platform()
        print_system_msg(f"Testing provider: {args.provider or 'all'}...", "info")
        result = asyncio.run(platform.test_model(args.provider, args.model))
        from rich.console import Console
        console = Console()
        if result.status == "healthy":
            console.print(f"[green]✅ {result.provider}/{result.model}[/] — {result.latency_ms:.0f}ms — {result.cost_estimate}")
        else:
            console.print(f"[red]❌ {result.provider}/{result.model}[/] — {result.error}")
        return 0

    if models_cmd == "benchmark":
        from core.model_providers.hybrid import get_platform
        from cli_visuals_new import print_system_msg
        from rich.table import Table
        from rich.console import Console
        console = Console()
        print_system_msg(f"Benchmarking provider: {args.provider or 'all'}...", "info")
        results = asyncio.run(get_platform().benchmark(args.provider))
        table = Table(title="Benchmark Results", border_style="blue")
        table.add_column("Provider")
        table.add_column("Model")
        table.add_column("Test")
        table.add_column("Latency")
        table.add_column("Tokens")
        for r in results:
            for t in r.get("tests", []):
                status_icon = "✅" if t.get("latency_ms") else "❌"
                table.add_row(
                    r["provider"], r["model"],
                    t.get("type", "?"),
                    f"{t.get('latency_ms', 0):.0f}ms" if t.get("latency_ms") else t.get("error", "?"),
                    str(t.get("tokens", "?")),
                )
        console.print(table)
        return 0

    if models_cmd == "switch":
        from core.model_providers.hybrid import get_platform
        platform = get_platform()
        msg = platform.set_mode_from_string(args.mode)
        from cli_visuals_new import print_system_msg
        print_system_msg(msg, "success")
        return 0

    if models_cmd == "start":
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
    from cli_server import ensure_server_running
    host = args.host or "127.0.0.1"
    port = args.port or 8000
    url = f"http://{host}:{port}/"
    check_host = "127.0.0.1" if host == "0.0.0.0" else host
    base_url = f"http://{check_host}:{port}"
    ensure_server_running(base_url, host, port)
    print(f"JARVIS server + web UI at {url}")
    if not args.no_open:
        webbrowser.open(url)
    return 0


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


def _parse_setting_value(val: str):
    try:
        import json as _json
        return _json.loads(val)
    except json.JSONDecodeError:
        pass
    if val.lower() == "true": return True
    if val.lower() == "false": return False
    if val.isdigit(): return int(val)
    try:
        return float(val)
    except ValueError:
        return val


def cmd_settings(args: argparse.Namespace) -> int:
    from core.settings.store import get_settings_store
    store = get_settings_store()

    def _try_config_registry(key: str):
        try:
            from core.config_registry import config as _cfg
            return _cfg.get(key, None)
        except KeyError:
            return None

    def _set_config_registry(key: str, val):
        try:
            from core.config_registry import config as _cfg
            _cfg.set(key, val)
            return True
        except Exception as e:
            logger.warning("Failed to set config registry key '%s': %s", key, e)
            return False

    if args.settings_command == "get":
        try:
            val = store.get(args.key)
            print(val)
        except KeyError:
            val = _try_config_registry(args.key)
            if val is not None:
                print(val)
            else:
                print(f"Error: Setting '{args.key}' not found.")
                return 1
    elif args.settings_command == "set":
        parsed_val = _parse_setting_value(args.value)
        try:
            if store.set(args.key, parsed_val):
                print(f"Successfully set {args.key} = {parsed_val}")
            else:
                if _set_config_registry(args.key, parsed_val):
                    print(f"Successfully set {args.key} = {parsed_val}")
                else:
                    print(f"Failed to set {args.key}")
                    return 1
        except Exception as e:
            logger.warning("Settings store failed for '%s': %s", args.key, e)
            if _set_config_registry(args.key, parsed_val):
                print(f"Successfully set {args.key} = {parsed_val}")
            else:
                print(f"Failed to set {args.key}")
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
        import re
        if not re.match(r'^[a-zA-Z][-a-zA-Z0-9_.]+$', pkg):
            print(f"JARVIS > Invalid package name: {pkg}")
            return 1
        confirm = input(f"Install plugin '{pkg}' from PyPI? [y/N] ").strip().lower()
        if confirm != 'y':
            print("JARVIS > Installation cancelled.")
            return 0
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
    elif args.plugin_action == "create":
        name = args.name
        plugins_dir = Path("plugins")
        plugin_dir = plugins_dir / name
        if plugin_dir.exists():
            print(f"Plugin '{name}' already exists at {plugin_dir}")
            return 1
        plugin_dir.mkdir(parents=True, exist_ok=True)
        manifest = {
            "name": f"jarvis.{name}",
            "version": "1.0.0",
            "description": f"Description for {name} plugin",
            "author": "JARVIS",
            "entry_point": f"{name}_plugin.py",
            "enabled": True,
            "hooks": ["on_load", "on_unload"],
        }
        manifest_path = plugin_dir / "plugin.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        py_content = f'''"""
plugins/{name}/{name}_plugin.py — {name} plugin for JARVIS.
"""
import logging
from core.plugins.base import Plugin
logger = logging.getLogger(__name__)

class {name.capitalize().replace("-", "")}Plugin(Plugin):
    def on_load(self):
        logger.info("[{name}] Plugin loaded")

    def on_unload(self):
        logger.info("[{name}] Plugin unloaded")
'''
        py_path = plugin_dir / f"{name}_plugin.py"
        py_path.write_text(py_content, encoding="utf-8")
        print(f"JARVIS > Plugin '{name}' created at {plugin_dir}")
        print(f"  📄 {manifest_path}")
        print(f"  🐍 {py_path}")
        print("Restart JARVIS or run 'jarvis plugin reload' to activate.")
        return 0
    return 1


def cmd_provider(args):
    import asyncio
    from core.providers.registry import provider_registry
    from core.providers.router import provider_router
    from core.providers.base import ExecutionResult, ProviderHealthStatus
    from core.providers.memory import provider_memory

    action = args.action
    rest = args.args or []

    if action == "list":
        providers = provider_registry.list_providers()
        if not providers:
            print("No providers registered")
            return 0
        print(f"{'ID':25s} {'Status':10s} {'Priority':10s} {'Performance':12s} {'Capabilities'}")
        print("-" * 95)
        for p in providers:
            status = "ENABLED" if p.enabled else "DISABLED"
            if not p.installed:
                status = "NOT_FOUND"
            perf = provider_memory.get_score(p.provider_id)
            perf_str = f"{perf*100:.0f}%" if perf > 0 else "---"
            caps = ", ".join(p.capabilities().capability_names[:5])
            if len(p.capabilities().capability_names) > 5:
                caps += f" (+{len(p.capabilities().capability_names) - 5})"
            priority = provider_registry.get_priority(p.provider_id)
            print(f"{p.provider_id:25s} {status:10s} {str(priority):10s} {perf_str:12s} {caps}")
        print(f"\nTotal: {len(providers)} providers")
        return 0

    elif action == "enable":
        if not rest:
            print("Usage: jarvis provider enable <provider_id>")
            return 1
        pid = rest[0]
        if provider_registry.enable(pid):
            print(f"Enabled provider: {pid}")
            return 0
        print(f"Provider not found: {pid}")
        return 1

    elif action == "disable":
        if not rest:
            print("Usage: jarvis provider disable <provider_id>")
            return 1
        pid = rest[0]
        if provider_registry.disable(pid):
            print(f"Disabled provider: {pid}")
            return 0
        print(f"Provider not found: {pid}")
        return 1

    elif action == "set-priority":
        if len(rest) < 2:
            print("Usage: jarvis provider set-priority <provider_id> <priority>")
            return 1
        pid = rest[0]
        try:
            priority = int(rest[1])
        except ValueError:
            print("Priority must be an integer")
            return 1
        if provider_registry.set_priority(pid, priority):
            print(f"Set priority for {pid} to {priority}")
            return 0
        print(f"Provider not found: {pid}")
        return 1

    elif action == "doctor":
        return asyncio.run(_cmd_provider_doctor())

    elif action == "install":
        if not rest:
            print("Usage: jarvis provider install <provider_id>")
            print("Known providers: " + ", ".join(sorted(_list_known_providers().keys())))
            return 1
        return asyncio.run(_cmd_provider_install(rest[0]))

    elif action == "benchmark":
        return asyncio.run(_cmd_provider_benchmark(rest))

    elif action == "info":
        if not rest:
            print("Usage: jarvis provider info <provider_id>")
            return 1
        return asyncio.run(_cmd_provider_info(rest[0]))

    elif action == "search":
        query = rest[0].lower() if rest else ""
        return _cmd_provider_search(query)

    return 1


def _list_known_providers():
    from core.providers.store import list_known_providers
    return list_known_providers()


async def _cmd_provider_doctor():
    from core.providers.registry import provider_registry
    from core.providers.base import ProviderHealthStatus
    from core.providers.memory import provider_memory

    providers = provider_registry.list_providers()
    if not providers:
        print("No providers registered")
        return 0

    print("Provider Health & Capability Coverage")
    print("=" * 60)
    print()

    all_caps: dict[str, list[tuple[str, bool, float]]] = {}
    results = {}

    import time
    for p in providers:
        pid = p.provider_id
        installed = "OK" if p.installed else "MISSING"
        enabled = "ON" if p.enabled else "OFF"
        print(f"  [{installed}/{enabled}] {pid:20s} ... ", end="")
        try:
            start = time.monotonic()
            health = await p.health()
            elapsed = (time.monotonic() - start) * 1000
            healthy = health.status == ProviderHealthStatus.HEALTHY
            if healthy:
                print(f"HEALTHY ({elapsed:.0f}ms)")
            elif health.status == ProviderHealthStatus.DEGRADED:
                print(f"DEGRADED ({elapsed:.0f}ms): {health.error}")
            else:
                print(f"DOWN: {health.error}")
            results[pid] = healthy
        except Exception as e:
            print(f"ERROR: {e}")
            results[pid] = False

        caps = p.capabilities()
        perf = provider_memory.get_score(pid)
        for cap in caps.capability_names:
            if cap not in all_caps:
                all_caps[cap] = []
            all_caps[cap].append((pid, results.get(pid, False), perf))

    print()
    print("Capability Coverage")
    print("-" * 60)
    for cap in sorted(all_caps.keys()):
        providers_for_cap = all_caps[cap]
        healthy_count = sum(1 for _, h, _ in providers_for_cap if h)
        total = len(providers_for_cap)
        bar_len = 20
        filled = int(bar_len * healthy_count / max(total, 1))
        bar = "█" * filled + "░" * (bar_len - filled)
        names = ", ".join(p for p, h, _ in providers_for_cap if h)
        if not names:
            names = "No healthy provider"
        print(f"  {cap:15s} {bar} {healthy_count}/{total}  {names}")

    print()
    ok_count = sum(1 for v in results.values() if v)
    print(f"Health: {ok_count}/{len(results)} providers healthy")
    return 0 if ok_count == len(results) else 1


async def _cmd_provider_install(provider_id: str):
    from core.providers.store import get_known_provider, write_manifest
    from core.providers.bootstrap import register_internal_providers, register_external_providers

    info = get_known_provider(provider_id)
    if not info:
        print(f"Unknown provider: {provider_id}")
        print("Known providers: " + ", ".join(sorted(_list_known_providers().keys())))
        print("To install a custom provider, place a manifest in ~/.jarvis/providers/manifests/")
        return 1

    pid = info["provider_id"]
    from core.providers.registry import provider_registry
    existing = provider_registry.get(pid)
    if existing:
        print(f"Provider {info['name']} is already installed")
        return 0

    write_manifest(provider_id)
    register_external_providers()
    from core.providers.bootstrap import scan_provider_plugins
    scan_provider_plugins()

    if provider_registry.get(pid):
        print(f"Installed: {info['name']} ({info['version']})")
        if info.get("install_hint"):
            print(f"NOTE: {info['install_hint']}")
        print(f"Enabled: {provider_registry.is_enabled(pid)}")
        return 0

    print(f"Registered manifest for {info['name']}")
    if info.get("install_hint"):
        print(f"To use: {info['install_hint']}")
    print("Then restart JARVIS or run: jarvis provider enable " + pid)
    return 0


async def _cmd_provider_benchmark(args: list[str]):
    import time
    from core.providers.registry import provider_registry
    from core.providers.benchmark import BenchmarkRunner, get_tasks, get_categories, TASKS
    from core.providers.benchmark_store import benchmark_store

    if "--leaderboard" in args or "-l" in args:
        category = None
        language = None
        for i, a in enumerate(args):
            if a in ("--category", "-c") and i + 1 < len(args):
                category = args[i + 1]
            if a in ("--language", "-lang") and i + 1 < len(args):
                language = args[i + 1]

        return _show_benchmark_leaderboard(benchmark_store, category, language)

    if "--results" in args or "-r" in args:
        provider = None
        category = None
        for i, a in enumerate(args):
            if a in ("--provider", "-p") and i + 1 < len(args):
                provider = args[i + 1]
            if a in ("--category", "-c") and i + 1 < len(args):
                category = args[i + 1]
        return _show_benchmark_results(benchmark_store, provider, category)

    if "--clear" in args:
        benchmark_store.clear()
        print("Benchmark data cleared")
        return 0

    if "--stats" in args or "-s" in args:
        return _show_benchmark_stats(benchmark_store)

    providers = provider_registry.list_providers()
    coding_providers = [p for p in providers if "coding" in p.capabilities().capability_names]
    if not coding_providers:
        print("No coding providers registered")
        return 1

    category = None
    for i, a in enumerate(args):
        if a in ("--category", "-c") and i + 1 < len(args):
            category = args[i + 1]

    print("Provider Benchmark Suite")
    print("=" * 60)
    if category:
        print(f"  Category: {category}")
        print()

    runner = BenchmarkRunner(store=benchmark_store)
    all_results: dict[str, list] = {}

    for p in coding_providers:
        pid = p.provider_id
        if not p.enabled:
            print(f"  [{pid}] SKIPPED (disabled)")
            continue
        if not p.installed:
            print(f"  [{pid}] SKIPPED (not installed)")
            continue

        tasks = get_tasks(category=category)
        print(f"  [{pid}] running {len(tasks)} benchmarks...")
        try:
            results = await runner.run_provider(p, category=category)
            all_results[pid] = results
        except Exception as e:
            print(f"  [{pid}] ERROR: {e}")
            continue

    print()
    return _show_benchmark_leaderboard(benchmark_store, category)


def _show_benchmark_leaderboard(store, category=None, language=None):
    from core.providers.benchmark_store import benchmark_store as bs
    leaderboard = store.get_leaderboard(category=category, language=language)
    if not leaderboard:
        print("No benchmark data yet. Run `jarvis provider benchmark` to collect data.")
        return 0

    print("Benchmark Leaderboard")
    print("=" * 70)
    if category:
        print(f"  Category: {category}")
    if language:
        print(f"  Language: {language}")
    print()

    print(f"{'Provider':20s} {'Category':15s} {'Language':12s} {'Quality':8s} {'Success':8s} {'Avg Dur':8s} {'Runs':6s}")
    print("-" * 70)
    for row in leaderboard:
        pid = row["provider_id"][:18]
        cat = row["category"][:13]
        lang = row["language"][:10] if row["language"] else "-"
        qual = f"{row['avg_quality']*100:.0f}%"
        succ = f"{row['success_rate']*100:.0f}%"
        dur = f"{row['avg_duration_ms']:.0f}ms"
        runs = str(row["runs"])
        print(f"{pid:20s} {cat:15s} {lang:12s} {qual:8s} {succ:8s} {dur:8s} {runs:6s}")
    print()

    print("Top Recommendations:")
    print("-" * 70)
    seen_cats: set[str] = set()
    for row in leaderboard:
        cat_key = f"{row['category']}/{row['language']}"
        if cat_key not in seen_cats and row['runs'] >= 2:
            seen_cats.add(cat_key)
            print(f"  {row['category']:15s} ({row['language'] or 'any':10s}) → {row['provider_id']:20s}  ({row['avg_quality']*100:.0f}% quality, {row['avg_duration_ms']:.0f}ms)")
    return 0


def _show_benchmark_results(store, provider=None, category=None):
    results = store.get_results(provider_id=provider, category=category)
    if not results:
        print("No benchmark results found.")
        return 0

    print(f"{'Task':30s} {'Provider':15s} {'Status':8s} {'Quality':8s} {'Duration':10s}")
    print("-" * 70)
    for r in results:
        status = "PASS" if r["success"] else "FAIL"
        qual = f"{r['quality_score']*100:.0f}%"
        dur = f"{r['duration_ms']:.0f}ms"
        task = r["task_id"][:28]
        pid = r["provider_id"][:13]
        print(f"{task:30s} {pid:15s} {status:8s} {qual:8s} {dur:10s}")
    print(f"\n{len(results)} results")
    return 0


def _show_benchmark_stats(store):
    stats = store.get_stats()
    print("Benchmark Statistics")
    print("=" * 40)
    print(f"  Total benchmark runs: {stats['total_runs']}")
    print(f"  Providers tested: {stats['providers']}")
    print(f"  Categories: {stats['categories']}")
    if stats["last_run"]:
        from datetime import datetime
        last = datetime.fromtimestamp(stats["last_run"])
        print(f"  Last run: {last.strftime('%Y-%m-%d %H:%M:%S')}")
    return 0


async def _cmd_provider_info(provider_id: str):
    from core.providers.registry import provider_registry
    from core.providers.memory import provider_memory
    from core.providers.budget import provider_budget
    from core.providers.store import get_known_provider

    p = provider_registry.get(provider_id)
    if not p:
        known = get_known_provider(provider_id)
        if known:
            print(f"Provider '{known['name']}' is known but not installed")
            print(f"  Install hint: {known.get('install_hint', '')}")
            return 0
        print(f"Provider not found: {provider_id}")
        return 1

    print(f"Provider: {p.name} ({p.provider_id})")
    print(f"  Version: {p.version}")
    print(f"  Status: {'ENABLED' if p.enabled else 'DISABLED'}")
    print(f"  Installed: {p.installed}")
    print(f"  Priority: {provider_registry.get_priority(p.provider_id)}")
    print()
    caps = p.capabilities()
    print(f"  Capabilities ({len(caps.capability_names)}):")
    for c in caps.capability_names:
        print(f"    - {c}")
    if caps.languages:
        print(f"  Languages: {', '.join(caps.languages)}")
    print()
    record = provider_memory.get_record(provider_id)
    if record:
        print(f"  Performance:")
        print(f"    Executions: {record.total_executions}")
        print(f"    Success rate: {record.success_rate*100:.0f}%")
        print(f"    Avg duration: {record.avg_duration_ms:.0f}ms")
        print(f"    Avg cost: ${record.avg_cost:.4f}")
        print(f"    Consecutive failures: {record.consecutive_failures}")
    print()
    budget_rec = provider_budget.get_record(provider_id)
    if budget_rec:
        print(f"  Budget:")
        print(f"    Total spent: ${budget_rec.total_spent:.2f}")
        print(f"    Total tokens: {budget_rec.total_tokens}")
        print(f"    Daily cost: ${budget_rec.daily_cost:.2f}")
        print(f"    Monthly cost: ${budget_rec.monthly_cost:.2f}")
    return 0


def _cmd_provider_search(query: str):
    from core.providers.store import list_known_providers
    import shutil

    known = list_known_providers()
    if query:
        matches = {k: v for k, v in known.items() if query in k or query in v.get("name", "").lower() or any(query in c.get("name", "") for c in v.get("capabilities", []))}
    else:
        matches = known

    if not matches:
        print(f"No providers matching '{query}'")
        return 0

    print(f"{'ID':25s} {'Name':20s} {'Status':12s} {'Capabilities'}")
    print("-" * 80)
    for pid, info in sorted(matches.items()):
        cmd = info.get("health_command", "").split()[0] if info.get("health_command") else ""
        installed = "INSTALLED" if (cmd and shutil.which(cmd)) else "AVAILABLE"
        caps = ", ".join(c.get("name", "") for c in info.get("capabilities", [])[:3])
        print(f"{pid:25s} {info['name']:20s} {installed:12s} {caps}")
    print(f"\n{len(matches)} providers found")
    return 0


def cmd_orchestrate(args):
    """Multi-provider orchestration: compose teams of providers."""
    import asyncio

    goal = args.goal
    if not goal and not args.plan_only:
        goal = input("Goal: ").strip()
    if not goal:
        print("Usage: jarvis orchestrate <goal> [--plan-only]")
        return 1

    from core.providers.orchestration import OrchestrationPlanner, Orchestrator

    planner = OrchestrationPlanner()
    plan = planner.plan(goal, context={
        "language": getattr(args, "language", ""),
        "framework": getattr(args, "framework", ""),
    })

    print("\nOrchestration Plan")
    print("=" * 60)
    print(f"  Goal: {plan.goal}")
    print(f"  Steps: {plan.total_steps}")
    print(f"  Providers: {plan.provider_count()}")
    print()
    for step in plan.steps:
        dep_str = ""
        if step.dependencies:
            dep_str = f" → after [{', '.join(d.step_id for d in step.dependencies)}]"
        print(f"  [{step.step_id}]")
        print(f"    Label:     {step.label}")
        print(f"    Provider:  {step.provider_id}")
        print(f"    Chain:     {step.chain_type.value}")
        print(f"    Capability: {step.task.get('capability', '?')}{dep_str}")
        print()

    if args.plan_only:
        print("Plan only mode — not executing.")
        return 0

    confirm = input("Execute this orchestration plan? [Y/n]: ").strip().lower()
    if confirm and confirm not in ("y", "yes", ""):
        print("Aborted.")
        return 0

    print("\nExecuting orchestration plan...")
    print("-" * 60)

    orchestrator = Orchestrator()
    result = asyncio.run(orchestrator.execute(plan))

    print()
    print(result.summary())
    print()

    if result.overall_success:
        print("✓ Orchestration completed successfully")
    else:
        print(f"✗ Orchestration failed: {result.error or 'Unknown error'}")

    merged = result.collect_artifacts()
    if merged:
        print(f"\nArtifacts produced: {len(merged)}")
        for key, val in list(merged.items())[:5]:
            print(f"  {key}: {val[:80]}...")

    return 0 if result.overall_success else 1


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
    from core.setup.engine import SetupEngine

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

    engine.run_full_setup(on_message=on_message, on_confirm=on_confirm, on_choice=on_choice)
    return 0


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


def cmd_status(args: argparse.Namespace) -> int:
    from cli_visuals_new import render_agent_status, print_system_msg
    import httpx
    
    env = common_env()
    base_url = env.get("JARVIS_SERVER", "http://127.0.0.1:8000")
    
    print_system_msg("Probing Neural Network Status...", "info")
    
    agents = [
        {"name": "MAESTRO", "role": "Orchestrator", "ready": True},
        {"name": "NEXUS", "role": "Research", "ready": True},
        {"name": "FORGE", "role": "Code", "ready": True},
        {"name": "ORACLE", "role": "Planning", "ready": True},
        {"name": "CIPHER", "role": "Security", "ready": True},
        {"name": "HERALD", "role": "Comms", "ready": True},
        {"name": "ATLAS", "role": "Data", "ready": True},
        {"name": "SCRIBE", "role": "Docs", "ready": True},
        {"name": "SENTINEL", "role": "Monitor", "ready": True},
    ]
    
    render_agent_status(agents)
    
    try:
        resp = httpx.get(f"{base_url}/api/health", timeout=2.0)
        if resp.status_code == 200:
            print_system_msg(f"Backend Core: ONLINE ({base_url})", "success")
        else:
            print_system_msg(f"Backend Core: DEGRADED ({resp.status_code})", "warning")
    except Exception as e:
        logger.warning("Backend health check failed: %s", e)
        print_system_msg(f"Backend Core: OFFLINE", "error")
        
    return 0


def cmd_doctor(args):
    """Run production doctor — feature audit, model check, memory usage, API status."""
    from cli_visuals_new import print_system_msg
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel

    console = Console()
    print_system_msg("Running JARVIS Production Doctor...", "info")

    # Setup status
    try:
        from core.setup.engine import SetupEngine
        engine = SetupEngine()
        s = engine.status()
        phase = s["phase"]
        phase_style = {"complete": "green", "in_progress": "yellow", "failed": "red", "not_started": "dim"}
        style = phase_style.get(phase, "white")
        lines = [
            f"[bold]Phase:[/] [{style}]{phase}[/]",
            f"[bold]Default model:[/] {s['recommended_model']['name']}",
            f"[bold]Hardware:[/] {s['hardware']['ram_gb']}GB RAM / {s['hardware']['gpu_name'] or 'No GPU'} / {s['hardware']['os']}",
        ]
        for name, status in s["checks"].items():
            icon = "✓" if status == "ok" else ("○" if status == "missing" else "x")
            lines.append(f"  {icon} {name}: {status}")
        console.print(Panel("\n".join(lines), title="Setup", border_style="cyan"))
    except Exception as e:
        console.print(f"[dim]Setup status unavailable: {e}[/]")

    try:
        from core.feature_registry import get_feature_report
        report = get_feature_report()
        table = Table(title="Feature Status", border_style="cyan")
        table.add_column("Feature", style="bold")
        table.add_column("Status", style="bold")
        table.add_column("Enabled")
        for f in report["features"]:
            status_style = {"stable": "green", "beta": "yellow", "experimental": "blue", "broken": "red", "planned": "dim"}
            style = status_style.get(f["status"], "white")
            table.add_row(f["name"], f"[{style}]{f['status']}[/]", "✅" if f["enabled"] else "❌")
        console.print(table)
        console.print(f"\n[bold]Summary:[/] {report['enabled']} enabled / {report['disabled']} disabled / {report['stable']} stable / {report['beta']} beta / {report['broken']} broken / {report['planned']} planned")
    except Exception as e:
        console.print(f"[red]Feature audit failed: {e}[/]")

    try:
        from core.diagnostics import build_diagnostic_report
        diag = build_diagnostic_report()
        console.print(Panel(f"[bold]Source Diagnostics:[/] {diag.status.upper()} — {len(diag.issues)} issues found", border_style="yellow"))
        for issue in diag.issues[:10]:
            sev_style = {"critical": "red", "high": "yellow", "medium": "blue", "low": "dim"}
            s = sev_style.get(issue.severity, "white")
            console.print(f"  [{s}]{issue.severity.upper():8s}[/] {issue.category:20s} {issue.path} — {issue.message}")
        if diag.capability_gaps:
            console.print(f"\n[bold]Capability Gaps:[/] {len(diag.capability_gaps)}")
            for g in diag.capability_gaps[:3]:
                console.print(f"  • {g}")
    except Exception as e:
        console.print(f"[red]Diagnostics failed: {e}[/]")

    try:
        from core.model_providers import get_router
        router = get_router()
        import asyncio
        health = asyncio.run(router.health_check())
        table = Table(title="Model Provider Health", border_style="blue")
        table.add_column("Provider", style="bold")
        table.add_column("Available")
        table.add_column("Healthy")
        table.add_column("Latency")
        for name, status in health.items():
            table.add_row(name, "✅" if status.available else "❌", "✅" if status.healthy else "❌", f"{status.latency_ms:.0f}ms")
        console.print(table)
    except Exception as e:
        console.print(f"[red]Model health check failed: {e}[/]")

    try:
        from core.environment_monitor import environment_monitor
        env = environment_monitor.check()
        console.print(Panel(
            f"Disk: {env.disk_free_gb:.1f} GB free  |  Memory: {env.memory_free_mb:.0f} MB free  |  "
            f"Ollama: {'✓' if env.ollama_available else '✗'} ({env.ollama_latency_ms:.0f}ms)  |  "
            f"Network: {'✓' if env.network_reachable else '✗'}",
            title="Environment", border_style="green",
        ))
    except Exception as e:
        console.print(f"[red]Environment check failed: {e}[/]")

    try:
        from core.integration_manager import health_check_all
        import asyncio
        integ_health = asyncio.run(health_check_all())
        table = Table(title="Integration Status", border_style="magenta")
        table.add_column("Integration", style="bold")
        table.add_column("Connected")
        table.add_column("Healthy")
        for name, status in integ_health.items():
            table.add_row(name, "✅" if status.get("connected") else "❌", "✅" if status.get("healthy") else "❌")
        console.print(table)
    except Exception as e:
        console.print(f"[red]Integration health check failed: {e}[/]")

    try:
        console.print(Panel("[bold]Voice Diagnostics[/]", border_style="cyan"))
        try:
            import sounddevice as sd
            sd_version = sd.__version__
            try:
                devices = sd.query_devices()
                input_devs = [d for d in devices if d["max_input_channels"] > 0]
                output_devs = [d for d in devices if d["max_output_channels"] > 0]
                console.print(f"  sounddevice {sd_version}: {len(input_devs)} input, {len(output_devs)} output devices")
                if input_devs:
                    default = sd.default.device
                    if isinstance(default, tuple):
                        default = default[0]
                    console.print(f"  Default input device: {default} — {sd.query_devices(default)['name']}")
                else:
                    console.print("  [red]No input devices found! Microphone required for voice.[/]")
            except Exception as e:
                console.print(f"  [red]sounddevice query failed: {e}[/]")
        except ImportError:
            console.print("  [red]sounddevice not installed! Install: pip install sounddevice[/]")
        try:
            import webrtcvad
            console.print(f"  webrtcvad: installed (mode={webrtcvad.Vad(1) is not None})")
        except ImportError:
            console.print("  [red]webrtcvad not installed! Install: pip install webrtcvad-wheels[/]")
        try:
            from assistant.tts import get_tts
            tts = get_tts()
            console.print(f"  TTS: initialized ({tts.voice})")
        except Exception as e:
            console.print(f"  [red]TTS init failed: {e}[/]")
        try:
            from assistant.stt import get_stt
            stt = get_stt()
            console.print(f"  STT: initialized ({type(stt).__name__})")
        except Exception as e:
            console.print(f"  [red]STT init failed: {e}[/]")
        from core.config_registry import config as _jc
        mode = _jc.get("voice.mode", "push-to-talk")
        provider = _jc.get("voice.tts_provider", "unknown")
        console.print(f"  Voice mode: {mode}  |  TTS provider: {provider}")
    except Exception as e:
        console.print(f"[red]Voice diagnostics failed: {e}[/]")

    try:
        from core.providers.registry import provider_registry
        from core.providers.base import ProviderHealthStatus
        providers = provider_registry.list_providers()
        if providers:
            console.print(Panel("[bold]Capability Coverage[/]", border_style="green"))
            all_caps: dict[str, list[str]] = {}
            for p in providers:
                for cap in p.capabilities().capability_names:
                    if cap not in all_caps:
                        all_caps[cap] = []
                    all_caps[cap].append(p.provider_id)
            for cap in sorted(all_caps.keys()):
                names = all_caps[cap]
                healthy_count = sum(1 for p in providers if p.provider_id in names and p.enabled and p.installed)
                total = len(names)
                bar_len = 20
                filled = int(bar_len * healthy_count / max(total, 1))
                bar = "█" * filled + "░" * (bar_len - filled)
                console.print(f"  [bold]{cap:15s}[/] {bar} {healthy_count}/{total}")
    except Exception as e:
        logger.warning("Capability coverage check failed: %s", e)

    if getattr(args, 'json', False):
        import json as _json
        try:
            from core.feature_registry import get_feature_report
            console.print(_json.dumps(get_feature_report(), indent=2))
        except Exception as e:
            logger.warning("JSON feature report failed: %s", e)

    print_system_msg("Doctor complete.", "success")
    return 0


def cmd_diagnostics(args):
    """Diagnostics dashboard — model health, integration health, voice health, feature audit."""
    from cli_visuals_new import print_system_msg
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    import asyncio
    console = Console()

    sub = getattr(args, 'diag_command', None)

    if sub == "models":
        print_system_msg("Model Health Diagnostics", "info")
        try:
            from core.model_providers import get_router
            router = get_router()
            health = asyncio.run(router.health_check())
            table = Table(title="Model Provider Health", border_style="blue")
            table.add_column("Provider", style="bold")
            table.add_column("Available")
            table.add_column("Healthy")
            table.add_column("Latency")
            for name, status in health.items():
                table.add_row(name, "✅" if status.available else "❌",
                              "✅" if status.healthy else "❌",
                              f"{status.latency_ms:.0f}ms")
            console.print(table)
        except Exception as e:
            console.print(f"[red]Model health check failed: {e}[/]")

    elif sub == "integrations":
        print_system_msg("Integration Health Diagnostics", "info")
        try:
            from core.integration_manager import health_check_all
            health = asyncio.run(health_check_all())
            table = Table(title="Integration Status", border_style="magenta")
            table.add_column("Integration", style="bold")
            table.add_column("Connected")
            table.add_column("Healthy")
            for name, status in health.items():
                table.add_row(name, "✅" if status.get("connected") else "❌",
                              "✅" if status.get("healthy") else "❌")
            console.print(table)
        except Exception as e:
            console.print(f"[red]Integration health check failed: {e}[/]")

    elif sub == "voice":
        print_system_msg("Voice Health Diagnostics", "info")
        try:
            from core.config_registry import config as _jc
            mode = _jc.get("voice.mode", "push-to-talk")
            stt = _jc.get("voice.stt_provider", "faster-whisper")
            tts = _jc.get("voice.tts_provider", "edge-tts")
            wake = _jc.get("voice.wake_word_enabled", False)
            console.print(Panel(
                f"Mode: {mode}\nSTT: {stt}\nTTS: {tts}\nWake word: {'✅' if wake else '❌'}",
                title="Voice Configuration", border_style="cyan"))
            try:
                import sounddevice as sd
                devices = sd.query_devices()
                input_devs = [d for d in devices if d["max_input_channels"] > 0]
                console.print(f"Audio: {len(input_devs)} input devices")
            except ImportError:
                console.print("[red]sounddevice not installed[/]")
            try:
                from assistant.stt import get_stt
                stt_inst = get_stt()
                console.print(f"STT: initialized ({type(stt_inst).__name__})")
            except Exception as e:
                console.print(f"[red]STT init failed: {e}[/]")
            try:
                from assistant.tts import get_tts
                tts_inst = get_tts()
                console.print(f"TTS: initialized ({tts_inst.voice})")
            except Exception as e:
                console.print(f"[red]TTS init failed: {e}[/]")
        except Exception as e:
            console.print(f"[red]Voice diagnostics failed: {e}[/]")

    elif sub == "features":
        print_system_msg("Feature Audit", "info")
        try:
            from core.feature_registry import get_feature_report
            report = get_feature_report()
            table = Table(title="Feature Status", border_style="cyan")
            table.add_column("Feature", style="bold")
            table.add_column("Status")
            table.add_column("Enabled")
            for f in report["features"]:
                status_style = {"stable": "green", "beta": "yellow", "experimental": "blue",
                               "broken": "red", "planned": "dim"}
                s = status_style.get(f["status"], "white")
                table.add_row(f["name"], f"[{s}]{f['status']}[/]", "✅" if f["enabled"] else "❌")
            console.print(table)
            console.print(f"\n[bold]Summary:[/] {report['enabled']} enabled / {report['disabled']} disabled / "
                          f"{report['stable']} stable / {report['broken']} broken")
        except Exception as e:
            console.print(f"[red]Feature audit failed: {e}[/]")

    else:
        return cmd_doctor(args)

    return 0


def cmd_home(args):
    """Home dashboard — show overall system status."""
    from cli_visuals_new import print_system_msg
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.layout import Layout
    console = Console()
    print_system_msg("JARVIS Home Dashboard", "info")

    try:
        from core.feature_registry import get_feature_report
        report = get_feature_report()
        stable_pct = round(report["stable"] / max(report["total"], 1) * 100)
        enabled_pct = round(report["enabled"] / max(report["total"], 1) * 100)
        console.print(Panel(
            f"[bold]Features:[/] {report['enabled']} enabled / {report['total']} total\n"
            f"[green]{stable_pct}% stable[/] — [yellow]{report['beta']} beta[/] — "
            f"[red]{report['broken']} broken[/] — [dim]{report['planned']} planned[/]\n"
            f"[bold]Status:[/] {'✅ All stable' if report['broken'] == 0 else '⚠️ ' + str(report['broken']) + ' broken'}",
            title="System Health", border_style="cyan"))
    except Exception as e:
        console.print(f"[red]Feature report failed: {e}[/]")

    try:
        from core.diagnostics import build_diagnostic_report
        diag = build_diagnostic_report()
        console.print(Panel(
            f"Status: [{'green' if diag.status == 'ok' else 'yellow'}]{diag.status.upper()}[/]\n"
            f"Issues: {len(diag.issues)}\n"
            f"Capability Gaps: {len(diag.capability_gaps)}",
            title="Diagnostics", border_style="green" if diag.status == "ok" else "yellow"))
    except Exception as e:
        logger.warning("Diagnostics import failed: %s", e)

    try:
        from core.model_providers.hybrid import get_platform
        import asyncio
        platform = get_platform()
        mode = platform.mode.value.upper()
        models = asyncio.run(platform.list_models())
        healthy = sum(1 for m in models if m.status == "healthy")
        console.print(Panel(
            f"Mode: [bold]{mode}[/]\n"
            f"Providers: {len(models)} total, [green]{healthy} healthy[/]",
            title="Models", border_style="blue"))
    except Exception as e:
        logger.warning("Models import failed: %s", e)

    try:
        from core.integration_manager import get_integration_manager
        mgr = get_integration_manager()
        integrations = mgr.list_integrations()
        connected = sum(1 for i in integrations if i["connected"])
        console.print(Panel(
            f"Integrations: {len(integrations)} total, [green]{connected} connected[/]",
            title="Integrations", border_style="magenta"))
    except Exception as e:
        logger.warning("Integrations import failed: %s", e)

    try:
        from core.sub_agents.registry import agent_registry
        agents = agent_registry.list_agents()
        console.print(Panel(
            f"Agents: [bold]{len(agents)}[/] registered",
            title="Agents", border_style="yellow"))
    except Exception as e:
        logger.warning("Agent registry import failed: %s", e)

    try:
        mem_mgr = _get_memory_manager()
        entries = _get_memory_count(mem_mgr)
        console.print(Panel(
            f"Memory entries: [bold]{entries}[/]",
            title="Memory", border_style="green"))
    except Exception as e:
        logger.warning("Memory manager import failed: %s", e)

    print_system_msg("Use /help for available commands, or run a subcommand like 'jarvis models list'", "info")
    return 0


def _get_memory_manager():
    from core.memory import MemoryManager
    from pathlib import Path
    data_dir = str(Path.home() / ".jarvis")
    return MemoryManager(data_dir=data_dir)


def _get_memory_count(mgr=None) -> int:
    if mgr is None:
        mgr = _get_memory_manager()
    try:
        return len(mgr.load_all())
    except Exception as e:
        logger.warning("Memory count failed: %s", e)
        return 0


def cmd_features(args):
    """Feature Registry — list, explore, and toggle features."""
    from cli_visuals_new import print_system_msg
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    console = Console()
    print_system_msg("Feature Registry", "info")

    action = getattr(args, 'feature_command', None) or getattr(args, 'action', None)

    if action == "explore" or action == "show":
        slug = getattr(args, 'slug', None)
        if slug:
            try:
                from core.feature_registry import FEATURES, get_status, is_enabled, Feature
                feature = FEATURES.get(slug)
                if not feature:
                    console.print(f"[red]Feature not found: {slug}[/]")
                    return 1
                status = get_status(slug).value.upper()
                enabled = is_enabled(slug)
                console.print(Panel(
                    f"[bold]{feature.name}[/]\n\n"
                    f"Slug: {slug}\n"
                    f"Category: {feature.category}\n"
                    f"Status: [{'green' if status == 'STABLE' else 'yellow'}]{status}[/]\n"
                    f"Enabled: {'✅' if enabled else '❌'}\n"
                    f"Default: {'✅' if feature.enabled_by_default else '❌'}\n"
                    f"Config key: {feature.config_key or 'N/A'}\n"
                    f"Docs: {feature.docs_path or 'N/A'}\n"
                    f"Dependencies: {', '.join(feature.dependencies) or 'None'}\n\n"
                    f"{feature.description}",
                    title=f"Feature: {slug}", border_style="cyan"))

                if feature.health_check_fn:
                    try:
                        mod_path, _, fn_name = feature.health_check_fn.rpartition(":")
                        if mod_path and fn_name:
                            import importlib, asyncio
                            mod = importlib.import_module(mod_path)
                            fn = getattr(mod, fn_name)
                            result = asyncio.run(fn() if asyncio.iscoroutinefunction(fn) else fn())
                            console.print(f"[green]Health check: OK[/]")
                            console.print(str(result)[:200])
                    except Exception as e:
                        console.print(f"[red]Health check failed: {e}[/]")
            except Exception as e:
                console.print(f"[red]Feature detail failed: {e}[/]")
        else:
            console.print("[yellow]Usage: jarvis features explore <slug>[/]")
        return 0

    if action == "toggle":
        slug = getattr(args, 'slug', None)
        enabled = getattr(args, 'enabled', True)
        if slug:
            try:
                from core.feature_registry import FEATURES, set_status, FeatureStatus
                from core.config_registry import config
                if slug not in FEATURES:
                    console.print(f"[red]Feature not found: {slug}[/]")
                    return 1
                config.set(f"feature.{slug}.enabled", enabled)
                new_status = FeatureStatus.STABLE if enabled else FeatureStatus.BROKEN
                set_status(slug, new_status)
                console.print(f"[green]Feature '{slug}' {'enabled' if enabled else 'disabled'}[/]")
            except Exception as e:
                console.print(f"[red]Toggle failed: {e}[/]")
        else:
            console.print("[yellow]Usage: jarvis features toggle <slug> [--off][/]")
        return 0

    # Default: list all features
    try:
        from core.feature_registry import get_all_features, get_feature_report
        report = get_feature_report()
        console.print(f"Total: {report['total']} | "
                      f"[green]Stable: {report['stable']}[/] | "
                      f"[yellow]Beta: {report['beta']}[/] | "
                      f"[red]Broken: {report['broken']}[/] | "
                      f"[dim]Planned: {report['planned']}[/]")

        table = Table(title=f"All Features ({report['total']})", border_style="cyan")
        table.add_column("Feature", style="bold")
        table.add_column("Slug")
        table.add_column("Category")
        table.add_column("Status")
        table.add_column("Enabled")
        for f in report["features"]:
            status_style = {"stable": "green", "beta": "yellow", "experimental": "blue",
                           "broken": "red", "planned": "dim"}
            s = status_style.get(f["status"], "white")
            table.add_row(
                f["name"][:50],
                f["slug"],
                f["category"],
                f"[{s}]{f['status']}[/]",
                "✅" if f["enabled"] else "❌",
            )
        console.print(table)
        console.print("\n[yellow]Explore a feature:[/] jarvis features explore <slug>")
        console.print("[yellow]Toggle a feature:[/] jarvis features toggle <slug> [--off]")
    except Exception as e:
        console.print(f"[red]Feature registry unavailable: {e}[/]")

    return 0


def cmd_voice(args):
    """Voice dashboard — STT, TTS, wake word status."""
    from cli_visuals_new import print_system_msg
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    console = Console()
    print_system_msg("Voice Dashboard", "info")

    try:
        from core.config_registry import config as _jc
        mode = _jc.get("voice.mode", "push-to-talk")
        stt_provider = _jc.get("voice.stt_provider", "faster-whisper")
        tts_provider = _jc.get("voice.tts_provider", "edge-tts")
        wake_enabled = _jc.get("voice.wake_word_enabled", False)
        console.print(Panel(
            f"Voice mode: [bold]{mode}[/]\n"
            f"STT: {stt_provider}\n"
            f"TTS: {tts_provider}\n"
            f"Wake word: {'✅ Enabled' if wake_enabled else '❌ Disabled'}",
            title="Voice Configuration", border_style="cyan"))
    except Exception as e:
        console.print(f"[red]Config read failed: {e}[/]")

    try:
        import sounddevice as sd
        devices = sd.query_devices()
        input_devs = [d for d in devices if d["max_input_channels"] > 0]
        output_devs = [d for d in devices if d["max_output_channels"] > 0]
        console.print(Panel(
            f"Input devices: {len(input_devs)}\n"
            f"Output devices: {len(output_devs)}",
            title="Audio Hardware", border_style="blue"))
    except Exception as e:
        logger.warning("sounddevice query failed: %s", e)
        console.print("[yellow]sounddevice not available[/]")

    if args.voice_command == "test":
        print_system_msg("Voice system test passed (components initialized)", "success")
    elif args.voice_command == "providers":
        table = Table(title="Available Providers", border_style="cyan")
        table.add_column("Type", style="bold")
        table.add_column("Provider")
        table.add_column("Status")
        providers = [
            ("STT", "faster-whisper", "local"),
            ("STT", "deepgram", "cloud"),
            ("STT", "azure", "cloud"),
            ("TTS", "kokoro", "local"),
            ("TTS", "edge-tts", "cloud"),
        ]
        for tp, prov, kind in providers:
            table.add_row(tp, prov, kind)
        console.print(table)

    return 0


def cmd_automation(args):
    """Automation dashboard — goals, phases, logs, repair cycles."""
    from cli_visuals_new import print_system_msg
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    console = Console()
    print_system_msg("Automation Dashboard", "info")

    if args.automation_command == "status" or not args.automation_command:
        try:
            from brain.automation.loop import build_loop
            loop = build_loop()
            status = loop.get_status() if hasattr(loop, 'get_status') else {}
            phase = status.get("phase", "idle")
            goal = status.get("goal", "No active goal")
            progress = status.get("progress", 0)
            repair_cycles = status.get("repair_cycles", 0)
            completion = status.get("completion_pct", 0)
            logs = status.get("logs", [])
            console.print(Panel(
                f"Goal: [bold]{goal}[/]\n"
                f"Phase: {phase}\n"
                f"Progress: {progress}%\n"
                f"Repair cycles: {repair_cycles}\n"
                f"Completion: {completion}%",
                title="Active Automation", border_style="cyan"))
            if logs:
                log_table = Table(title="Recent Logs", border_style="blue")
                log_table.add_column("Time")
                log_table.add_column("Message")
                for log in logs[-5:]:
                    log_table.add_row(log.get("time", ""), log.get("message", ""))
                console.print(log_table)
        except Exception as e:
            console.print(f"[yellow]Automation loop not available: {e}[/]")
            console.print(Panel(
                "Use [bold]/goal <goal>[/] to start automation\n"
                "Use [bold]/develop <goal>[/] for development workflow\n"
                "Use [bold]/build <goal>[/] for autonomous build",
                title="Quick Start", border_style="green"))

    elif args.automation_command == "goals":
        console.print("[yellow]Active goals feature requires backend /api/horizon/goals endpoint[/]")

    elif args.automation_command == "repair":
        try:
            from core.pattern_failure_memory import pattern_memory
            stats = pattern_memory.get_stats()
            table = Table(title="Repair Pattern Memory", border_style="yellow")
            table.add_column("Pattern", style="bold")
            table.add_column("Count")
            table.add_column("Fix Strategy")
            for p in stats.get("top_patterns", []):
                table.add_row(p["pattern"][:50], str(p["count"]), p["fix"][:40])
            console.print(table)
            console.print(f"\nTotal patterns: {stats['total_patterns']}")
            console.print(f"Total fixes applied: {stats['total_fixes_applied']}")
        except Exception as e:
            console.print(f"[red]Repair memory unavailable: {e}[/]")

    elif args.automation_command == "architectural":
        try:
            from brain.automation.loop import ArchitecturalMemory
            arch = ArchitecturalMemory()
            table = Table(title="Architectural Memory", border_style="blue")
            table.add_column("Project Type", style="bold")
            table.add_column("Lessons")
            table.add_column("Components")
            table.add_column("Hits")
            for key, entry in arch._patterns.items():
                table.add_row(
                    entry.get("project_type", key),
                    str(len(entry.get("lessons", []))),
                    ", ".join(entry.get("required_components", [])),
                    str(entry.get("hit_count", 0)),
                )
            console.print(table)
        except Exception as e:
            console.print(f"[yellow]Architectural memory not available: {e}[/]")

    return 0


def cmd_memory(args):
    """Memory dashboard — memories, vector store, failure memory, architectural memory."""
    from cli_visuals_new import print_system_msg
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    console = Console()
    print_system_msg("Memory Dashboard", "info")

    action = getattr(args, 'memory_command', None) or getattr(args, 'action', None)

    if action == "list" or not action:
        try:
            from core.memory import MemoryManager
            from pathlib import Path
            data_dir = str(Path.home() / ".jarvis")
            mgr = MemoryManager(data_dir=data_dir)
            entries = mgr.load_all()
            table = Table(title=f"Memory Entries ({len(entries)})", border_style="green")
            table.add_column("ID", style="dim")
            table.add_column("Text")
            table.add_column("Category")
            table.add_column("Uses")
            table.add_column("Source")
            for e in entries[-20:]:
                table.add_row(
                    e.get("id", "?")[:8],
                    e.get("text", "")[:60],
                    e.get("category", ""),
                    str(e.get("uses", 0)),
                    e.get("source", ""),
                )
            console.print(table)
        except Exception as ex:
            console.print(f"[red]Memory load failed: {ex}[/]")

    elif action == "vector":
        try:
            from core.memory_vector import MemoryVectorStore
            from pathlib import Path
            data_dir = str(Path.home() / ".jarvis")
            vstore = MemoryVectorStore(data_dir=data_dir)
            count = vstore.count()
            console.print(Panel(
                f"Vector store: {'✅ Healthy' if vstore.healthy else '❌ Unhealthy'}\n"
                f"Entries: {count}",
                title="Vector Memory", border_style="cyan"))
        except Exception as e:
            console.print(f"[yellow]Vector store not available: {e}[/]")

    elif action == "failure":
        try:
            from core.pattern_failure_memory import pattern_memory
            stats = pattern_memory.get_stats()
            table = Table(title="Failure Memory", border_style="red")
            table.add_column("Pattern")
            table.add_column("Count")
            table.add_column("Fix")
            for p in stats.get("top_patterns", []):
                table.add_row(p["pattern"][:60], str(p["count"]), p["fix"][:40])
            console.print(table)
            console.print(f"\nTotal patterns: [bold]{stats['total_patterns']}[/]")
            console.print(f"Total fixes applied: [bold]{stats['total_fixes_applied']}[/]")
        except Exception as e:
            console.print(f"[red]Failure memory unavailable: {e}[/]")

    elif action == "architectural":
        try:
            from brain.automation.loop import ArchitecturalMemory
            arch = ArchitecturalMemory()
            if not arch._patterns:
                console.print("[yellow]No architectural patterns learned yet[/]")
            else:
                table = Table(title="Architectural Memory", border_style="blue")
                table.add_column("Project")
                table.add_column("Lessons")
                table.add_column("Components")
                table.add_column("Hits")
                for key, entry in arch._patterns.items():
                    table.add_row(
                        entry.get("project_type", key),
                        str(len(entry.get("lessons", []))),
                        ", ".join(entry.get("required_components", []))[:40],
                        str(entry.get("hit_count", 0)),
                    )
                console.print(table)
        except Exception as e:
            console.print(f"[yellow]Architectural memory not available: {e}[/]")

    elif action == "add":
        text = getattr(args, 'text', None)
        if text:
            try:
                from core.memory import MemoryManager
                from pathlib import Path
                mgr = MemoryManager(data_dir=str(Path.home() / ".jarvis"))
                entries = mgr.load_all()
                entry = mgr.add_entry(text, source="cli")
                entries.append(entry)
                mgr.save(entries)
                console.print(f"[green]✅ Memory added: {text[:60]}[/]")
            except Exception as e:
                console.print(f"[red]Failed to add memory: {e}[/]")
        else:
            console.print("[yellow]Usage: jarvis memory add <text>[/]")

    elif action == "search":
        query = getattr(args, 'query', None) or getattr(args, 'text', None)
        if query:
            try:
                from core.memory import MemoryManager
                from pathlib import Path
                mgr = MemoryManager(data_dir=str(Path.home() / ".jarvis"))
                entries = mgr.load_all()
                relevant = mgr.get_relevant_memories(query, entries)
                table = Table(title=f"Search Results for '{query}'", border_style="cyan")
                table.add_column("Score")
                table.add_column("Text")
                table.add_column("Category")
                for score, entry in relevant[:10]:
                    table.add_row(f"{score:.2f}", entry.get("text", "")[:80], entry.get("category", ""))
                console.print(table)
            except Exception as e:
                console.print(f"[red]Search failed: {e}[/]")
        else:
            console.print("[yellow]Usage: jarvis memory search <query>[/]")

    return 0


def cmd_integrations(args):
    """Integration management dashboard."""
    from cli_visuals_new import print_system_msg
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    import asyncio
    console = Console()
    print_system_msg("Integration Management", "info")

    action = getattr(args, 'integration_command', None)

    try:
        from core.integration_manager import get_integration_manager
        mgr = get_integration_manager()
    except Exception as e:
        console.print(f"[red]Integration manager unavailable: {e}[/]")
        return 1

    if action == "list" or not action:
        integrations = mgr.list_integrations()
        table = Table(title=f"Integrations ({len(integrations)})", border_style="magenta")
        table.add_column("Name", style="bold")
        table.add_column("Connected")
        table.add_column("Status")
        for i in integrations:
            name = i["name"]
            connected = i["connected"]
            icon = "✅" if connected else "❌"
            try:
                status = asyncio.run(mgr.health_check(name))
                healthy = "✅" if status.healthy else "❌"
            except Exception as ex:
                logger.warning("Integration health check failed for '%s': %s", name, ex)
                healthy = "?"
            table.add_row(name, icon, healthy)
        console.print(table)

    elif action == "connect":
        name = getattr(args, 'name', None)
        if name:
            result = asyncio.run(mgr.connect(name))
            if result:
                console.print(f"[green]✅ Connected: {name}[/]")
            else:
                console.print(f"[red]❌ Failed to connect: {name}[/]")
        else:
            console.print("[yellow]Usage: jarvis integrations connect <name>[/]")

    elif action == "disconnect":
        name = getattr(args, 'name', None)
        if name:
            result = asyncio.run(mgr.disconnect(name))
            console.print(f"[green]Disconnected: {name}[/]" if result else f"[red]Failed: {name}[/]")

    elif action == "health":
        name = getattr(args, 'name', None)
        if name:
            status = asyncio.run(mgr.health_check(name))
            console.print(Panel(
                f"Name: {status.name}\n"
                f"Connected: {'✅' if status.connected else '❌'}\n"
                f"Healthy: {'✅' if status.healthy else '❌'}\n"
                f"Latency: {status.latency_ms:.0f}ms\n"
                f"Error: {status.error or 'None'}",
                title=f"Health — {name}", border_style="cyan"))
        else:
            results = asyncio.run(mgr.health_check_all())
            table = Table(title="Integration Health", border_style="magenta")
            table.add_column("Name", style="bold")
            table.add_column("Connected")
            table.add_column("Healthy")
            table.add_column("Latency")
            for name, status in results.items():
                table.add_row(name, "✅" if status.connected else "❌",
                              "✅" if status.healthy else "❌",
                              f"{status.latency_ms:.0f}ms" if status.latency_ms else "—")
            console.print(table)

    elif action == "config":
        name = getattr(args, 'name', None)
        key = getattr(args, 'key', None)
        value = getattr(args, 'value', None)
        if name and key and value:
            integ = mgr.get(name)
            if integ:
                integ._config[key] = value
                integ._save_config()
                console.print(f"[green]Set {name}.{key} = {value}[/]")
            else:
                console.print(f"[red]Integration not found: {name}[/]")
        elif name:
            integ = mgr.get(name)
            if integ:
                for k, v in integ._config.items():
                    console.print(f"  {k}: {v}")
            else:
                console.print(f"[red]Integration not found: {name}[/]")

    return 0


def cmd_models_extended(args):
    """Extended model management — includes API key management, per-task assignment, provider priority."""
    sub = getattr(args, 'models_command', None)

    if sub == "list":
        return cmd_models(args)
    if sub == "test":
        return cmd_models(args)
    if sub == "benchmark":
        return cmd_models(args)
    if sub == "switch":
        return cmd_models(args)
    if sub == "start":
        return cmd_models(args)

    from cli_visuals_new import print_system_msg
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    import asyncio
    console = Console()

    if sub == "priority":
        try:
            from core.model_providers.hybrid import get_platform
            platform = get_platform()
            console.print(Panel(
                f"Current mode: [bold]{platform.mode.value.upper()}[/]\n"
                "Priority order: local providers first (ollama), then cloud providers by latency\n"
                "Use [bold]jarvis models switch local|cloud|hybrid[/] to change",
                title="Provider Priority", border_style="blue"))
        except Exception as e:
            console.print(f"[red]Error: {e}[/]")

    elif sub == "assign":
        try:
            from core.model_providers.router import TaskType
            from core.config_registry import config
            task = getattr(args, 'task_type', None)
            model = getattr(args, 'model_name', None)
            if task and model:
                config.set(f"role_models.{task}", model)
                console.print(f"[green]Assigned {model} to {task} tasks[/]")
            else:
                table = Table(title="Per-Task Model Assignment", border_style="cyan")
                table.add_column("Task Type", style="bold")
                table.add_column("Assigned Model")
                table.add_column("Default")
                from core.model_providers.router import DEFAULT_ROLE_MODELS
                for t in TaskType:
                    key = t.value
                    assigned = config.get(f"role_models.{key}", None)
                    default = DEFAULT_ROLE_MODELS.get(key, "auto")
                    table.add_row(key, assigned or "(auto)", default)
                console.print(table)
        except Exception as e:
            console.print(f"[red]Error: {e}[/]")

    elif sub == "apikeys":
        action = getattr(args, 'key_action', 'list')
        provider = getattr(args, 'provider_name', None)
        key_value = getattr(args, 'key_value', None)

        if action == "set" and provider and key_value:
            from core.api_key_vault import vault
            vault.set(f"{provider.upper()}_API_KEY", key_value)
            console.print(f"[green]API key set for {provider}[/]")
        elif action == "delete" and provider:
            from core.api_key_vault import vault
            vault.delete(f"{provider.upper()}_API_KEY")
            console.print(f"[green]API key deleted for {provider}[/]")
        else:
            table = Table(title="API Keys", border_style="yellow")
            table.add_column("Provider", style="bold")
            table.add_column("Status")
            providers_list = ["OPENAI", "ANTHROPIC", "GEMINI", "GROQ", "OPENROUTER"]
            import os
            for p in providers_list:
                env_val = os.getenv(f"{p}_API_KEY", "")
                from core.api_key_vault import vault
                vault_val = vault.get(f"{p}_API_KEY")
                present = bool(env_val or vault_val)
                table.add_row(p, "✅ Set" if present else "❌ Not set")
            console.print(table)
            console.print("\n[yellow]Usage:[/]")
            console.print("  jarvis models apikeys set <provider> <key>")
            console.print("  jarvis models apikeys delete <provider>")

    return 0


def cmd_agents_extended(args):
    """Agent dashboard — status, health, active model, execution history."""
    sub = getattr(args, 'agents_command', None)
    from cli_visuals_new import print_system_msg, render_agent_status
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    console = Console()

    if sub == "list" or not sub:
        try:
            from core.sub_agents.registry import agent_registry
            agents = agent_registry.list_agents()
            table = Table(title=f"Agent Registry ({len(agents)})", border_style="yellow")
            table.add_column("Agent", style="bold")
            table.add_column("Description")
            table.add_column("Modes")
            table.add_column("Status")
            for a in agents:
                table.add_row(
                    a["name"],
                    a.get("description", "")[:50],
                    ", ".join(a.get("modes", [])),
                    a.get("status", "idle"),
                )
            console.print(table)
        except Exception as e:
            console.print(f"[red]Agent registry unavailable: {e}[/]")

    elif sub == "run":
        from cli_commands import cmd_agent_run
        return cmd_agent_run(args)

    elif sub == "health":
        try:
            from core.sub_agents.registry import agent_registry
            agents = agent_registry.list_agents()
            table = Table(title="Agent Health", border_style="green")
            table.add_column("Agent", style="bold")
            table.add_column("Status")
            table.add_column("Available")
            for a in agents:
                status = a.get("status", "unknown")
                available = "✅" if status in ("idle", "done") else "⚠️"
                table.add_row(a["name"], status, available)
            console.print(table)
        except Exception as e:
            console.print(f"[red]Agent health check failed: {e}[/]")

    return 0


def cmd_cleanup_audit(args):
    """Map active modules, orphan candidates, and root clutter."""
    from cli_visuals_new import print_system_msg
    from rich.console import Console
    from rich.table import Table
    from pathlib import Path
    console = Console()
    print_system_msg("Running cleanup audit...", "info")
    root = Path(__file__).resolve().parent
    clutter = [p for p in root.iterdir() if p.suffix in (".py", ".md", ".json", ".yml", ".yaml") and p.is_file()]
    orphans = [p.name for p in clutter if "test" not in p.name and "setup" not in p.name and p.name not in ("jarvis.py", "config.yaml", "requirements.txt", "pyproject.toml", "README.md")]
    table = Table(title="Root Clutter", border_style="yellow")
    table.add_column("File")
    table.add_column("Size")
    for o in sorted(orphans):
        sz = Path(root, o).stat().st_size
        table.add_row(o, f"{sz:,} bytes")
    console.print(table)
    console.print(f"\n[bold]Total root files:[/] {len(orphans)} orphan candidates")
    if getattr(args, 'json', False):
        import json as _json
        console.print(_json.dumps({"orphan_files": sorted(orphans)}, indent=2))
    return 0


def cmd_skill(args):
    """Create, list, or run skills from CLI."""
    from cli_visuals_new import print_system_msg
    from rich.console import Console
    from rich.table import Table
    console = Console()

    action = getattr(args, 'skill_action', None) or getattr(args, 'action', None)
    name = getattr(args, 'name', None)

    if action == "create" and name:
        print_system_msg(f"Creating skill: {name}...", "info")
        from core.skill_loader import SKILLS_DIR
        skill_dir = SKILLS_DIR
        md_path = skill_dir / f"{name}.md"
        py_path = skill_dir / f"{name}.py"
        if md_path.exists():
            console.print(f"[red]Skill '{name}' already exists at {md_path}[/]")
            return 1
        md_content = f"""---
name: {name}
description: "A custom {name} skill"
triggers:
  - "{name}"
---

# {name}

Your skill description here.
"""
        py_content = f'''"""
skills/{name}.py — Handler for {name} skill.
"""
import logging
logger = logging.getLogger(__name__)

async def handle(message: str) -> str:
    return f"{{message}} (handled by {name} skill)"
'''
        skill_dir.mkdir(parents=True, exist_ok=True)
        md_path.write_text(md_content, encoding="utf-8")
        py_path.write_text(py_content, encoding="utf-8")
        test_dir = skill_dir.parent / "tests"
        test_dir.mkdir(parents=True, exist_ok=True)
        test_path = test_dir / f"test_{name}.py"
        test_content = f'''"""Tests for {name} skill."""
import pytest
from skills.{name} import handle

@pytest.mark.asyncio
async def test_{name}_handler():
    result = await handle("test message")
    assert "{name}" in result
'''
        test_path.write_text(test_content, encoding="utf-8")
        from core.skill_loader import _skills
        _skills.clear()
        console.print(f"[green]✅ Skill '{name}' created:[/]")
        console.print(f"  📄 {md_path}")
        console.print(f"  🐍 {py_path}")
        console.print(f"  🧪 {test_path}")
        return 0

    if action == "list" or not action:
        from core.skill_loader import match_skill
        table = Table(title="Installed Skills", border_style="cyan")
        table.add_column("Name", style="bold")
        table.add_column("Description")
        table.add_column("Triggers")
        from core.skill_loader import SKILLS_DIR
        if SKILLS_DIR.exists():
            for md_file in sorted(SKILLS_DIR.glob("*.md")):
                text = md_file.read_text(encoding="utf-8")
                name_val = md_file.stem
                desc = ""
                triggers = ""
                for line in text.split("\n"):
                    if line.startswith("description:"):
                        desc = line.split(":", 1)[1].strip().strip('"')
                    if line.startswith("  - "):
                        triggers += line.strip("- ").strip() + " "
                table.add_row(name_val, desc or "N/A", triggers.strip())
        console.print(table)
        return 0

    console.print(f"[yellow]Usage: jarvis skill create <name>  |  jarvis skill list[/]")
    return 0


def cmd_mcp(args):
    from cli_visuals_new import print_system_msg
    from rich.panel import Panel
    from rich.console import Console
    console = Console()
    print_system_msg("Probing Model Context Protocol (MCP) Servers...", "info")
    console.print(Panel("[dim]No external MCP servers currently linked.[/]\nUse [bold cyan]/mcp connect <url>[/] to bridge a new provider.", title="MCP BRIDGE"))
    return 0


def cmd_tui(args):
    from cli_server import ensure_server_running
    from cli_utils import common_env
    env = common_env()
    base_url = env.get("JARVIS_SERVER", "http://127.0.0.1:8000")
    ensure_server_running(base_url)
    try:
        from jarvis_tui.main import JarvisApp
    except ImportError:
        print("TUI not installed. Run: pip install -e .[tui]")
        return 1
    app = JarvisApp()
    app.run()
    return 0
def _cmd_scheduler(args):
    """Handle scheduler sub-commands from the CLI."""
    import asyncio
    from core.scheduler.store import SchedulerStore
    from core.scheduler.queue import SchedulerQueue
    from core.scheduler.scheduler import Scheduler
    from core.activity.manager import ActivityManager
    from core.activity.resume import ResumeEngine
    from core.activity.storage import ActivityStore

    rest = getattr(args, 'cmd', [])[1:]
    if not rest or rest[0] in ("-h", "--help", "help"):
        print("Usage: jarvis advanced scheduler <subcommand> [args]")
        print()
        print("Subcommands:")
        print("  start              Start the scheduler background loop")
        print("  stop               Stop the scheduler background loop")
        print("  pause              Pause scheduling (keep state)")
        print("  resume             Resume scheduling")
        print("  submit <goal>      Submit a new activity")
        print("  list [status]      List activities (optionally filter by status)")
        print("  status <id>        Get status of an activity")
        print("  cancel <id>        Cancel a pending/blocked activity")
        print("  set-priority <id> <priority>   Change priority (0-5)")
        print("  tick               Force a single scheduler tick")
        return 0

    cmd_name = rest[0]
    cmd_args = rest[1:]

    from core.tools.scheduler_tools import (
        do_scheduler_start, do_scheduler_stop, do_scheduler_pause,
        do_scheduler_resume, do_scheduler_submit, do_scheduler_list,
        do_scheduler_status, do_scheduler_cancel, do_scheduler_set_priority,
        do_scheduler_tick, set_scheduler, get_scheduler,
    )
    from core.scheduler.registry import get_registry

    # Auto-create scheduler if not running
    sched = get_scheduler()
    if sched is None:
        store = ActivityStore()
        mgr = ActivityManager(store=store)
        resume = ResumeEngine(mgr)
        sched = Scheduler(mgr, resume_engine=resume, registry=get_registry())
        set_scheduler(sched)

    async def _run():
        if cmd_name == "start":
            r = await do_scheduler_start()
            print(f"Scheduler: {r['status']} (state={r['state']})")
        elif cmd_name == "stop":
            r = await do_scheduler_stop()
            print(f"Scheduler: {r['status']}")
        elif cmd_name == "pause":
            r = await do_scheduler_pause()
            print(f"Scheduler: {r['status']} (state={r['state']})")
        elif cmd_name == "resume":
            r = await do_scheduler_resume()
            print(f"Scheduler: {r['status']} (state={r['state']})")
        elif cmd_name == "submit":
            goal = " ".join(cmd_args) if cmd_args else "Untitled activity"
            r = await do_scheduler_submit(goal=goal)
            print(f"Submitted: {r['activity_id']} (goal={r['goal']}, priority={r['priority']})")
        elif cmd_name == "list":
            status_filter = cmd_args[0] if cmd_args else None
            r = await do_scheduler_list(status_filter=status_filter)
            print(f"Queue: {r['total']} total ({r['ready']} ready, {r['blocked']} blocked)")
            if r.get("current"):
                print(f"  Current: {r['current']['activity_id']} ({r['current']['goal']}) [{r['current']['status']}]")
            for a in r.get("activities", []):
                print(f"  {a['activity_id']}: {a['goal']} [{a['status']}] priority={a['priority']} score={a['score']}")
        elif cmd_name == "status":
            if not cmd_args:
                print("Usage: scheduler status <activity_id>")
                return
            r = await do_scheduler_status(cmd_args[0])
            if "error" in r:
                print(f"Error: {r['error']}")
            else:
                print(f"Activity: {r['activity_id']}")
                print(f"  Goal: {r.get('goal', '')}")
                print(f"  Status: {r.get('status', '')}")
                print(f"  Priority: {r.get('priority', 0)}")
                print(f"  Score: {r.get('score', 0)}")
                print(f"  Node type: {r.get('node_type', '')}")
                print(f"  Depends on: {r.get('depends_on', [])}")
        elif cmd_name == "cancel":
            if not cmd_args:
                print("Usage: scheduler cancel <activity_id>")
                return
            r = await do_scheduler_cancel(cmd_args[0])
            if r["cancelled"]:
                print(f"Cancelled: {r['activity_id']}")
            else:
                print(f"Not found or not cancellable: {r['activity_id']}")
        elif cmd_name == "set-priority":
            if len(cmd_args) < 2:
                print("Usage: scheduler set-priority <activity_id> <priority>")
                return
            try:
                pri = int(cmd_args[1])
            except ValueError:
                print("Priority must be an integer (0-5)")
                return
            r = await do_scheduler_set_priority(cmd_args[0], pri)
            if r["updated"]:
                print(f"Updated: {r['activity_id']} → priority={r['priority']}")
            else:
                print(f"Activity not found: {r['activity_id']}")
        elif cmd_name == "tick":
            r = await do_scheduler_tick()
            print(f"Tick {r.get('tick', '?')}: ", end="")
            if r.get("executed"):
                print(f"executed {r['activity_id']} ({r.get('executor', '?')}) in {r.get('duration_ms', '?')}ms")
            elif r.get("error"):
                print(f"error: {r['error']}")
            else:
                print(f"no action ({r.get('reason', 'unknown')})")
        elif cmd_name == "chain_submit":
            if len(args.steps) < 2:
                print("Usage: jarvis advanced scheduler chain_submit <chain_name> <goal1:type1> <goal2:type2> ...")
                print("Example: jarvis advanced scheduler chain_submit \"Android Project\" research build email")
                return 1
            steps_list = []
            for s in args.steps[1:]:  # skip chain_name
                parts = s.split(":")
                goal = parts[0]
                ntype = parts[1] if len(parts) > 1 else "goal"
                steps_list.append([goal, ntype])
            r = await do_scheduler_chain_submit(name=args.steps[0], steps=steps_list)
            if "chain_id" in r:
                print(f"Chain created: {r['chain_id']}")
                print(f"  Name: {r['name']}")
                print(f"  Status: {r['status']}")
                print(f"  Activities: {len(r['activities'])}")
                for a in r['activities']:
                    print(f"    {a['activity_id']}: {a['goal'][:50]} (order={a['metadata'].get('chain_order', '?')})")
            else:
                print(f"Error: {r}")
        elif cmd_name == "chain_list":
            r = await do_scheduler_chain_list()
            chains = r.get("chains", [])
            if not chains:
                print("No chains found.")
            else:
                print(f"Chains ({len(chains)}):")
                for c in chains:
                    print(f"  {c['chain_id']}: {c['name']} [{c['status']}] {c['progress']}")
        elif cmd_name == "chain_status":
            if len(args.steps) < 1:
                print("Usage: jarvis advanced scheduler chain_status <chain_id>")
                return 1
            r = await do_scheduler_chain_status(args.steps[0])
            if "error" in r:
                print(f"Error: {r['error']}")
            else:
                print(f"Chain: {r['name']}")
                print(f"  Status: {r['status']}")
                print(f"  Progress: {r['progress']}")
                print(f"  Current step: {r['current_step']}")
                for a in r['activities']:
                    deps = ", ".join(a['depends_on']) if a['depends_on'] else "none"
                    print(f"  {a['activity_id']}: [{a['status']}] {a['goal'][:50]} (deps: {deps})")
        elif cmd_name == "chain_cancel":
            if len(args.steps) < 1:
                print("Usage: jarvis advanced scheduler chain_cancel <chain_id>")
                return 1
            r = await do_scheduler_chain_cancel(args.steps[0])
            print(f"Cancelled: {r['cancelled']}" if r.get('cancelled') else f"Chain not found: {args.steps[0]}")
        else:
            print(f"Unknown scheduler subcommand: {cmd_name}")
            print("Run 'jarvis advanced scheduler' for help.")

    asyncio.run(_run())
    return 0


def _cmd_activity(args, _store=None):
    """Handle activity sub-commands from the CLI."""
    import asyncio
    from core.activity.manager import ActivityManager
    from core.activity.storage import ActivityStore

    rest = getattr(args, 'args', [])
    cmd_name = getattr(args, 'action', 'list')

    if cmd_name in ("-h", "--help", "help"):
        print("Usage: jarvis activity <subcommand> [args]")
        print()
        print("Subcommands:")
        print("  list                   List active activities")
        print("  tree <id>              Show activity tree")
        print("  get <id>               Show activity details")
        print("  summary [id]           Show activity summary")
        print("  watch                  Live activity feed (Ctrl+C to stop)")
        return 0

    store = _store or ActivityStore()
    mgr = ActivityManager(store=store)

    if cmd_name == "list":
        activities = mgr.get_active_activities()
        if not activities:
            print("No active activities.")
            return 0
        from rich.table import Table
        from rich.console import Console
        table = Table(title="Active Activities")
        table.add_column("ID", style="cyan")
        table.add_column("Goal", style="white")
        table.add_column("Status", style="yellow")
        table.add_column("Depth", style="dim")
        table.add_column("Created", style="dim")
        for a in activities:
            status_style = {
                "PENDING": "yellow", "RUNNING": "green",
                "SUSPENDED": "blue", "FAILED": "red", "CANCELLED": "dim",
            }.get(a.status.value, "white")
            table.add_row(
                a.node_id[:16],
                a.label[:60],
                f"[{status_style}]{a.status.value}[/]",
                str(a.depth),
                a.created_at.strftime("%H:%M:%S") if a.created_at else "",
            )
        Console().print(table)
        return 0

    elif cmd_name == "tree":
        if not rest:
            print("Usage: jarvis activity tree <activity_id>")
            return 1
        aid = rest[0]
        nodes = mgr.get_tree(aid)
        if not nodes:
            print(f"Activity not found: {aid}")
            return 1
        edges = store.get_outgoing_edges(aid)
        children: dict[str, list] = {}
        for n in nodes:
            p = n.parent_id or ""
            children.setdefault(p, []).append(n)

        def _print_tree(parent_id: str, indent: int = 0):
            for n in children.get(parent_id, []):
                status_icon = {"PENDING": "○", "RUNNING": "▶", "COMPLETED": "✓", "FAILED": "✗", "SUSPENDED": "⏸", "CANCELLED": "⊘"}.get(n.status.value, "?")
                agent_tag = f" [{n.agent_id}]" if n.agent_id else ""
                print(f"{'  ' * indent}{status_icon} {n.node_type}:{n.label[:50]}{agent_tag} [{n.status.value}]")
                _print_tree(n.node_id, indent + 1)

        print(f"\nActivity Tree: {aid}")
        print("=" * 60)
        _print_tree("")
        print()
        if edges:
            print(f"Edges ({len(edges)}):")
            for e in edges:
                print(f"  {e.from_node_id[:12]} → {e.to_node_id[:12]} [{e.edge_type}]")
        return 0

    elif cmd_name == "get":
        if not rest:
            print("Usage: jarvis activity get <activity_id>")
            return 1
        aid = rest[0]
        node = mgr.get_activity(aid)
        if not node:
            print(f"Activity not found: {aid}")
            return 1
        print(f"ID:         {node.node_id}")
        print(f"Type:       {node.node_type}")
        print(f"Label:      {node.label}")
        print(f"Status:     {node.status.value}")
        print(f"Depth:      {node.depth}")
        if node.agent_id:
            print(f"Agent:      {node.agent_id}")
        if node.workflow_id:
            print(f"Workflow:   {node.workflow_id}")
        if node.parent_id:
            print(f"Parent:     {node.parent_id}")
        if node.started_at:
            print(f"Started:    {node.started_at}")
        if node.completed_at:
            print(f"Completed:  {node.completed_at}")
        if node.artifacts:
            print(f"Artifacts:  {', '.join(f'{k}={v}' for k, v in node.artifacts.items())}")
        edges = store.get_edges(aid)
        if edges:
            print("\nEdges:")
            for e in edges:
                direction = "→" if e.from_node_id == aid else "←"
                other = e.to_node_id if e.from_node_id == aid else e.from_node_id
                print(f"  {direction} {other[:16]} [{e.edge_type}]")
        return 0

    elif cmd_name == "summary":
        from rich.table import Table
        from rich.console import Console
        if rest:
            aids = [rest[0]]
        else:
            acts = mgr.get_active_activities()
            aids = [a.node_id for a in acts]
        if not aids:
            print("No activities to summarize.")
            return 0
        for aid in aids:
            summary = mgr.summarize(aid)
            if "error" in summary:
                print(f"Activity {aid}: {summary['error']}")
                continue
            print(f"\nActivity: {summary['goal']} ({summary['activity_id'][:16]})")
            print(f"  Status: {summary['status']} | Nodes: {summary['total_nodes']} | Depth: {summary['depth']}")
            print(f"  Agents: {', '.join(summary['agents_used']) if summary['agents_used'] else 'none'}")
            print(f"  Created: {summary.get('created_at', 'unknown')}")
            by_status = summary.get('by_status', {})
            if by_status:
                print(f"  Status breakdown:")
                table = Table(show_header=False, box=None)
                table.add_column("Status")
                table.add_column("Count")
                for s, c in sorted(by_status.items()):
                    table.add_row(f"  {s}", str(c))
                Console().print(table)
        return 0

    elif cmd_name == "watch":
        print("Watching activity feed... (Ctrl+C to stop)")
        import time
        last_ids = set()
        try:
            while True:
                activities = mgr.get_active_activities()
                current_ids = {a.node_id for a in activities}
                new_ids = current_ids - last_ids
                for a in activities:
                    if a.node_id in new_ids:
                        print(f"[NEW] {a.node_id[:12]} {a.label[:50]} [{a.status.value}]")
                counts = {}
                for a in activities:
                    c = store.count_by_status(a.node_id)
                    counts[a.node_id] = c
                last_ids = current_ids
                time.sleep(3)
        except KeyboardInterrupt:
            print("\nStopped.")
        return 0

    else:
        print(f"Unknown activity subcommand: {cmd_name}")
        print("Run 'jarvis activity' for help.")
        return 1


cmd_activity = _cmd_activity




# ── Primary Commands (Phase 7 CLI) ─────────────────────────────────────────

def _write_report(result: dict, ws: dict, args) -> str:
    """Write markdown report to output file."""
    path_short = ws.get('root', '').rstrip('/\\').split('/')[-1].split('\\')[-1]
    lines = []
    lines.append(f"# {path_short} — Project Analysis Report")
    lines.append("")
    lines.append(f"Generated by JARVIS — language: {ws['language']}, build: {ws['build_system']}, branch: {ws['branch']}")
    lines.append("")
    lines.append("## Workspace Overview")
    lines.append(f"- **Root:** {ws['root']}")
    lines.append(f"- **Git Root:** {ws['git_root'] or '(not a git repo)'}")
    lines.append(f"- **Branch:** {ws['branch'] or 'N/A'}")
    lines.append(f"- **Language:** {ws['language']}")
    lines.append(f"- **Framework:** {ws['framework'] or 'none'}")
    lines.append(f"- **Build System:** {ws['build_system']}")
    lines.append(f"- **Package Manager:** {ws['package_manager']}")
    lines.append(f"- **Files:** {ws['files']}")
    lines.append(f"- **Entry Points:** {', '.join(ws['entry_points'][:5]) or 'none'}")
    lines.append(f"- **Test Suites:** {ws['test_suites']}")
    lines.append(f"- **Build Command:** {ws['build_command']}")
    lines.append(f"- **Test Command:** {ws['test_command']}")
    lines.append(f"- **Run Command:** {ws['run_command']}")
    lines.append("")

    for aspect_name in ['entry_points', 'api_routes', 'tests', 'auth', 'database', 'dead_code', 'pipeline']:
        data = result.get(aspect_name)
        if data is None:
            continue
        lines.append(f"## {aspect_name.upper()}")
        lines.append("")
        if isinstance(data, list):
            if len(data) == 0:
                lines.append("(none detected)")
            else:
                count_text = f" ({len(data)} items)"
                lines.append(f"**Count:** {len(data)}{count_text}")
                lines.append("")
                for item in data[:20]:
                    if isinstance(item, dict):
                        name = item.get("file", item.get("name", str(item)))
                        extra = item.get("type", item.get("matches", ""))
                        if extra:
                            lines.append(f"- {name} ({extra})")
                        else:
                            lines.append(f"- {name}")
                    else:
                        lines.append(f"- {item}")
                if len(data) > 20:
                    lines.append(f"- ... and {len(data) - 20} more")
        elif isinstance(data, dict):
            for k, v in data.items():
                if isinstance(v, list):
                    lines.append(f"- **{k}:** {', '.join(str(x) for x in v[:3])}{' ...' if len(v) > 3 else ''}")
                elif isinstance(v, bool):
                    lines.append(f"- **{k}:** {'yes' if v else 'no'}")
                else:
                    lines.append(f"- **{k}:** {v}")
        lines.append("")

    lines.append("---")
    lines.append("_Generated by JARVIS_")
    return '\n'.join(lines)


def cmd_understand(args):
    """Analyze repository structure, entry points, dependencies, API routes, tests."""
    import asyncio
    from core.agent_orchestrator import AgentOrchestrator

    orch = AgentOrchestrator(project_dir=getattr(args, 'path', os.getcwd()))
    aspect = getattr(args, 'aspect', 'all')
    result = asyncio.run(orch.analyze_repository(aspect))

    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    console = Console()

    if aspect == "all":
        ws = asyncio.run(orch.workspace_status())
        console.print(Panel(
            f"[bold]{Path(ws['root']).name}[/] — {ws['language']} / {ws['framework'] or 'no framework'}\n"
            f"Build: {ws['build_system']}  |  {ws['files']} files  |  "
            f"{ws['test_suites']} test suites  |  branch: {ws['branch']}",
            title="Workspace Overview", border_style="cyan",
        ))

        for aspect_name, data in result.items():
            if isinstance(data, dict) and data.get("error"):
                continue
            if isinstance(data, list):
                console.print(f"\n[bold]{aspect_name.upper()}[/] ({len(data)} items)")
                for item in data[:10]:
                    if isinstance(item, dict):
                        name = item.get("file", item.get("name", str(item)))
                        console.print(f"  • {name}")
            elif isinstance(data, dict):
                console.print(f"\n[bold]{aspect_name.upper()}[/]")
                for k, v in list(data.items())[:10]:
                    console.print(f"  {k}: {v}")

        console.print(f"\n[dim]Run 'jarvis understand --aspect <name>' for details on a specific aspect[/]")

        output = getattr(args, 'output', None)
        if output:
            report = _write_report(result, ws, args)
            with open(output, 'w', encoding='utf-8') as f:
                f.write(report)
            console.print(f"\n[green]Report written to {output}[/]")
    else:
        data = result.get(aspect, {})
        if isinstance(data, list):
            for item in data[:20]:
                console.print(item)
        else:
            console.print(data)

    return 0


def cmd_workspace(args):
    """Show current workspace status."""
    import asyncio
    import os
    from core.agent_orchestrator import AgentOrchestrator
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel

    console = Console()
    path = getattr(args, 'path', os.getcwd())
    orch = AgentOrchestrator(project_dir=str(path))
    ws = asyncio.run(orch.workspace_status())

    console.print(Panel(
        f"[bold]Root:[/] {ws['root']}\n"
        f"[bold]Git Root:[/] {ws['git_root'] or '(not a git repo)'}\n"
        f"[bold]Branch:[/] {ws['branch'] or 'N/A'}",
        title="Workspace", border_style="cyan",
    ))

    table = Table(border_style="blue")
    table.add_column("Property", style="bold")
    table.add_column("Value")
    table.add_row("Language", ws['language'])
    table.add_row("Framework", ws['framework'] or 'none')
    table.add_row("Build System", ws['build_system'])
    table.add_row("Package Manager", ws['package_manager'])
    table.add_row("Files", str(ws['files']))
    table.add_row("Entry Points", ", ".join(ws['entry_points'][:5]) or "none")
    table.add_row("Test Suites", str(ws['test_suites']))
    table.add_row("Build Command", ws['build_command'] or 'none')
    table.add_row("Test Command", ws['test_command'] or 'none')
    table.add_row("Run Command", ws['run_command'] or 'none')
    console.print(table)
    return 0


def cmd_code(args):
    """Autonomous coding: understand → plan → generate → build → test → repair → verify."""
    import asyncio
    from core.agent_orchestrator import AgentOrchestrator
    from rich.console import Console
    from rich.panel import Panel

    console = Console()
    task = getattr(args, 'task', '')
    path = getattr(args, 'path', os.getcwd())

    console.print(Panel(
        f"[bold]Task:[/] {task}\n[bold]Path:[/] {path}",
        title="Autonomous Coding", border_style="green",
    ))

    orch = AgentOrchestrator(project_dir=str(path))
    result = asyncio.run(orch.code(task, str(path)))

    if result.get("status") == "completed":
        console.print(f"[green]✅ Task completed[/]")
        console.print(f"Completion: {result.get('completion', 0) * 100:.0f}%")
    else:
        console.print(f"[red]❌ Task failed: {result.get('status', 'unknown')}[/]")

    build_history = result.get("build_history", {})
    if build_history:
        for gid, entries in build_history.items():
            console.print(f"\n[bold]Build Attempts ({len(entries)}):[/]")
            for i, entry in enumerate(entries):
                console.print(f"  {i+1}. {entry[:120]}...")

    return 0 if result.get("status") == "completed" else 1


def cmd_build(args):
    """Build project with auto-repair on failure."""
    import asyncio
    from core.agent_orchestrator import AgentOrchestrator
    from rich.console import Console
    from rich.panel import Panel

    console = Console()
    path = getattr(args, 'path', os.getcwd())
    command = getattr(args, 'command', None)

    orch = AgentOrchestrator(project_dir=str(path))
    result = asyncio.run(orch.build(str(path), command))

    if result.get("success"):
        console.print(Panel(
            f"[green]✅ Build succeeded[/]\n"
            f"Output:\n{result.get('output', '')[:2000]}",
            title="Build Result", border_style="green",
        ))
    else:
        console.print(Panel(
            f"[red]❌ Build failed[/]\n"
            f"Error:\n{result.get('output', result.get('error', 'No output'))[:2000]}",
            title="Build Result", border_style="red",
        ))
        if result.get("repaired"):
            console.print("[yellow]⚠️  Build failed even after repair attempts[/]")

    return 0 if result.get("success") else 1


def cmd_run(args):
    """Run the project using detected run command."""
    import asyncio
    from core.agent_orchestrator import AgentOrchestrator
    from rich.console import Console
    from rich.panel import Panel

    console = Console()
    path = getattr(args, 'path', os.getcwd())

    orch = AgentOrchestrator(project_dir=str(path))
    result = asyncio.run(orch.run(str(path)))

    if result.get("success"):
        console.print(Panel(
            f"[green]✅ Ran successfully[/]\n"
            f"Command: {result.get('command', '')}\n"
            f"Output:\n{result.get('output', '')[:2000]}",
            title="Run Result", border_style="green",
        ))
    else:
        console.print(Panel(
            f"[red]❌ Run failed[/]\n"
            f"Error: {result.get('error', result.get('output', 'No output'))[:2000]}",
            title="Run Result", border_style="red",
        ))

    return 0 if result.get("success") else 1


_ADVANCED_COMMANDS = {
    "server": "Start the FastAPI backend server",
    "restart": "Restart the local backend stack",
    "gui": "Start the Flutter Windows GUI",
    "web": "Build & serve the JARVIS web UI",
    "up": "Start JARVIS desktop stack (server + GUI)",
    "agent": "Run JARVIS sub-agents (list/run)",
    "agents": "Agent dashboard — list, run, health",
    "tui": "Launch the Textual TUI",
    "plugin": "Manage plugins",
    "skill": "Create and list skills",
    "voice": "Voice dashboard — STT, TTS, wake word",
    "automation": "Automation dashboard — goals, phases, repair",
    "memory": "Memory dashboard — memories, vectors, patterns",
    "integrations": "Manage integrations (Gmail, Telegram, etc.)",
    "features": "Feature Registry — list, explore, toggle",
    "diagnostics": "Diagnostics dashboard",
    "home": "Home dashboard — system overview",
    "project": "Manage projects",
    "cloud": "Cloud/Supabase commands",
    "extension": "Show IDE/extension integration commands",
    "index": "Index workspace files for codebase search",
    "setup": "Run setup wizard for first-time configuration",
    "debug": "Inspect runtime state",
    "cleanup-audit": "Map active modules and orphan candidates",
    "status": "Show current JARVIS autonomous status",
    "scheduler": "Autonomous scheduler: start, stop, pause, resume, submit, list, status, cancel, set-priority, tick",
}


def cmd_advanced(args):
    """Run advanced commands (server, agents, voice, etc.) or list them."""
    # Import from the module itself (available at runtime after module loads)
    import sys
    _mod = sys.modules[__name__]
    cmd_server = getattr(_mod, 'cmd_server', lambda a: 0)
    cmd_restart = getattr(_mod, 'cmd_restart', lambda a: 0)
    cmd_gui = getattr(_mod, 'cmd_gui', lambda a: 0)
    cmd_web = getattr(_mod, 'cmd_web', lambda a: 0)
    cmd_up = getattr(_mod, 'cmd_up', lambda a: 0)
    cmd_agent_list = getattr(_mod, 'cmd_agent_list', lambda a: 0)
    cmd_agent_run = getattr(_mod, 'cmd_agent_run', lambda a: 0)
    cmd_agents_extended = getattr(_mod, 'cmd_agents_extended', lambda a: 0)
    cmd_tui = getattr(_mod, 'cmd_tui', lambda a: 0)
    cmd_plugin = getattr(_mod, 'cmd_plugin', lambda a: 0)
    cmd_skill = getattr(_mod, 'cmd_skill', lambda a: 0)
    cmd_voice = getattr(_mod, 'cmd_voice', lambda a: 0)
    cmd_automation = getattr(_mod, 'cmd_automation', lambda a: 0)
    cmd_memory = getattr(_mod, 'cmd_memory', lambda a: 0)
    cmd_integrations = getattr(_mod, 'cmd_integrations', lambda a: 0)
    cmd_features = getattr(_mod, 'cmd_features', lambda a: 0)
    cmd_diagnostics = getattr(_mod, 'cmd_diagnostics', lambda a: 0)
    cmd_home = getattr(_mod, 'cmd_home', lambda a: 0)
    cmd_project = getattr(_mod, 'cmd_project', lambda a: 0)
    cmd_cloud = getattr(_mod, 'cmd_cloud', lambda a: 0)
    cmd_extension = getattr(_mod, 'cmd_extension', lambda a: 0)
    cmd_index = getattr(_mod, 'cmd_index', lambda a: 0)
    cmd_setup = getattr(_mod, 'cmd_setup', lambda a: 0)
    cmd_debug = getattr(_mod, 'cmd_debug', lambda a: 0)
    cmd_cleanup_audit = getattr(_mod, 'cmd_cleanup_audit', lambda a: 0)
    cmd_status = getattr(_mod, 'cmd_status', lambda a: 0)
    from rich.console import Console
    from rich.table import Table

    cmds = getattr(args, 'args', []) or getattr(args, 'cmd', [])
    if not cmds:
        console = Console()
        console.print("[bold]Advanced Commands:[/]\n")
        table = Table(border_style="yellow")
        table.add_column("Command", style="bold")
        table.add_column("Description")
        for name, desc in sorted(_ADVANCED_COMMANDS.items()):
            table.add_row(name, desc)
        console.print(table)
        console.print("\n[dim]Usage: jarvis advanced <command> [args...][/]")
        return 0

    cmd_name = cmds[0]
    rest = cmds[1:]

    handler_map = {
        "server": cmd_server, "restart": cmd_restart,
        "gui": cmd_gui, "web": cmd_web, "up": cmd_up,
        "agent": _cmd_advanced_agent,
        "agents": cmd_agents_extended,
        "tui": cmd_tui,
        "plugin": cmd_plugin, "skill": cmd_skill,
        "voice": cmd_voice, "automation": cmd_automation,
        "memory": cmd_memory, "integrations": cmd_integrations,
        "features": cmd_features, "diagnostics": cmd_diagnostics,
        "home": cmd_home, "project": cmd_project,
        "cloud": cmd_cloud, "extension": cmd_extension,
        "index": cmd_index, "setup": cmd_setup,
        "debug": cmd_debug, "cleanup-audit": cmd_cleanup_audit,
        "status": cmd_status,
        "scheduler": _cmd_scheduler,
    }

    if cmd_name in ("agent", "agents") and rest:
        if rest[0] == "list":
            return cmd_agent_list(args)
        elif rest[0] == "run" and len(rest) > 2:
            import argparse
            a = argparse.Namespace(name=rest[1], task=" ".join(rest[2:]), mode=None, lang="auto")
            return cmd_agent_run(a)

    handler = handler_map.get(cmd_name)
    if handler:
        _DEFAULTS = [
            ("host", "127.0.0.1"), ("port", 8000),
            ("multi_model", False), ("dry_run", False),
            ("no_reload", False), ("api_url", None),
            ("ws_url", None), ("device", "windows"),
            ("google_api_key", None), ("droq_api_key", None),
            ("background", False), ("with_models", False),
            ("forward", []), ("id", None), ("name", None),
            ("goal", ""), ("task", ""), ("mode", None), ("lang", "auto"),
        ]
        for attr, default in _DEFAULTS:
            if not hasattr(args, attr):
                setattr(args, attr, default)
        return handler(args)

    print(f"Unknown advanced command: {cmd_name}")
    print("Run 'jarvis advanced' for the list of available commands.")
    return 1


def _cmd_advanced_agent(args):
    """Handle agent sub-commands."""
    rest = getattr(args, 'cmd', [])[1:]
    if not rest or rest[0] == "list":
        return cmd_agent_list(argparse.Namespace())
    if rest[0] == "run" and len(rest) > 2:
        import argparse
        a = argparse.Namespace(name=rest[1], task=" ".join(rest[2:]), mode=None, lang="auto")
        return cmd_agent_run(a)
    print("Usage: jarvis advanced agent list|run <name> <task>")
    return 1


def cmd_version(args: argparse.Namespace) -> int:
    """Show JARVIS version information."""
    from core.version import version_string
    print(version_string())
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    """Run quick system demo (smoke test)."""
    from demo.quick_demo import main as demo_main
    return demo_main()


def cmd_benchmark(args: argparse.Namespace) -> int:
    """Run performance baselines for RC3.4."""
    from core.benchmark.perf_baseline import main as benchmark_main
    return benchmark_main()
