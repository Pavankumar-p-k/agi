#!/usr/bin/env python3
"""Unified JARVIS launcher for CLI, server, GUI, models, and IDE integrations."""

from __future__ import annotations

import sys
import os
import time
import json
import socket
import shutil
import asyncio
import subprocess
import argparse
import logging
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

# --- CLI Enhancement Imports ---
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.completion import Completer, Completion, WordCompleter, PathCompleter
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.styles import Style
from pygments.lexers import PythonLexer, guess_lexer_for_filename
from pygments import highlight
from pygments.formatters import TerminalFormatter


ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
BACKEND = ROOT
APPS = ROOT / "apps" / "jarvis_app"
AUTONOMY_CLI = ROOT / "autonomy" / "cli" / "jarvis_cli.py"
STUDENT_MAIN = ROOT / "learning" / "student_agi" / "student_agi_main.py"

MODEL_PORTS = [
    ("tinyllama", 11434),
    ("deepseek-r1:1.5b", 11435),
    ("qwen2.5-coder:3b", 11436),
    ("qwen3:4b", 11437),
    ("qwen2.5:7b", 11438),
    ("mistral:7b", 11439),
    ("llama3.1:8b", 11440),
    ("phi3:mini", 11441),
    ("moondream", 11442),
]

_legacy_route_notice_shown = False
_local_runtime_notice_shown = False
_local_os_runtime = None


# --- Config ---
JARVIS_DIR = Path.home() / ".jarvis"
CONFIG_PATH = JARVIS_DIR / "config.json"
HISTORY_PATH = JARVIS_DIR / "history"

@dataclass
class JarvisConfig:
    default_model: str = "gemma4:e4b"
    debug: bool = False
    debug_search: bool = False
    show_timestamps: bool = False
    mode: str = "chat"
    theme: str = "dark"
    aliases: dict = None

    def save(self):
        JARVIS_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(json.dumps(asdict(self), indent=2, default=str))

    @classmethod
    def load(cls):
        if CONFIG_PATH.exists():
            try:
                data = json.loads(CONFIG_PATH.read_text())
                valid_keys = cls.__dataclass_fields__
                filtered = {k: v for k, v in data.items() if k in valid_keys}
                return cls(**filtered)
            except Exception:
                pass
        return cls()


# --- Completer ---
class JarvisCompleter(Completer):
    COMMANDS = [
        "/session", "/sessions", "/session-new", "/session-switch",
        "/session-rename", "/session-export", "/session-fork", "/session-compact",
        "/model", "/undo", "/clear", "/agent", "/mode",
        "/history", "/timestamps", "/debug", "/debug-search", "/theme",
        "/stash", "/stash-list", "/stash-load",
        "/read", "/write", "/edit", "/ls", "/dir", "/tree", "/run", "/diff",
        "/status", "/help", "/h", "/exit", "/quit",
        "/generate-ui", "/gui", "/opencode",
        "/plan", "/goal", "/develop", "/vision", "/feedback", "/tools",
    ]

    def __init__(self, state_getter):
        self._state_getter = state_getter

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        if not text:
            return

        first_space = text.find(" ")
        if first_space == -1:
            yield from self._complete_command(text)
            return

        cmd = text[:first_space].lower()
        arg = text[first_space + 1:]
        yield from self._complete_arg(cmd, arg)

    def _complete_command(self, prefix):
        for cmd in self.COMMANDS:
            if cmd.startswith(prefix):
                yield Completion(cmd, start_position=-len(prefix))

    def _complete_arg(self, cmd, prefix):
        if cmd in ("/read", "/write", "/edit", "/ls", "/dir", "/tree"):
            from pathlib import Path
            dir_part = os.path.dirname(prefix) or "."
            file_part = os.path.basename(prefix)
            try:
                dir_path = Path(dir_part)
                if dir_path.exists():
                    for entry in sorted(dir_path.iterdir()):
                        name = entry.name
                        if name.startswith(file_part):
                            display = name + ("/" if entry.is_dir() else "")
                            yield Completion(display, start_position=-len(file_part))
            except (PermissionError, OSError):
                pass

        elif cmd in ("/session-switch",):
            from core.session import list_sessions
            try:
                sessions = list_sessions()
                for s in sessions:
                    sid = s.get("session_id", "")
                    if sid.startswith(prefix):
                        yield Completion(sid, start_position=-len(prefix))
            except Exception:
                pass

        elif cmd in ("/model",):
            yield from self._complete_model(prefix)

        elif cmd == "/stash-load":
            full_path = Path.home() / ".jarvis" / "stash"
            if full_path.exists():
                for f in sorted(full_path.glob("*.json")):
                    try:
                        idx = int(f.stem)
                        label = json.loads(f.read_text()).get("label", "") or str(idx)
                        display = f"{idx}"
                        meta_text = f"#{idx} {label}"
                        if str(idx).startswith(prefix):
                            yield Completion(display, start_position=-len(prefix), display_meta=meta_text)
                    except (ValueError, json.JSONDecodeError):
                        pass

    def _complete_model(self, prefix):
        models = ["gemma4:e4b", "qwen3:4b", "llama3.1:8b", "qwen2.5:7b",
                  "qwen2.5-coder:3b", "mistral:7b", "deepseek-r1:1.5b",
                  "tinyllama", "phi3:mini"]
        for m in models:
            if m.startswith(prefix):
                yield Completion(m, start_position=-len(prefix))


# --- Color helpers ---
def style_theme(dark=True):
    return Style.from_dict({
        "prompt": "fg:#00ff00 bold" if dark else "fg:#005500 bold",
        "jarvis": "fg:#00afff bold" if dark else "fg:#0055ff bold",
        "user": "fg:#ffffff" if dark else "fg:#000000",
        "info": "fg:#888888 italic",
        "error": "fg:#ff0000 bold",
        "success": "fg:#00ff00" if dark else "fg:#005500",
        "warning": "fg:#ffaa00",
        "timestamp": "fg:#666666",
        "header": "fg:#00afff bold",
    })


def syntax_highlight(text, filename=None):
    try:
        lexer = guess_lexer_for_filename(filename or "_.py", text) if filename else PythonLexer()
        return highlight(text, lexer, TerminalFormatter())
    except Exception:
        return text


def colorize(text, color):
    colors = {
        "green": "\033[92m", "cyan": "\033[96m", "red": "\033[91m",
        "yellow": "\033[93m", "blue": "\033[94m", "magenta": "\033[95m",
        "bold": "\033[1m", "dim": "\033[2m", "reset": "\033[0m",
    }
    c = colors.get(color, colors["reset"])
    return f"{c}{text}{colors['reset']}"


@dataclass
class CliState:
    session: 'ConversationManager' = None
    config: 'JarvisConfig' = None
    mode: str = "chat"
    debug: bool = False
    debug_search: bool = False
    show_timestamps: bool = False
    current_model: str = "gemma4:e4b"
    base_url: str = "http://127.0.0.1:8000"
    _pending_text: str = ""

IDE_PRESETS = {
    "codex": "CLI-first workflow similar to Codex. Use JARVIS through terminal and HTTP APIs.",
    "vscode": "VS Code and forks can call JARVIS through local tasks, terminal profiles, and HTTP tools.",
    "cursor": "Cursor can reuse the same local CLI and HTTP endpoints as VS Code.",
    "windsurf": "Windsurf can connect through terminal tasks and local JARVIS APIs.",
    "zed": "Zed can use shell commands and OpenAPI/HTTP integrations against the JARVIS server.",
    "jetbrains": "JetBrains IDEs can use external tools and HTTP clients against the JARVIS server.",
}


def python_exe() -> str:
    candidates = [
        ROOT / ".venv" / "Scripts" / "python.exe",
        ROOT / ".venv311" / "Scripts" / "python.exe",
        ROOT / "venv" / "Scripts" / "python.exe",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return sys.executable


def common_env() -> dict:
    env = os.environ.copy()
    env.setdefault("PYTHONPATH", str(ROOT))
    env.setdefault("JARVIS_SERVER", "http://127.0.0.1:8000")
    env.setdefault("OLLAMA_URL", "http://127.0.0.1:11434")
    env.setdefault("JARVIS_AUTO_MODELS", "single")
    return env


def run_command(cmd: list[str], cwd: Path | None = None, env: dict | None = None, dry_run: bool = False) -> int:
    cmd = prepare_command(cmd)
    if dry_run:
        print("DRY RUN:", " ".join(cmd))
        if cwd:
            print("CWD:", cwd)
        return 0
    return subprocess.run(cmd, cwd=str(cwd) if cwd else None, env=env).returncode


def spawn_background(
    title: str,
    cmd: list[str],
    cwd: Path | None = None,
    env: dict | None = None,
    dry_run: bool = False,
) -> int:
    cmd = prepare_command(cmd)
    if dry_run:
        print(f"DRY RUN [{title}]:", " ".join(cmd))
        if cwd:
            print("CWD:", cwd)
        return 0
    popen_kwargs = {
        "cwd": str(cwd) if cwd else None,
        "env": env,
    }
    if os.name == "nt":
        popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
    subprocess.Popen(cmd, **popen_kwargs)
    return 0


def prepare_command(cmd: list[str]) -> list[str]:
    if not cmd:
        raise ValueError("Command cannot be empty")
    if os.name != "nt":
        return cmd

    executable = shutil.which(cmd[0]) or cmd[0]
    if Path(executable).suffix.lower() in {".bat", ".cmd"}:
        return ["cmd.exe", "/c", executable, *cmd[1:]]
    return [executable, *cmd[1:]]


def run_autonomy_cli(cli_args: list[str]) -> int:
    env = common_env()
    ensure_server_running(env.get("JARVIS_SERVER", "http://127.0.0.1:8000"))
    cmd = [python_exe(), str(AUTONOMY_CLI), *cli_args]
    return run_command(cmd, cwd=ROOT, env=env)


def cmd_cli(args: argparse.Namespace) -> int:
    from core.session import ConversationManager, get_last_session_id, list_sessions

    env = common_env()
    base_url = env.get("JARVIS_SERVER", "http://127.0.0.1:8000")
    ensure_local_stack_running(env)
    cli_debug = getattr(args, "debug", False)

    # Load config
    cfg = JarvisConfig.load()
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

    # Setup prompt_toolkit session
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

    print()
    dbg_label = colorize(' DEBUG', 'yellow') if state.debug else ''
    banner = (
        f"{colorize('+----------------------------------------------------+', 'cyan')}\n"
        f"{colorize('|  JARVIS AI OS - Interactive Chat                   |', 'cyan')}\n"
        f"{colorize('|  /help for commands                                |', 'cyan')}\n"
        f"{colorize(f'|  Session: {session.session_id[:8]}...', 'cyan')}{dbg_label}"
        f"{colorize('                     |', 'cyan')}\n"
        f"{colorize('+----------------------------------------------------+', 'cyan')}"
    )
    print(f"\n{banner}\n")

    stash_capture_mode = False

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
        if not text:
            if stash_capture_mode:
                print(f"{colorize('JARVIS > cancelled stash capture.', 'yellow')}")
                stash_capture_mode = False
            continue

        # Alias expansion
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
                result = request_json(state.base_url, "/api/chat", payload)
                reply = extract_reply(result)
                if is_limited_mode_reply(reply):
                    ensure_ollama_running(env)
                    result = request_json(state.base_url, "/api/chat", payload)
                    reply = extract_reply(result)
                state.session.add_message("assistant", reply)
                state.session.save()

                if state.debug and "_debug" in result:
                    dbg = result["_debug"]
                    print(f"{colorize('[DEBUG]', 'yellow')} session_id={dbg['session_id']}")
                    print(f"{colorize('[DEBUG]', 'yellow')} model={dbg['model']} history_count={dbg['history_count']}")
                    print(f"{colorize('[DEBUG]', 'yellow')} messages sent: {json.dumps(dbg['messages_sent'], indent=2)}")
                if state.debug_search:
                    intent = result.get("intent", {})
                    action = result.get("action", {})
                    if intent.get("intent") in ("web_search", "search"):
                        print(f"{colorize('[DEBUG-SEARCH]', 'yellow')} query: {text}")
                        print(f"{colorize('[DEBUG-SEARCH]', 'yellow')} action: {action.get('action', '')[:500]}")
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

            ts_prefix = ""
            if state.show_timestamps:
                ts_str = datetime.now().strftime("%H:%M:%S")
                ts_prefix = f"{colorize(f'[{ts_str}]', 'timestamp')} "

            print(f"{colorize('JARVIS >', 'cyan')} {ts_prefix}{reply}")
            specialist = result.get("specialist", {}).get("name")
            if specialist:
                agent_str = f"[agent={specialist}]"
                print(f"        {colorize(agent_str, 'green')}")
            lat_str = f"[{result.get('latency_ms', 0)} ms]"
            print(f"        {colorize(lat_str, 'dim')}")
        except Exception as exc:
            print(f"{colorize('JARVIS > request failed:', 'red')} {exc}")


def handle_cli_slash_command(text: str, state: CliState) -> str:
    from core.session import ConversationManager, list_sessions

    lowered = text.lower().strip()

    # --- Session info ---
    if lowered in {"/session", "/s"}:
        s = state.session
        name = getattr(s, "name", None) or ""
        name_str = f" ({name})" if name else ""
        print(f"Session: {s.session_id}{name_str}")
        print(f"Created: {s.created_at}")
        print(f"Messages: {s.message_count}")
        print(f"Tokens: {s.token_count}")
        print(f"Mode: {state.mode}")
        print(f"Model: {state.current_model}")
        return "handled"

    # --- List sessions ---
    if lowered == "/sessions":
        sessions = list_sessions()
        if not sessions:
            print("No sessions found.")
        else:
            print(f"{'ID':<40} {'Created':<28} {'Msgs':<6} {'Name':<20}")
            print("-" * 94)
            for s in sessions:
                sid = s.get("session_id", "?")
                created = s.get("created_at", "")[:19]
                count = s.get("message_count", 0)
                name = ""
                spath = Path.home() / ".jarvis" / "sessions" / f"{sid}.json"
                if spath.exists():
                    try:
                        sdata = json.loads(spath.read_text(encoding="utf-8"))
                        name = sdata.get("name", "") or ""
                    except Exception:
                        pass
                print(f"{sid:<40} {created:<28} {count:<6} {name:<20}")
        return "handled"

    # --- New session ---
    if lowered == "/session-new":
        state.session.save()
        state.session = ConversationManager()
        print(f"JARVIS > new session: {state.session.session_id}")
        return "handled"

    # --- Switch session ---
    if lowered.startswith("/session-switch "):
        sid = text.split(None, 1)[1].strip()
        spath = Path.home() / ".jarvis" / "sessions" / f"{sid}.json"
        if not spath.exists():
            print(f"JARVIS > session not found: {sid}")
        else:
            state.session.save()
            state.session = ConversationManager(session_id=sid)
            state.session.load()
            print(f"JARVIS > switched to session: {sid} ({state.session.message_count} messages)")
        return "handled"

    # --- Rename session ---
    if lowered.startswith("/session-rename "):
        name = text.split(None, 1)[1].strip()
        state.session.rename(name)
        print(f"JARVIS > session renamed to: {name}")
        return "handled"

    # --- Export session ---
    if lowered == "/session-export":
        path = state.session.export_transcript()
        print(f"JARVIS > session exported to: {path}")
        return "handled"

    # --- Fork session ---
    if lowered == "/session-fork":
        new_cm = state.session.fork()
        print(f"JARVIS > forked new session: {new_cm.session_id}")
        state.session.save()
        state.session = new_cm
        return "handled"

    # --- Compact session ---
    if lowered == "/session-compact":
        before = state.session.message_count
        state.session.compact()
        after = state.session.message_count
        print(f"JARVIS > compacted session: {before} -> {after} messages")
        return "handled"

    # --- Undo ---
    if lowered == "/undo":
        msgs = state.session.messages
        if len(msgs) < 2:
            print("JARVIS > nothing to undo.")
        else:
            removed = msgs[-2:]
            if removed[0]["role"] == "user" and removed[-1]["role"] == "assistant":
                state.session.messages = msgs[:-2]
                state.session.save()
                print(f"JARVIS > removed last exchange ({len(removed)} messages).")
            else:
                last = msgs.pop()
                state.session.save()
                print(f"JARVIS > removed last {last['role']} message.")
        return "handled"

    # --- Model ---
    if lowered == "/model":
        print(f"JARVIS > current model: {state.current_model}")
        return "handled"
    if lowered.startswith("/model "):
        model = text.split(None, 1)[1].strip()
        state.current_model = model
        if state.config:
            state.config.default_model = model
            state.config.save()
        print(f"JARVIS > model set to: {model}")
        return "handled"

    # --- Clear ---
    if lowered == "/clear":
        os.system("cls" if os.name == "nt" else "clear")
        return "handled"

    # --- Timestamps ---
    if lowered == "/timestamps":
        state.show_timestamps = not state.show_timestamps
        if state.config:
            state.config.show_timestamps = state.show_timestamps
            state.config.save()
        status = "ON" if state.show_timestamps else "OFF"
        print(f"JARVIS > timestamps {status}")
        return "handled"

    # --- Debug ---
    if lowered == "/debug":
        state.debug = not state.debug
        if state.config:
            state.config.debug = state.debug
            state.config.save()
        status = "ON" if state.debug else "OFF"
        print(f"JARVIS > debug {status}")
        return "handled"

    # --- Debug Search ---
    if lowered == "/debug-search":
        state.debug_search = not state.debug_search
        if state.config:
            state.config.debug_search = state.debug_search
            state.config.save()
        status = "ON" if state.debug_search else "OFF"
        print(f"JARVIS > debug-search {status}")
        return "handled"

    # --- Theme ---
    if lowered == "/theme":
        if state.config:
            new_theme = "light" if state.config.theme == "dark" else "dark"
            state.config.theme = new_theme
            state.config.save()
            print(f"JARVIS > theme set to {new_theme}. (restart to take full effect)")
        else:
            print("JARVIS > theme toggled.")
        return "handled"

    # --- History ---
    if lowered == "/history" or lowered.startswith("/history "):
        parts = text.split()
        n = 10
        if len(parts) > 1:
            try:
                n = int(parts[1])
            except ValueError:
                pass
        msgs = state.session.messages
        if not msgs:
            print("No messages.")
        else:
            for msg in msgs[-n:]:
                ts = msg.get("timestamp", "")[:19]
                ts_str = f"[{ts}] " if ts else ""
                print(f"{ts_str}{msg['role'].upper()}: {msg['content'][:200]}")
        return "handled"

    # --- Agent mode ---
    if lowered == "/agent":
        print(f"JARVIS > current mode: {state.mode}")
        return "handled"
    if lowered.startswith("/agent "):
        target = text.split(None, 1)[1].strip().lower()
        if target not in {"chat", "agent"}:
            print("JARVIS > mode must be 'chat' or 'agent'.")
        else:
            state.mode = target
            if state.config:
                state.config.mode = target
                state.config.save()
            print(f"JARVIS > mode set to {target}.")
        return "handled"

    # --- Mode alias ---
    if lowered.startswith("/mode "):
        target = text.split(None, 1)[1].strip().lower()
        if target not in {"chat", "agent"}:
            print("JARVIS > mode must be 'chat' or 'agent'.")
        else:
            state.mode = target
            if state.config:
                state.config.mode = target
                state.config.save()
            print(f"JARVIS > mode set to {target}.")
        return "handled"

    # --- Stash ---
    if lowered == "/stash":
        return "stash_capture"
    if lowered.startswith("/stash "):
        stash_text = text.split(None, 1)[1].strip()
        idx = state.session.stash_prompt(stash_text)
        print(f"JARVIS > stashed as #{idx}.")
        return "handled"

    # --- Stash list ---
    if lowered == "/stash-list":
        items = state.session.list_stash()
        if not items:
            print("No stashed prompts.")
        else:
            for item in items:
                idx = item.get("index", 0)
                label = item.get("label", "") or ""
                text_preview = item.get("text", "")[:80]
                print(f"  #{idx:3d}  {label:15} {text_preview}")
        return "handled"

    # --- Stash load ---
    if lowered.startswith("/stash-load "):
        parts = text.split()
        try:
            idx = int(parts[1])
        except (IndexError, ValueError):
            print("Usage: /stash-load <n>")
            return "handled"
        stash_text = state.session.load_stash(idx)
        if not stash_text:
            print(f"JARVIS > stash #{idx} not found.")
        else:
            state._pending_text = stash_text
            print(f"JARVIS > loaded stash #{idx}.")
            return "skip"
        return "handled"

    # --- File tools ---
    if lowered.startswith("/read "):
        path = text.split(None, 1)[1].strip()
        import asyncio
        from core.file_agent import file_agent
        try:
            content = asyncio.run(file_agent.read_file(path))
            if len(content) > 2000:
                print(f"{path} ({len(content)} chars, showing first 2000):")
                print(content[:2000])
                print(f"\n... ({len(content) - 2000} more chars)")
            else:
                print(content)
        except Exception as e:
            print(f"Error reading {path}: {e}")
        return "handled"

    if lowered.startswith("/write "):
        path = text.split(None, 1)[1].strip()
        print("Enter file content (end with '---END---' on its own line):")
        lines = []
        try:
            while True:
                line = input()
                if line.strip() == "---END---":
                    break
                lines.append(line)
        except (KeyboardInterrupt, EOFError):
            print("\nCancelled.")
            return "handled"
        content = "\n".join(lines)
        import asyncio
        from core.file_agent import file_agent
        result = asyncio.run(file_agent.write_file(path, content))
        if result.get("cancelled"):
            print("Write cancelled.")
        elif result.get("changed"):
            print(f"Written to {path} ({result['size']} bytes)")
        else:
            print(f"File unchanged: {path}")
        return "handled"

    if lowered.startswith("/edit "):
        path = text.split(None, 1)[1].strip()
        print(f"Enter SEARCH block (end with '---REPLACE---' on its own line, then REPLACE block, end with '---END---'):")
        lines = []
        try:
            while True:
                line = input()
                if line.strip() == "---END---":
                    break
                lines.append(line)
        except (KeyboardInterrupt, EOFError):
            print("\nCancelled.")
            return "handled"
        full = "\n".join(lines)
        if "---REPLACE---" in full:
            parts = full.split("---REPLACE---", 1)
            search_text = parts[0].strip("\n")
            replace_text = parts[1].strip("\n")
            import asyncio
            from core.file_agent import file_agent
            result = asyncio.run(file_agent.edit_file(path, search_text, replace_text))
            if result.get("error"):
                print(f"Edit failed: {result['error']}")
            elif result.get("cancelled"):
                print("Edit cancelled.")
            else:
                print(f"Edited {path} ({'exact' if result.get('exact_match') else 'fuzzy'} match)")
        else:
            print("Error: no ---REPLACE--- separator found.")
        return "handled"

    if lowered.startswith("/ls") or lowered.startswith("/dir "):
        parts = text.split(None, 1)
        path = parts[1].strip() if len(parts) > 1 else "."
        recursive = " -r" in lowered or " --recursive" in lowered
        import asyncio
        from core.file_agent import file_agent
        try:
            files = asyncio.run(file_agent.list_files(path, recursive=recursive))
            if not files:
                print(f"No files in {path}")
            else:
                total = len(files)
                for f in files[:30]:
                    size = f["size"]
                    size_str = f"{size:,} B" if size < 1024 else f"{size/1024:.1f} KB" if size < 1048576 else f"{size/1048576:.1f} MB"
                    print(f"  {f['name']:<50} {size_str:>10}")
                if total > 30:
                    print(f"  ... and {total - 30} more files")
        except Exception as e:
            print(f"Error: {e}")
        return "handled"

    if lowered.startswith("/tree "):
        path = text.split(None, 1)[1].strip()
        import asyncio
        from core.file_agent import file_agent
        try:
            tree = asyncio.run(file_agent.tree_view(path))
            print(tree)
        except Exception as e:
            print(f"Error: {e}")
        return "handled"

    if lowered.startswith("/run "):
        cmd = text.split(None, 1)[1].strip()
        import asyncio
        from core.file_agent import file_agent
        result = asyncio.run(file_agent.run_command(cmd))
        if result.get("error"):
            print(f"Error: {result['error']}")
        elif result.get("cancelled"):
            print("Command cancelled.")
        else:
            if result["stdout"]:
                print(result["stdout"])
            if result["stderr"]:
                print(f"[stderr]\n{result['stderr']}")
            print(f"[exit code: {result['returncode']}]")
        return "handled"

    if lowered == "/diff":
        import asyncio
        from core.file_agent import file_agent
        result = asyncio.run(file_agent.run_command("git diff", skip_confirm=True))
        if result.get("stdout"):
            print(result["stdout"])
        else:
            print("No changes or not a git repository.")
        return "handled"

    if lowered.startswith("/diff "):
        path = text.split(None, 1)[1].strip()
        import asyncio
        from core.file_agent import file_agent
        result = asyncio.run(file_agent.run_command(f"git diff -- {path}", skip_confirm=True))
        if result.get("stdout"):
            print(result["stdout"])
        else:
            print(f"No changes to {path}")
        return "handled"

    # --- Config commands ---
    if lowered == "/config":
        cfg = state.config
        print(f"default_model: {cfg.default_model}")
        print(f"debug: {cfg.debug}")
        print(f"debug_search: {cfg.debug_search}")
        print(f"show_timestamps: {cfg.show_timestamps}")
        print(f"mode: {cfg.mode}")
        print(f"theme: {cfg.theme}")
        print(f"aliases: {json.dumps(cfg.aliases or {}, indent=2)}")
        return "handled"

    if lowered.startswith("/config "):
        parts = text.split(None, 2)
        if len(parts) < 3:
            print("Usage: /config <key> <value>")
            return "handled"
        key = parts[1]
        val = parts[2]
        cfg = state.config
        if not hasattr(cfg, key):
            print(f"Unknown config key: {key}")
            return "handled"
        # Parse value
        if isinstance(getattr(cfg, key), bool):
            setattr(cfg, key, val.lower() in ("true", "yes", "1", "on"))
        elif isinstance(getattr(cfg, key), int):
            setattr(cfg, key, int(val))
        else:
            setattr(cfg, key, val)
        cfg.save()
        print(f"Config updated: {key} = {getattr(cfg, key)}")
        # Sync to state
        if key == "debug":
            state.debug = cfg.debug
        elif key == "debug_search":
            state.debug_search = cfg.debug_search
        elif key == "show_timestamps":
            state.show_timestamps = cfg.show_timestamps
        elif key == "default_model":
            state.current_model = cfg.default_model
        elif key == "mode":
            state.mode = cfg.mode
        return "handled"

    if lowered == "/alias":
        cfg = state.config
        if not cfg.aliases:
            print("No aliases defined.")
        else:
            for k, v in cfg.aliases.items():
                print(f"  /{k} -> {v}")
        return "handled"

    if lowered.startswith("/alias "):
        parts = text.split(None, 2)
        if len(parts) < 3:
            print("Usage: /alias <name> <command>")
            return "handled"
        name = parts[1].lstrip("/")
        command = parts[2]
        cfg = state.config
        if cfg.aliases is None:
            cfg.aliases = {}
        cfg.aliases[name] = command
        cfg.save()
        print(f"Alias set: /{name} -> {command}")
        return "handled"

    if lowered.startswith("/alias-del "):
        name = text.split(None, 1)[1].strip().lstrip("/")
        cfg = state.config
        if cfg.aliases and name in cfg.aliases:
            del cfg.aliases[name]
            cfg.save()
            print(f"Alias removed: /{name}")
        else:
            print(f"Alias not found: /{name}")
        return "handled"

    # --- Status ---
    if lowered == "/status":
        cmd_status(argparse.Namespace())
        return "handled"

    # --- Help ---
    if lowered in {"/help", "/h", "/?"}:
        print_help()
        return "handled"

    # --- Exit ---
    if lowered in {"/exit"}:
        print("JARVIS > saving session and exiting...")
        return "exit"

    # --- UI Generation ---
    if lowered.startswith("/generate-ui ") or lowered.startswith("/gui "):
        prompt = text.split(None, 1)[1].strip()
        context = "html"
        if " --flutter" in lowered or " --fl" in lowered:
            context = "flutter"
        prompt_clean = prompt.replace(" --flutter", "").replace(" --fl", "")
        result = request_json(state.base_url, "/api/generate-ui", {
            "message": prompt_clean,
            "context": context,
        })
        if result.get("error"):
            print(f"{colorize('Error:', 'red')} {result['error']}")
        else:
            fp = result.get("file_path", "?")
            print(f"{colorize('Generated UI:', 'green')} {fp}")
            print(f"{colorize('Preview:', 'cyan')}")
            code = result.get("code", "")
            if len(code) > 500:
                print(code[:500])
                print(f"\n... ({len(code) - 500} more chars)")
            else:
                print(code)
        return "handled"

    # --- Legacy commands (forward-compat) ---
    if lowered == "/tools":
        result = request_json(state.base_url, "/os/tools", method="GET")
        tools = [tool.get("name", "") for tool in result.get("tools", [])]
        print("Tools:", ", ".join(sorted(name for name in tools if name)))
        return "handled"

    # --- OpenCode delegate ---
    if lowered.startswith("/opencode "):
        task = text.split(None, 1)[1].strip()
        import asyncio
        from core.context_hub import ContextHub
        from core.opencode_delegate import delegate_to_opencode, is_opencode_task
        if not is_opencode_task(task) and " --force" not in lowered:
            print(f"{colorize('Not clearly an opencode task.', 'yellow')} Use --force to override.")
            return "handled"
        print(f"{colorize('Delegating to opencode...', 'cyan')}")
        hub = ContextHub()
        ctx = asyncio.run(hub.gather(task_type="code", prompt=task))
        result = asyncio.run(delegate_to_opencode(
            task=task,
            context={"context_hub": hub, "extra_context": hub.format_for_prompt(ctx)},
            timeout=300,
        ))
        if result.get("success"):
            print(f"{colorize('OpenCode completed:', 'green')}")
            if result["stdout"]:
                print(result["stdout"][:3000])
        else:
            print(f"{colorize('OpenCode failed:', 'red')} {result.get('error', 'unknown')}")
            if result.get("stdout"):
                print(result["stdout"][:1000])
        return "handled"

    if lowered.startswith("/plan "):
        prompt = text.split(None, 1)[1].strip()
        context = build_cli_context(prompt)
        context["cli_mode"] = state.mode
        endpoint = "/os/agents/preview" if state.mode == "agent" else "/os/agent/plan"
        payload = {"prompt": prompt, "context": context}
        if state.mode == "agent":
            payload["agent_name"] = "auto"
        preview = request_json(state.base_url, endpoint, payload)
        specialist = preview.get("specialist", {}).get("name")
        if specialist:
            print(f"Agent: {specialist}")
        print_plan_preview(preview)
        return "handled"
    if lowered.startswith("/goal "):
        prompt = text.split(None, 1)[1].strip()
        context = build_cli_context(prompt)
        context["cli_mode"] = state.mode
        endpoint = "/os/agents/submit" if state.mode == "agent" else "/os/agent/submit"
        payload = {"prompt": prompt, "context": context}
        if state.mode == "agent":
            payload["agent_name"] = "auto"
        result = request_json(state.base_url, endpoint, payload)
        specialist = result.get("specialist", {}).get("name")
        if specialist:
            print(f"Agent: {specialist}")
        print(f"JARVIS > queued goal {result['goal']['goal_id']} as job {result['job_id']}")
        print_plan_preview(result)
        return "handled"
    if lowered.startswith("/develop "):
        prompt = text.split(None, 1)[1].strip()
        context = build_cli_context(prompt)
        context["cli_mode"] = state.mode
        endpoint = "/os/agents/submit" if state.mode == "agent" else "/os/agent/submit"
        payload = {"prompt": prompt, "context": context}
        if state.mode == "agent":
            payload["agent_name"] = "auto"
        result = request_json(state.base_url, endpoint, payload)
        specialist = result.get("specialist", {}).get("name")
        if specialist:
            print(f"Agent: {specialist}")
        print(f"JARVIS > starting development goal {result['goal']['goal_id']}")
        print_plan_preview(result)
        poll_job(state.base_url, result["job_id"])
        return "handled"
    if lowered.startswith("/vision "):
        prompt = text.split(None, 1)[1].strip()
        context = build_cli_context(prompt)
        context["intent"] = "vision"
        context["cli_mode"] = state.mode
        result = request_json(state.base_url, "/os/agent/think", {"prompt": prompt, "context": context})
        print(f"JARVIS > {extract_reply(result)}")
        return "handled"
    if lowered.startswith("/feedback "):
        parts = text.split(None, 2)
        if len(parts) >= 3:
            accepted = parts[1].lower() in ("yes", "y", "good", "correct", "1", "true")
            reason = parts[2]
            try:
                result = request_json(state.base_url, "/feedback", {
                    "message": "", "response": "", "accepted": accepted, "reason": reason
                })
                print(f"JARVIS > Feedback recorded. Rules: {result.get('rules', 0)}")
            except Exception as exc:
                print(f"Feedback failed: {exc}")
        else:
            print("Usage: /feedback <yes|no> <reason>")
        return "handled"

    return "ignored"


def print_help():
    print(colorize("""JARVIS CLI Commands:

Session:
  /session /s           Show current session info
  /sessions             List all sessions
  /session-new          Start a new session
  /session-switch <id>  Switch to a session
  /session-rename <name> Rename session
  /session-export       Export session transcript
  /session-fork         Fork current session
  /session-compact      Compact session (summarize old)
  /undo                 Remove last exchange

Model:
  /model                Show current model
  /model <name>         Switch model

Config:
  /config               Show all config values
  /config <key> <val>   Set a config value (saved to ~/.jarvis/config.json)
  /alias                List aliases
  /alias <name> <cmd>   Define a command alias
  /alias-del <name>     Remove an alias

Display:
  /clear                Clear screen
  /timestamps           Toggle timestamps
  /debug                Toggle debug mode
  /debug-search         Toggle search result debugging
  /theme                Toggle dark/light theme

History:
  /history [n]          Show last N exchanges (default 10)

Agent:
  /agent /mode          Show current mode
  /agent <mode>         Switch mode (chat/agent)

Stash:
  /stash <text>         Save a prompt
  /stash-list           List stashed prompts
  /stash-load <n>       Load a stashed prompt

System:
  /status               Show system status
  /help /h /?           Show this help
  /exit                 Save and exit

Files:
  /read <path>          Read and display a file
  /write <path>         Write content to a file
  /edit <path>          Edit file with SEARCH/REPLACE blocks
  /ls [path]            List files in directory
  /tree <path>          Show directory tree
  /run <command>        Run a shell command
  /diff [path]          Show git diff

Generate:
  /generate-ui <desc>   Generate a UI from description (--flutter for Flutter)
  /gui <desc>           Shortcut for /generate-ui

Delegation:
  /opencode <task>      Delegate heavy coding task to opencode (--force to bypass detection)

Other:
  /plan <goal>          Preview an execution plan
  /goal <goal>          Submit a long-running goal
  /develop <goal>       Start development workflow
  /vision <prompt>      Vision analysis
  /feedback <yes|no> <reason>  Provide feedback
  /tools                List available tools

CLI Enhancements:
  Tab completion        Hit Tab to complete commands, paths, sessions, models
  History               Up/Down arrows navigate command history
  Aliases               Define shortcuts with /alias <name> <command>
  Persistent config     Settings saved to ~/.jarvis/config.json""", 'cyan'))


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


def backend_server_cmd(host: str, port: int, reload_enabled: bool) -> list[str]:
    code = (
        "import sys, uvicorn; "
        "getattr(sys.stdout, 'reconfigure', lambda **kwargs: None)(encoding='utf-8', errors='replace'); "
        "getattr(sys.stderr, 'reconfigure', lambda **kwargs: None)(encoding='utf-8', errors='replace'); "
        "h, p, r = sys.argv[1], int(sys.argv[2]), sys.argv[3].lower() == 'true'; "
        "uvicorn.run('core.main:app', host=h, port=p, reload=r)"
    )
    return [python_exe(), "-c", code, host, str(port), str(reload_enabled).lower()]


def parse_server_location(base_url: str) -> tuple[str, int]:
    parsed = urlparse(base_url if "://" in base_url else f"http://{base_url}")
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return host, port


def is_port_open(host: str, port: int, timeout: float = 0.3) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def is_server_reachable(base_url: str, timeout: float = 1.0) -> bool:
    host, port = parse_server_location(base_url)
    if not is_port_open(host, port, timeout=min(timeout, 0.3)):
        return False
    for endpoint in ("/health", "/os/status", "/"):
        try:
            request = urllib.request.Request(
                f"{base_url.rstrip('/')}{endpoint}",
                headers={"Connection": "close", "User-Agent": "JARVIS-Launcher"},
            )
            with urllib.request.urlopen(request, timeout=timeout) as response:
                if getattr(response, "status", 200) < 500:
                    return True
        except (urllib.error.URLError, TimeoutError, OSError):
            continue
        except Exception:
            continue
    return False


def wait_for_server(base_url: str, attempts: int = 30, interval_s: float = 1.0) -> bool:
    for _ in range(attempts):
        time.sleep(interval_s)
        if is_server_reachable(base_url, timeout=0.5):
            return True
    return False


def ensure_server_running(base_url: str, host: str = "127.0.0.1", port: int = 8000):
    target_host, target_port = parse_server_location(base_url)
    if target_host not in {"127.0.0.1", "localhost"}:
        return
    if is_server_reachable(base_url, timeout=0.5):
        return
    print("JARVIS backend is not running. Starting local server...")
    env = common_env()
    spawn_background(
        "JARVIS-Server",
        backend_server_cmd(target_host or host, target_port or port, False),
        cwd=ROOT,
        env=env,
        dry_run=False,
    )
    if wait_for_server(base_url):
        print(f"JARVIS backend ready at {base_url}")
        return
    print(f"JARVIS backend did not become ready at {base_url}")


def ollama_base_url(env: dict) -> str:
    return env.get("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")


def is_ollama_reachable(env: dict, timeout: float = 1.0) -> bool:
    base_url = ollama_base_url(env)
    try:
        with urllib.request.urlopen(f"{base_url}/api/tags", timeout=timeout):
            return True
    except Exception:
        return False


def ensure_ollama_running(env: dict):
    auto_models = env.get("JARVIS_AUTO_MODELS", "single").lower()
    if auto_models == "multi" or env.get("OLLAMA_MULTI_INSTANCE", "").lower() in {"1", "true", "yes", "on"}:
        for model, port in MODEL_PORTS:
            model_env = env.copy()
            model_env.update(
                {
                    "OLLAMA_HOST": f"127.0.0.1:{port}",
                    "OLLAMA_NUM_GPU": model_env.get("OLLAMA_NUM_GPU", "99"),
                    "OLLAMA_KEEP_ALIVE": model_env.get("OLLAMA_KEEP_ALIVE", "300"),
                    "OLLAMA_NUM_PARALLEL": model_env.get("OLLAMA_NUM_PARALLEL", "1"),
                    "OLLAMA_FLASH_ATTENTION": model_env.get("OLLAMA_FLASH_ATTENTION", "1"),
                    "OLLAMA_KV_CACHE_TYPE": model_env.get("OLLAMA_KV_CACHE_TYPE", "q8_0"),
                    "OLLAMA_MAX_LOADED_MODELS": model_env.get("OLLAMA_MAX_LOADED_MODELS", "1"),
                    "CUDA_VISIBLE_DEVICES": model_env.get("CUDA_VISIBLE_DEVICES", "0"),
                }
            )
            url = f"http://127.0.0.1:{port}"
            try:
                with urllib.request.urlopen(f"{url}/api/tags", timeout=1.0):
                    continue
            except Exception:
                print(f"Starting Ollama model endpoint for {model} on {port}...")
                spawn_background(f"Ollama-{model}", ["ollama", "serve"], cwd=ROOT, env=model_env, dry_run=False)
        env["OLLAMA_MULTI_INSTANCE"] = "1"
        env["OLLAMA_MODEL_ENDPOINTS"] = ";".join(f"{model}=http://127.0.0.1:{port}" for model, port in MODEL_PORTS)
        time.sleep(2)
        return

    if is_ollama_reachable(env):
        return
    print("Ollama is not running. Starting local model server...")
    spawn_background("Ollama", ["ollama", "serve"], cwd=ROOT, env=env, dry_run=False)
    for _ in range(20):
        time.sleep(1)
        if is_ollama_reachable(env):
            print(f"Ollama ready at {ollama_base_url(env)}")
            return
    print(f"Ollama did not become ready at {ollama_base_url(env)}")


def wait_for_ollama_ready(timeout_s: int = 30) -> bool:
    """Wait for Ollama to be reachable, with timeout."""
    for _ in range(timeout_s):
        if is_ollama_reachable({}):
            return True
        time.sleep(1)
    return False


def ensure_local_stack_running(env: dict):
    ensure_ollama_running(env)
    ensure_server_running(env.get("JARVIS_SERVER", "http://127.0.0.1:8000"))


def legacy_endpoint_fallback(endpoint: str, payload: dict | None = None) -> tuple[str, dict | None] | None:
    mapping = {
        "/os/agents/run": "/os/agent/think",
        "/os/agents/preview": "/os/agent/plan",
        "/os/agents/submit": "/os/agent/submit",
    }
    fallback = mapping.get(endpoint)
    if not fallback:
        return None
    normalized_payload = dict(payload or {})
    normalized_payload.pop("agent_name", None)
    return fallback, normalized_payload


def get_local_os_runtime():
    global _local_os_runtime
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    if _local_os_runtime is None:
        from jarvis_os.bootstrap import build_jarvis_os
        
        _local_os_runtime = build_jarvis_os()
    return _local_os_runtime


def _run_async(coro):
    """Run a coroutine synchronously from sync code."""
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(asyncio.run, coro)
        return future.result()


def _normalize_local_execution(result: dict) -> dict:
    execution = dict(result.get("execution", {}))
    if "results" in execution and "step_results" not in execution:
        execution["step_results"] = list(execution.get("results", []))
    if "latency_ms" not in result:
        if execution.get("started_at") and execution.get("completed_at"):
            result["latency_ms"] = int((execution["completed_at"] - execution["started_at"]) * 1000)
        else:
            result["latency_ms"] = 0
    result["execution"] = execution
    return result


def _local_goal(prompt: str, context: dict | None = None) -> dict:
    return {
        "goal_id": f"goal_{uuid.uuid4().hex[:10]}",
        "prompt": prompt,
        "context": dict(context or {}),
    }


def local_request_json(endpoint: str, payload: dict | None = None, method: str | None = None) -> dict:
    runtime = get_local_os_runtime()
    data = dict(payload or {})
    prompt = data.get("prompt", "")
    context = data.get("context") or {}
    agent_name = data.get("agent_name", "auto")

    if method == "GET" and endpoint == "/os/tools":
        return {"tools": runtime.tools.catalog()}
    if method == "GET" and endpoint == "/os/status":
        status = runtime.status()
        return {
            "initialized": True,
            "components": {
                "tools": runtime.tools.catalog(),
                "models": status.get("models", {}),
                "scheduler": {"count": status.get("schedule_count", 0)},
                "skills_registry": {"count": status.get("skills", 0)},
                "supervisor": status.get("daemon", {}),
                "safety": status.get("policy", {}),
                "self_improvement": {"running": status.get("daemon", {}).get("running", False)},
                "world_model": {"memories": status.get("memory_items", 0), "goals": len(runtime.list_jobs().get("jobs", [])), "knowledge": 0, "experiences": 0},
                "learning": {"enabled": True, "student_agi_loaded": False},
                "browser": {"mode": "local"},
                "access_manager": {"grants": []},
                "mobile_sync": {"linked_devices": []},
                "gateway": {"channels": {}},
            },
        }
    if endpoint in {"/os/agents/preview", "/os/agent/plan"}:
        preview = runtime.preview_prompt(prompt, context=context, agent_name=agent_name)
        if asyncio.iscoroutine(preview):
            preview = _run_async(preview)
        preview["goal"] = _local_goal(prompt, context)
        return preview
    if endpoint in {"/os/agents/run", "/os/agent/think"}:
        result = runtime.handle_prompt(prompt, context=context, agent_name=agent_name)
        if asyncio.iscoroutine(result):
            result = _run_async(result)
        return _normalize_local_execution(result)
    if endpoint in {"/os/agents/submit", "/os/agent/submit"}:
        submission = runtime.submit_prompt(prompt, context=context, agent_name=agent_name)
        if asyncio.iscoroutine(submission):
            submission = _run_async(submission)
        preview = submission.get("preview", {})
        job = submission.get("job", {})
        return {
            "goal": _local_goal(prompt, context),
            "job_id": job.get("job_id", ""),
            "plan": preview.get("plan", {}),
            "analysis": preview.get("analysis", {}),
            "specialist": preview.get("specialist", {}),
        }
    if method == "GET" and endpoint.startswith("/os/executions/"):
        job_id = endpoint.rsplit("/", 1)[-1]
        job = runtime.get_job(job_id)
        if asyncio.iscoroutine(job):
            job = _run_async(job)
        result = job.get("result", {})
        if result:
            result = _normalize_local_execution(result)
            execution = result.get("execution", {})
            return {
                "job_id": job_id,
                "status": job.get("status", "missing"),
                "result": {
                    "summary": execution.get("summary", result.get("reply", "")),
                    "step_results": execution.get("step_results", []),
                },
            }
        return {"job_id": job_id, "status": job.get("status", "missing"), "error": job.get("error", "")}
    raise urllib.error.HTTPError(url=endpoint, code=404, msg="Not Found", hdrs=None, fp=None)


def request_json(base_url: str, endpoint: str, payload: dict | None = None, method: str | None = None) -> dict:
    global _legacy_route_notice_shown, _local_runtime_notice_shown
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}{endpoint}",
        data=data,
        headers={"Content-Type": "application/json"},
        method=method or ("POST" if data else "GET"),
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        fallback = legacy_endpoint_fallback(endpoint, payload)
        if exc.code == 404 and fallback:
            legacy_endpoint, legacy_payload = fallback
            if not _legacy_route_notice_shown:
                print("JARVIS > detected older backend routes; using compatibility mode.")
                _legacy_route_notice_shown = True
            result = request_json(base_url, legacy_endpoint, legacy_payload, method=method)
            if isinstance(result, dict):
                result.setdefault("_jarvis_compat", {})["fallback_endpoint"] = legacy_endpoint
            return result
        if endpoint.startswith("/os/") and exc.code == 404:
            if not _local_runtime_notice_shown:
                print("JARVIS > backend AI OS routes unavailable; using local JARVIS OS runtime.")
                _local_runtime_notice_shown = True
            return local_request_json(endpoint, payload, method=method or ("POST" if data else "GET"))
        raise
    except urllib.error.URLError:
        if endpoint.startswith("/os/"):
            if not _local_runtime_notice_shown:
                print("JARVIS > backend unreachable; using local JARVIS OS runtime.")
                _local_runtime_notice_shown = True
            return local_request_json(endpoint, payload, method=method or ("POST" if data else "GET"))
        raise


def poll_job(base_url: str, job_id: str, max_wait_s: int = 180) -> int:
    waited = 0
    while waited < max_wait_s:
        result = request_json(base_url, f"/os/executions/{job_id}", method="GET")
        status = result.get("status", "missing")
        if status in {"completed", "failed"}:
            print(f"Job status: {status}")
            payload = result.get("result", {})
            if payload:
                print(payload.get("summary", "No summary"))
                for step in payload.get("step_results", []):
                    mark = "ok" if step.get("success") else "fail"
                    detail = step.get("error") or step.get("tool")
                    print(f"  - {mark}: {detail}")
            elif result.get("error"):
                print(result["error"])
            return 0 if status == "completed" else 1
        if waited == 0:
            print("Running...")
        time.sleep(2)
        waited += 2
    print("Timed out waiting for job completion.")
    return 1


def build_cli_context(prompt: str) -> dict:
    cwd = Path.cwd().resolve()
    context = {
        "platform": "cli",
        "cwd": str(cwd),
        "workspace_root": str(cwd),
        "approved": True,
        "local_only": os.getenv("JARVIS_LOCAL_ONLY", "1").lower() not in {"0", "false", "no"},
    }
    lowered = prompt.lower()
    if any(
        token in lowered
        for token in ("project", "repo", "repository", "codebase", "review", "architecture", "develop", "build", "implement", "fix", "debug")
    ):
        context["workspace_summary"] = workspace_snapshot(cwd)
    return context


def is_agentic_prompt(prompt: str) -> bool:
    lowered = prompt.lower()
    triggers = (
        "open ",
        "launch ",
        "review ",
        "analyze ",
        "understand ",
        "inspect ",
        "build ",
        "develop ",
        "implement ",
        "create ",
        "fix ",
        "debug ",
        "plan ",
        "search ",
        "send ",
        "vision ",
        "look at ",
        "read ",
        "list ",
    )
    return any(token in lowered for token in triggers)


def print_plan_preview(result: dict):
    plan = result.get("plan", {})
    analysis = result.get("analysis", {})
    steps = plan.get("steps", [])
    if not steps:
        return
    print("Plan:")
    intent = analysis.get("intent")
    if intent:
        print(f"  intent: {intent}")
    for index, step in enumerate(steps, start=1):
        print(f"  {index}. [{step.get('tool', 'unknown')}] {step.get('action', '')}")


def workspace_snapshot(root: Path) -> str:
    manifest_names = ["pyproject.toml", "requirements.txt", "package.json", "pubspec.yaml", "README.md", "setup.py"]
    manifests = [name for name in manifest_names if (root / name).exists()]
    top_entries = []
    try:
        entries = sorted(root.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower()))
        for entry in entries[:12]:
            top_entries.append(entry.name + ("/" if entry.is_dir() else ""))
    except Exception as err:
        logging.getLogger(__name__).error("workspace_snapshot error: %s", err, exc_info=True)
        raise
    readme_excerpt = ""
    readme = root / "README.md"
    if readme.exists():
        try:
            readme_excerpt = readme.read_text(encoding="utf-8", errors="replace")[:400].replace("\n", " ").strip()
        except Exception:
            readme_excerpt = ""
    return (
        f"Workspace root: {root}. "
        f"Top-level entries: {', '.join(top_entries) or 'none'}. "
        f"Manifests: {', '.join(manifests) or 'none'}. "
        f"README: {readme_excerpt or 'not available'}"
    )


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


def stop_local_services(include_ollama: bool = False):
    if os.name == "nt":
        python_filter = (
            "Get-CimInstance Win32_Process | "
            "Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -match 'core\\.main:app' } | "
            "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
        )
        subprocess.run(["powershell", "-NoProfile", "-Command", python_filter], capture_output=True, text=True)
        if include_ollama:
            ollama_filter = (
                "Get-CimInstance Win32_Process | "
                "Where-Object { $_.Name -eq 'ollama.exe' } | "
                "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
            )
            subprocess.run(["powershell", "-NoProfile", "-Command", ollama_filter], capture_output=True, text=True)
        return

    subprocess.run(["pkill", "-f", "core.main:app"], capture_output=True, text=True)
    if include_ollama:
        subprocess.run(["pkill", "-f", "ollama serve"], capture_output=True, text=True)


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


def extract_reply(result: dict) -> str:
    # /api/chat format: top-level "response" key
    direct = result.get("response")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    # /os/ format: execution.step_results[...].output
    execution = result.get("execution", {})
    for step in reversed(execution.get("step_results", [])):
        output = step.get("output")
        if isinstance(output, dict):
            for key in ("response", "reply", "summary", "speech", "output"):
                value = output.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
            if output.get("success") is False:
                error = output.get("error") or output.get("speech")
                if error:
                    return str(error)
        if isinstance(output, str) and output.strip():
            return output.strip()
        error = step.get("error")
        if error:
            return str(error)
    reflection = result.get("reflection", {})
    lessons = reflection.get("lessons", [])
    if lessons and not execution.get("success", False):
        return str(lessons[0])
    return execution.get("summary", "Request completed.")


def is_limited_mode_reply(reply: str) -> bool:
    lowered = reply.lower()
    return "limited mode" in lowered or "start ollama" in lowered or "ollama" in lowered and "full ai features" in lowered


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jarvis",
        description="Unified JARVIS launcher for CLI, server, GUI, models, and IDE integrations.",
        prefix_chars="-/",
    )
    subparsers = parser.add_subparsers(dest="subcommand")

    cli_parser = subparsers.add_parser("cli", help="Start the interactive JARVIS terminal chat.", prefix_chars="-/")
    cli_parser.add_argument("--new-session", action="store_true", help="Start a fresh session (ignore previous).")
    cli_parser.add_argument("--session", default=None, help="Resume a specific session by ID.")
    cli_parser.add_argument("--debug", action="store_true", help="Dump raw LLM prompts and responses.")
    cli_parser.add_argument("--debug-search", action="store_true", help="Show search queries and raw results.")
    cli_parser.set_defaults(func=cmd_cli)

    chat = subparsers.add_parser("chat", help="Alias for 'jarvis cli'.", prefix_chars="-/")
    chat.add_argument("--new-session", action="store_true", help="Start a fresh session (ignore previous).")
    chat.add_argument("--session", default=None, help="Resume a specific session by ID.")
    chat.add_argument("--debug", action="store_true", help="Dump raw LLM prompts and responses.")
    chat.add_argument("--debug-search", action="store_true", help="Show search queries and raw results.")
    chat.set_defaults(func=cmd_cli)

    status = subparsers.add_parser("status", help="Show current JARVIS autonomous status.", prefix_chars="-/")
    status.set_defaults(func=cmd_status)

    server = subparsers.add_parser("server", help="Start the FastAPI backend server.", prefix_chars="-/")
    server.add_argument("/m", "--multi-model", action="store_true", dest="multi_model", help="Start multi-model Ollama servers before backend.")
    server.add_argument("--host", default="0.0.0.0")
    server.add_argument("--port", type=int, default=8000)
    server.add_argument("--no-reload", action="store_true", help="Disable auto-reload.")
    server.add_argument("--dry-run", action="store_true", help="Print commands instead of executing them.")
    server.set_defaults(func=cmd_server)

    restart = subparsers.add_parser("restart", help="Restart the local backend stack.", prefix_chars="-/")
    restart.add_argument("/m", "--multi-model", action="store_true", dest="multi_model", help="Restart with multi-model Ollama endpoints.")
    restart.add_argument("--with-models", action="store_true", help="Stop existing Ollama processes before restart.")
    restart.add_argument("--host", default="0.0.0.0")
    restart.add_argument("--port", type=int, default=8000)
    restart.add_argument("--no-reload", action="store_true", help="Disable auto-reload after restart.")
    restart.add_argument("--dry-run", action="store_true", help="Print commands instead of executing them.")
    restart.set_defaults(func=cmd_restart)

    gui = subparsers.add_parser("gui", help="Start the Flutter Windows GUI.", prefix_chars="-/")
    gui.add_argument("--device", default="windows")
    gui.add_argument("--host", default="127.0.0.1")
    gui.add_argument("--port", type=int, default=8000)
    gui.add_argument("--api-url")
    gui.add_argument("--ws-url")
    gui.add_argument("--google-api-key", default="", help="Google API key for Flutter app")
    gui.add_argument("--droq-api-key", default="", help="DroQ API key for Flutter app")
    gui.add_argument("--dry-run", action="store_true")
    gui.set_defaults(func=cmd_gui)

    up = subparsers.add_parser("up", help="Start JARVIS desktop stack (server + GUI).", prefix_chars="-/")
    up.add_argument("/m", "--multi-model", action="store_true", dest="multi_model", help="Start multi-model Ollama servers too.")
    up.add_argument("--background", action="store_true", help="Spawn server and GUI in separate windows.")
    up.add_argument("--host", default="127.0.0.1")
    up.add_argument("--port", type=int, default=8000)
    up.add_argument("--device", default="windows")
    up.add_argument("--api-url")
    up.add_argument("--ws-url")
    up.add_argument("--google-api-key", default="", help="Google API key for Flutter app")
    up.add_argument("--droq-api-key", default="", help="DroQ API key for Flutter app")
    up.add_argument("--no-reload", action="store_true")
    up.add_argument("--dry-run", action="store_true")
    up.set_defaults(func=cmd_up)

    student = subparsers.add_parser("student", help="Run the Student AGI service or commands.", prefix_chars="-/")
    student.add_argument("forward", nargs=argparse.REMAINDER)
    student.add_argument("--dry-run", action="store_true")
    student.set_defaults(func=cmd_student)

    models = subparsers.add_parser("models", help="List or start configured model servers.", prefix_chars="-/")
    models_sub = models.add_subparsers(dest="models_command")
    models_list = models_sub.add_parser("list", help="List multi-model endpoint mapping.", prefix_chars="-/")
    models_list.set_defaults(func=cmd_models)
    models_start = models_sub.add_parser("start", help="Start multi-model backend stack.", prefix_chars="-/")
    models_start.add_argument("--host", default="0.0.0.0")
    models_start.add_argument("--port", type=int, default=8000)
    models_start.add_argument("--no-reload", action="store_true")
    models_start.add_argument("--dry-run", action="store_true")
    models_start.set_defaults(func=cmd_models)

    extension = subparsers.add_parser("extension", help="Show IDE/extension integration commands.", prefix_chars="-/")
    extension_sub = extension.add_subparsers(dest="extension_command")
    extension_list = extension_sub.add_parser("list", help="List supported IDE presets.", prefix_chars="-/")
    extension_list.set_defaults(func=cmd_extension)
    extension_show = extension_sub.add_parser("show", help="Show setup commands for one IDE preset.", prefix_chars="-/")
    extension_show.add_argument("ide", choices=sorted(IDE_PRESETS.keys()))
    extension_show.add_argument("--host", default="127.0.0.1")
    extension_show.add_argument("--port", type=int, default=8000)
    extension_show.set_defaults(func=cmd_extension)

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
    args = parser.parse_args()
    if not getattr(args, "subcommand", None):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
