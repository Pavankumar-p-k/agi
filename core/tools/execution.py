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
"""
tool_execution.py

Tool dispatcher and result formatter for the agent loop.
Routes tool blocks to MCP servers or native implementations.

Extracted from agent_tools.py.
"""

import asyncio
import base64
import collections
import json
import logging
import os
import re
import sys
import time
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from core.sandbox.docker_sandbox import docker_sandbox as _docker_sandbox
from core.config_schema import jarvis_config
from core.tools.security import owner_is_admin_or_single_user
from core.sub_agents.tool import do_sessions_spawn

# Build automation adapter — bridges the Graph Runtime to the Automation Loop
from core.tools.build_tools import (
    do_build_project,
    do_repair_project,
    do_run_tests,
    do_runtime_validate,
    cancel_build as do_cancel_build,
)
# Chat/memory tools — formerly BROKEN_TOOLS, now implemented
from core.tools.chat_tools import (
    do_manage_memory,
    do_create_session,
    do_chat_with_model,
)
# Workflow tools — durable multi-step execution
from core.tools.workflow_tools import (
    do_workflow_start,
    do_workflow_resume,
    do_workflow_cancel,
    do_workflow_status,
    do_workflow_list,
)

# Tools that are registered but not yet implemented — return disabled status
BROKEN_TOOLS: set[str] = set()

MAX_OUTPUT_CHARS = 10_000
MAX_READ_CHARS = 20_000

# ---------------------------------------------------------------------------
# Path confinement for read_file / write_file
# ---------------------------------------------------------------------------
# read_file + write_file are admin-only tools, but the path the agent
# supplies is model-controlled. Prompt-injection in an admin's chat can
# weaponise "read /etc/shadow" or "write ~/.ssh/authorized_keys" without
# the admin noticing.
#
# Policy:
#   1. Sensitive-subpath deny list — checked FIRST. Blocks .ssh,
#      .gnupg, shell rc files, token/env files even if the root above
#      them is on the allowlist.
#   2. Allowlist — only the directories the agent legitimately needs
#      (project data/, system tmp). $HOME is NOT on the default list.
#   3. Opt-in extra roots — admin can add broader roots via the
#      "tool_path_extra_roots" setting (list of path strings).
# ---------------------------------------------------------------------------

_SENSITIVE_BASENAMES: set[str] = {
    ".ssh", ".gnupg", ".gitconfig",
    ".bashrc", ".bash_profile", ".bash_logout",
    ".zshrc", ".zprofile", ".zshenv",
    ".profile", ".tcshrc", ".cshrc",
    ".env", ".netrc",
}

_SENSITIVE_FILE_PATTERNS: tuple[str, ...] = (
    "authorized_keys", "id_rsa", "id_ed25519", "id_ecdsa",
    "known_hosts",
)


def _is_sensitive_path(resolved: str) -> bool:
    """Return True if *resolved* falls under a sensitive directory or
    matches a sensitive filename — regardless of what root it sits under.
    """
    parts = resolved.split(os.sep)
    filenames: set[str] = {parts[-1]} if parts else set()

    # Check if any path component is a sensitive directory.
    for part in parts:
        if part in _SENSITIVE_BASENAMES:
            return True

    # Check filename against known sensitive files.
    for pat in _SENSITIVE_FILE_PATTERNS:
        if pat in filenames:
            return True

    return False


def _tool_path_roots() -> list[str]:
    """Return the list of directory roots that read_file / write_file
    may touch. Default: project data/ + system temp dirs. Extra roots
    are loaded from the ``tool_path_extra_roots`` setting.
    """
    roots: list[str] = []

    # Project data directory — the agent's primary workspace.
    from core.constants import DATA_DIR
    roots.append(DATA_DIR)

    # /tmp (and its macOS realpath /private/tmp).
    roots.append("/tmp")
    try:
        private_tmp = os.path.realpath("/tmp")
        if private_tmp != "/tmp":
            roots.append(private_tmp)
    except OSError as _e:
        logger.debug("[core.tools.execution] realpath /tmp failed: %s", _e)

    # $TMPDIR — per-user temp root on macOS (e.g. /var/folders/.../T/).
    tmpdir = os.environ.get("TMPDIR")
    if tmpdir:
        roots.append(tmpdir)

    # Opt-in extra roots from settings.
    try:
        from core.settings import get_setting
        extra = get_setting("tool_path_extra_roots")
        if isinstance(extra, list):
            roots.extend(str(r) for r in extra if r)
    except Exception as _e:
        logger.debug("get_setting extra_roots failed: %s", _e)

    # Deduplicate; resolve symlinks so containment is unambiguous.
    seen: set[str] = set()
    out: list[str] = []
    for r in roots:
        try:
            real = os.path.realpath(r)
        except OSError as _e:
            logger.debug("[core.tools.execution] realpath failed: %s", _e)
            continue
        if real in seen:
            continue
        seen.add(real)
        out.append(real)
    return out


def _resolve_tool_path(raw_path: str) -> str:
    """Resolve and confine a model-supplied path.

    Order of checks:
      1. Non-empty path.
      2. Sensitive-subpath deny list (blocks .ssh, .gnupg, etc.
         even when the root is on the allowlist).
      3. Allowlist containment (must land under one of the roots).

    Returns the realpath on success. Raises ValueError on rejection.
    Symlinks are resolved before comparison.
    """
    if raw_path is None or not str(raw_path).strip():
        raise ValueError("path is required")
    expanded = os.path.expanduser(str(raw_path).strip())
    resolved = os.path.realpath(expanded)

    if _is_sensitive_path(resolved):
        raise ValueError(
            f"path '{raw_path}' is inside a sensitive directory "
            f"(e.g. .ssh, .gnupg) or matches a sensitive filename"
        )

    for root in _tool_path_roots():
        if resolved == root:
            return resolved
        try:
            common = os.path.commonpath([resolved, root])
        except ValueError:
            continue
        if common == root:
            return resolved
    raise ValueError(
        f"path '{raw_path}' is outside the allowed roots"
    )

# Bash + python tools used to share a single 60s timeout. That's
# enough for one-shot commands but starves real workloads (pip
# install, ffmpeg conversions, etc.) — and worse, the agent saw the
# 60s timeout and went silent because it had nothing to report.
# The new default is intentionally generous: long enough that real
# work isn't killed mid-flight, but bounded so a runaway process
# (infinite loop, hung connect, etc.) eventually frees the worker.
# The user can cancel sooner via the chat stop button — when the
# SSE stream is torn down, the asyncio task running the subprocess
# gets cancelled and the subprocess is killed by the finally block.
DEFAULT_BASH_TIMEOUT = 60 * 60     # 1 hour
DEFAULT_PYTHON_TIMEOUT = 60 * 60

# How often to push a progress event while a long-running subprocess
# is still in flight. The frontend cares about "alive" more than
# "every-byte" — 2s is the sweet spot.
PROGRESS_INTERVAL_S = 2.0
# Tail buffer size — we keep the most recent N lines of stdout +
# stderr so the progress event includes a "what's it doing right now"
# snippet without dragging the whole output along.
PROGRESS_TAIL_LINES = 12


def get_mcp_manager():
    try:
        from src import agent_tools
        return agent_tools.get_mcp_manager()
    except ImportError as e:
        logger.warning("[core.tools.execution] get_mcp_manager: src.agent_tools not available (%s)", e)
        return None


def _truncate(text: str, limit: int = MAX_OUTPUT_CHARS) -> str:
    if len(text) > limit:
        return text[:limit] + f"\n... (truncated, {len(text)} chars total)"
    return text

logger = logging.getLogger(__name__)


async def _run_subprocess_streaming(
    proc: asyncio.subprocess.Process,
    *,
    timeout: float,
    progress_cb: Callable[[dict], Awaitable[None]] | None = None,
) -> tuple[str, str, int | None, bool]:
    """Run a subprocess to completion, streaming progress.

    Reads stdout + stderr line-by-line into ring buffers so a
    periodic progress callback can emit a "tail" of recent output
    without waiting for the full result. Returns
    (full_stdout, full_stderr, return_code, timed_out).

    `timed_out=True` means the process was killed because it ran
    past `timeout` seconds. Whatever output we'd buffered up to
    that point is still returned.
    """
    started = time.time()
    stdout_full: list[str] = []
    stderr_full: list[str] = []
    tail = collections.deque(maxlen=PROGRESS_TAIL_LINES)

    async def _reader(stream, full_buf, label: str):
        if stream is None:
            return
        while True:
            line = await stream.readline()
            if not line:
                break
            decoded = line.decode("utf-8", errors="replace").rstrip("\n")
            full_buf.append(decoded)
            if label == "err":
                tail.append(f"! {decoded}")
            else:
                tail.append(decoded)

    async def _progress_emitter():
        # Skip the first push — many commands finish well under
        # PROGRESS_INTERVAL_S and a 0-second "progress" event would
        # just add UI churn.
        await asyncio.sleep(PROGRESS_INTERVAL_S)
        while True:
            if progress_cb:
                try:
                    await progress_cb({
                        "elapsed_s": round(time.time() - started, 1),
                        "tail": "\n".join(list(tail)),
                    })
                except Exception as _e:
                    logger.debug("progress callback failed: %s", _e)
            await asyncio.sleep(PROGRESS_INTERVAL_S)

    rd_out = asyncio.create_task(_reader(proc.stdout, stdout_full, "out"))
    rd_err = asyncio.create_task(_reader(proc.stderr, stderr_full, "err"))
    prog_task = asyncio.create_task(_progress_emitter()) if progress_cb else None

    timed_out = False
    try:
        await asyncio.wait_for(proc.wait(), timeout=timeout)
    except TimeoutError:
        timed_out = True
        try:
            proc.kill()
        except Exception as _e:
            logger.debug("kill on timeout failed: %s", _e)
        try:
            await asyncio.wait_for(proc.wait(), timeout=2)
        except Exception as _e:
            logger.debug("wait after kill on timeout failed: %s", _e)
    except asyncio.CancelledError:
        # User hit stop / SSE stream torn down. Kill the child so it
        # doesn't keep running orphaned. Re-raise so the agent loop's
        # cancellation propagates as the user expects.
        try:
            proc.kill()
        except Exception as _e:
            logger.debug("kill on cancel failed: %s", _e)
        try:
            await asyncio.wait_for(proc.wait(), timeout=2)
        except Exception as _e:
            logger.debug("wait after kill on cancel failed: %s", _e)
        # Best-effort: stop the readers + emitter before re-raising.
        for t in (rd_out, rd_err):
            t.cancel()
        if prog_task is not None:
            prog_task.cancel()
        raise
    finally:
        if prog_task is not None and not prog_task.done():
            prog_task.cancel()
            try:
                await prog_task
            except (asyncio.CancelledError, Exception):
                pass
        # Wait for readers to finish draining the pipes.
        for t in (rd_out, rd_err):
            try:
                await asyncio.wait_for(t, timeout=1)
            except Exception as _e:
                logger.debug("reader drain cancelled: %s", _e)

    return (
        "\n".join(stdout_full),
        "\n".join(stderr_full),
        proc.returncode,
        timed_out,
    )

_ADMIN_TOOLS = {
    "app_api",
    "manage_endpoints",
    "manage_mcp",
    "manage_webhooks",
    "manage_tokens",
    "manage_settings",
    "download_model",
    "serve_model",
    "serve_preset",
    "stop_served_model",
    "cancel_download",
    "browser_evaluate",
}


def _owner_is_admin(owner: str | None) -> bool:
    """Mirror route-level admin behavior for agent tool execution."""
    return owner_is_admin_or_single_user(owner)

# ---------------------------------------------------------------------------
# MCP-backed tool helpers
# ---------------------------------------------------------------------------

# Map legacy tool names -> (MCP server_id, MCP tool_name)
_MCP_TOOL_MAP = {
    "bash":           ("bash",       "bash"),
    "python":         ("python",     "python"),
    "read_file":      ("filesystem", "read_file"),
    "write_file":     ("filesystem", "write_file"),
    "append_file":    ("filesystem", "append_file"),
    "delete_file":    ("filesystem", "delete_file"),
    "list_folder":    ("filesystem", "list_folder"),
    "web_search":     ("web_search", "web_search"),
    "web_fetch":      ("web_fetch",  "web_fetch"),
    "generate_image": ("image_gen",  "generate_image"),
}


def _parse_generate_image(content: str) -> dict:
    lines = content.strip().split("\n")
    args = {"prompt": lines[0].strip() if lines else ""}
    for i, key in enumerate(["model", "size", "quality"], 1):
        if len(lines) > i and lines[i].strip():
            args[key] = lines[i].strip()
    return args


def _parse_manage_memory(content: str) -> dict:
    lines = content.strip().split("\n")
    action = lines[0].strip().lower() if lines else ""
    args = {"action": action}
    if action == "add":
        args["text"] = lines[1].strip() if len(lines) > 1 else ""
        if len(lines) > 2 and lines[2].strip():
            args["category"] = lines[2].strip().lower()
    elif action == "edit":
        args["memory_id"] = lines[1].strip() if len(lines) > 1 else ""
        args["text"] = lines[2].strip() if len(lines) > 2 else ""
    elif action == "delete":
        args["memory_id"] = lines[1].strip() if len(lines) > 1 else ""
    elif action == "search":
        args["text"] = lines[1].strip() if len(lines) > 1 else ""
    elif action == "list":
        if len(lines) > 1 and lines[1].strip():
            args["category"] = lines[1].strip().lower()
    return args


def _parse_write_file(content: str) -> dict:
    lines = content.split("\n", 1)
    return {"path": lines[0].strip(), "content": lines[1] if len(lines) > 1 else ""}


def _parse_append_file(content: str) -> dict:
    lines = content.split("\n", 1)
    return {"path": lines[0].strip(), "content": lines[1] if len(lines) > 1 else ""}


def _parse_delete_file(content: str) -> dict:
    return {"path": content.split("\n")[0].strip()}


def _parse_list_folder(content: str) -> dict:
    return {"path": content.split("\n")[0].strip()}


_MCP_ARG_PARSERS: dict[str, callable] = {
    "bash":           lambda c: {"command": c},
    "python":         lambda c: {"code": c},
    "web_search":     lambda c: {"query": c.split("\n")[0].strip()},
    "web_fetch":      lambda c: {"url": c.split("\n")[0].strip()},
    "read_file":      lambda c: {"path": c.split("\n")[0].strip()},
    "write_file":     _parse_write_file,
    "append_file":    _parse_append_file,
    "delete_file":    _parse_delete_file,
    "list_folder":    _parse_list_folder,
    "generate_image": _parse_generate_image,
    "manage_memory":  _parse_manage_memory,
}


def _build_mcp_args(tool: str, content: str) -> dict:
    """Convert fenced-block text content to structured MCP arguments."""
    parser = _MCP_ARG_PARSERS.get(tool)
    return parser(content) if parser else {}


async def _call_mcp_tool(
    tool: str,
    content: str,
    progress_cb: Callable[[dict], Awaitable[None]] | None = None,
    session_id: str | None = None,
) -> dict:
    """Route a legacy tool call through the MCP manager, with direct fallbacks."""
    mcp = get_mcp_manager()
    if not mcp:
        return await _direct_fallback(tool, content, progress_cb=progress_cb, session_id=session_id) or {"error": f"MCP manager not available for tool '{tool}'", "exit_code": 1}

    server_id, tool_name = _MCP_TOOL_MAP[tool]
    qualified = f"mcp__{server_id}__{tool_name}"
    args = _build_mcp_args(tool, content)
    result = await mcp.call_tool(qualified, args)

    # If MCP server not connected, try direct fallback
    if isinstance(result, dict) and result.get("exit_code") == 1 and "not connected" in result.get("error", ""):
        fallback = await _direct_fallback(tool, content, progress_cb=progress_cb, session_id=session_id)
        if fallback:
            return fallback

    return result


_BG_MARKERS = {"#!bg", "#bg", "# bg", "#background", "# background", "@background", "# @background"}


def _split_bg_marker(content: str):
    """If the bash content's first non-empty line is a background marker
    (e.g. `#!bg`), return (True, command_without_marker); else (False, content)."""
    lines = content.split("\n")
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i < len(lines) and lines[i].strip().lower() in _BG_MARKERS:
        del lines[i]
        return True, "\n".join(lines).strip()
    return False, content


async def _direct_fallback(
    tool: str,
    content: str,
    progress_cb: Callable[[dict], Awaitable[None]] | None = None,
    session_id: str | None = None,
) -> dict | None:
    """In-process execution path for the eight tools that used to live as
    stdio MCP servers under mcp_servers/. Those servers were deleted in
    favor of native execution; this function is now the canonical path,
    not a fallback. The name is kept for backwards compat with callers.

    `progress_cb` is called periodically while bash/python subprocesses
    are still running, with `{elapsed_s, tail}` payloads. Other tools
    ignore it.
    """
    import json as _json

    # Inherit env + force a sane terminal so subprocesses that touch
    # terminfo (anything calling `clear`, `tput`, `os.system("clear")`,
    # or scripts that probe $TERM) don't spam "TERM environment variable
    # not set" errors. The agent's bash/python tool calls run with PIPE
    # stdin/stdout (no real TTY), so curses/termios still won't work —
    # but at least non-interactive code with incidental TERM lookups
    # stops failing. COLUMNS/LINES give terminal-width-aware tools (less,
    # rich, etc.) reasonable defaults instead of 0×0.
    _subproc_env = {
        **os.environ,
        "TERM": "xterm-256color",
        "COLUMNS": "120",
        "LINES": "40",
    }

    try:
        if tool == "bash":
            # Phase 7: Sandbox execution if enabled
            if jarvis_config.sandbox.enabled:
                if _docker_sandbox.available:
                    res = await _docker_sandbox.exec_bash(content, timeout=DEFAULT_BASH_TIMEOUT)
                    if res["success"]:
                        return {"output": res["stdout"].rstrip() or "(no output)", "exit_code": res["exit_code"]}
                    return {"error": res.get("error", "bash command failed"), "exit_code": 1}
                from core.sandbox.sandbox_manager import sandbox_manager
                res = await sandbox_manager.exec(session_id or "default", tool, [content])
                if res["success"]:
                    output = res["stdout"].rstrip()
                    return {"output": output or "(no output)", "exit_code": res["exit_code"]}
                else:
                    return {"error": res["error"], "exit_code": 1}

            # Platform-aware subprocess fallback (no sandbox / sandbox unavailable)
            if sys.platform == "win32":
                proc = await asyncio.create_subprocess_exec(
                    "cmd", "/c", content,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=_subproc_env,
                )
            else:
                proc = await asyncio.create_subprocess_exec(
                    "/bin/sh", "-c", content,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=_subproc_env,
                )
            stdout, stderr, rc, timed_out = await _run_subprocess_streaming(
                proc,
                timeout=DEFAULT_BASH_TIMEOUT,
                progress_cb=progress_cb,
            )
            if timed_out:
                return {"error": f"bash: timed out after {DEFAULT_BASH_TIMEOUT}s — process killed", "exit_code": 124, "stdout": _truncate(stdout, MAX_OUTPUT_CHARS), "stderr": _truncate(stderr, MAX_OUTPUT_CHARS)}
            output = stdout.rstrip()
            err = stderr.rstrip()
            if err:
                output = (output + "\nSTDERR: " + err).strip() if output else "STDERR: " + err
            output = _truncate(output, MAX_OUTPUT_CHARS)
            return {"output": output or "(no output)", "exit_code": rc or 0}

        if tool == "python":
            # Phase 7: Sandbox execution if enabled
            from core.sandbox.sandbox_manager import sandbox_manager
            if jarvis_config.sandbox.enabled:
                res = await sandbox_manager.exec(session_id or "default", tool, ["python", "-c", content])
                if res["success"]:
                    output = res["stdout"].rstrip()
                    return {"output": output or "(no output)", "exit_code": res["exit_code"]}
                else:
                    return {"error": res["error"], "exit_code": 1}

            # Run user code in a subprocess so an infinite loop or crash
            # can't take the whole server down. -I = isolated mode (skip
            # user site, no PYTHONPATH inheritance) for hygiene.
            proc = await asyncio.create_subprocess_exec(
                # Use the running interpreter — there is no `python3.exe` on
                # Windows, which made the agent's `python` tool fail there.
                (sys.executable or "python"), "-I", "-c", content,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=_subproc_env,
            )
            stdout, stderr, rc, timed_out = await _run_subprocess_streaming(
                proc,
                timeout=DEFAULT_PYTHON_TIMEOUT,
                progress_cb=progress_cb,
            )
            if timed_out:
                return {"error": f"python: timed out after {DEFAULT_PYTHON_TIMEOUT}s — process killed", "exit_code": 124, "stdout": _truncate(stdout, MAX_OUTPUT_CHARS), "stderr": _truncate(stderr, MAX_OUTPUT_CHARS)}
            output = stdout.rstrip()
            err = stderr.rstrip()
            if err:
                output = (output + "\nSTDERR: " + err).strip() if output else "STDERR: " + err
            output = _truncate(output, MAX_OUTPUT_CHARS)
            return {"output": output or "(no output)", "exit_code": rc or 0}

        if tool == "read_file":
            raw_path = content.split("\n", 1)[0].strip()

            # Track hot file
            try:
                from core.tools.hot_files import touch_file
                base = raw_path.split(":")[0] if ":" in raw_path else raw_path
                touch_file(base, session_id=session_id or "default")
            except Exception as e:
                logger.warning("[core.tools.execution] execute_tool failed: %s", e)

            # Parse optional line range from path (e.g. foo.py:10-30 or foo.py:20)
            line_start = None
            line_count = None
            if ":" in raw_path:
                base, _, spec = raw_path.partition(":")
                try:
                    if "-" in spec:
                        parts = spec.split("-", 1)
                        line_start = int(parts[0])
                        end = int(parts[1])
                        line_count = end - line_start + 1
                    else:
                        line_start = int(spec)
                        line_count = 1
                    raw_path = base
                except (ValueError, TypeError) as _e:
                    logger.debug("[core.tools.execution] parse line range failed: %s", _e)

            try:
                path = _resolve_tool_path(raw_path)
            except ValueError as e:
                return {"error": f"read_file: {e}", "exit_code": 1}
            try:
                def _read():
                    with open(path, encoding="utf-8", errors="replace") as f:
                        return f.read(MAX_READ_CHARS + 1)
                data = await asyncio.to_thread(_read)
            except FileNotFoundError:
                return {"error": f"read_file: {path}: not found", "exit_code": 1}
            except PermissionError:
                return {"error": f"read_file: {path}: permission denied", "exit_code": 1}
            except OSError as e:
                return {"error": f"read_file: {path}: {e}", "exit_code": 1}

            lines = data.split("\n")
            if line_start is not None:
                line_idx = max(0, line_start - 1)
                if line_count is not None:
                    selected = lines[line_idx:line_idx + line_count]
                else:
                    selected = lines[line_idx:]
                lines = selected
                data = "\n".join(lines)

            # Add line numbers
            line_num_start = line_start if line_start is not None else 1
            numbered_lines = [f"{line_num_start + i:4d}: {line}" for i, line in enumerate(lines)]
            output = "\n".join(numbered_lines)

            truncated = len(data) > MAX_READ_CHARS
            if truncated:
                output = output[:MAX_READ_CHARS] + f"\n... [truncated at {MAX_READ_CHARS} chars]"
            return {"output": output, "exit_code": 0}

        if tool == "write_file":
            lines = content.split("\n", 1)
            raw_path = lines[0].strip()
            body = lines[1] if len(lines) > 1 else ""
            try:
                path = _resolve_tool_path(raw_path)
            except ValueError as e:
                return {"error": f"write_file: {e}", "exit_code": 1}
            try:
                def _write():
                    d = os.path.dirname(path)
                    if d:
                        os.makedirs(d, exist_ok=True)
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(body)
                    return len(body)
                size = await asyncio.to_thread(_write)
            except PermissionError:
                return {"error": f"write_file: {path}: permission denied", "exit_code": 1}
            except OSError as e:
                return {"error": f"write_file: {path}: {e}", "exit_code": 1}
            # Track hot file
            try:
                from core.tools.hot_files import touch_file
                touch_file(str(path), session_id=session_id or "default")
            except Exception as e:
                logger.warning("[core.tools.execution] process_tool_result failed: %s", e)
            return {"output": f"Wrote {size} bytes to {path}", "exit_code": 0}

        if tool == "append_file":
            lines = content.split("\n", 1)
            raw_path = lines[0].strip()
            body = lines[1] if len(lines) > 1 else ""
            try:
                path = _resolve_tool_path(raw_path)
            except ValueError as e:
                return {"error": f"append_file: {e}", "exit_code": 1}
            try:
                def _append():
                    d = os.path.dirname(path)
                    if d:
                        os.makedirs(d, exist_ok=True)
                    with open(path, "a", encoding="utf-8") as f:
                        f.write(body)
                    return len(body)
                size = await asyncio.to_thread(_append)
            except PermissionError:
                return {"error": f"append_file: {path}: permission denied", "exit_code": 1}
            except OSError as e:
                return {"error": f"append_file: {path}: {e}", "exit_code": 1}
            return {"output": f"Appended {size} bytes to {path}", "exit_code": 0}

        if tool == "delete_file":
            raw_path = content.split("\n", 1)[0].strip()
            try:
                path = _resolve_tool_path(raw_path)
            except ValueError as e:
                return {"error": f"delete_file: {e}", "exit_code": 1}
            try:
                def _delete():
                    if os.path.isfile(path):
                        os.remove(path)
                        return True
                    return False
                deleted = await asyncio.to_thread(_delete)
            except PermissionError:
                return {"error": f"delete_file: {path}: permission denied", "exit_code": 1}
            except OSError as e:
                return {"error": f"delete_file: {path}: {e}", "exit_code": 1}
            if deleted:
                return {"output": f"Deleted {path}", "exit_code": 0}
            return {"error": f"delete_file: {path}: not found", "exit_code": 1}

        if tool == "list_folder":
            raw_path = content.split("\n", 1)[0].strip()
            try:
                path = _resolve_tool_path(raw_path)
            except ValueError as e:
                return {"error": f"list_folder: {e}", "exit_code": 1}
            try:
                def _list():
                    if not os.path.isdir(path):
                        return None
                    entries = []
                    for entry in sorted(os.listdir(path)):
                        full = os.path.join(path, entry)
                        size = os.path.getsize(full) if os.path.isfile(full) else 0
                        mtime = os.path.getmtime(full)
                        kind = "file" if os.path.isfile(full) else "dir"
                        entries.append({"name": entry, "kind": kind, "size": size, "mtime": mtime})
                    return entries
                entries = await asyncio.to_thread(_list)
            except PermissionError:
                return {"error": f"list_folder: {path}: permission denied", "exit_code": 1}
            except OSError as e:
                return {"error": f"list_folder: {path}: {e}", "exit_code": 1}
            if entries is None:
                return {"error": f"list_folder: {path}: not found", "exit_code": 1}
            return {"output": entries, "exit_code": 0}

        if tool == "web_search":
            try:
                from src.search import comprehensive_web_search
            except ImportError as e:
                logger.warning("[core.tools.execution] web_search: src.search not available (%s)", e)
                return {"error": "web_search module not available", "exit_code": 1}
            raw = content.strip()
            query = raw
            time_filter = None
            max_pages = 5
            # Allow JSON-shaped args: {"query": "...", "time_filter": "day", "max_pages": 7}
            if raw.startswith("{"):
                try:
                    parsed = _json.loads(raw)
                    if isinstance(parsed, dict) and "query" in parsed:
                        query = str(parsed.get("query", "")).strip()
                        tf = parsed.get("time_filter") or parsed.get("freshness")
                        if isinstance(tf, str) and tf.lower() in ("day", "week", "month", "year"):
                            time_filter = tf.lower()
                        mp = parsed.get("max_pages")
                        if isinstance(mp, int) and 1 <= mp <= 10:
                            max_pages = mp
                except _json.JSONDecodeError as _e:
                    logger.debug("[core.tools.execution] web_search extra config JSON parse failed: %s", _e)
            if not query:
                query = raw.split("\n")[0].strip()
            # Auto-detect freshness from query phrasing when not explicit
            if time_filter is None:
                q_lc = query.lower()
                if any(kw in q_lc for kw in ("today", "latest", "breaking", "this morning", "right now", "currently")):
                    time_filter = "day"
                elif any(kw in q_lc for kw in ("this week", "past week", "recent news", "last few days")):
                    time_filter = "week"
                elif any(kw in q_lc for kw in ("this month", "past month")):
                    time_filter = "month"
                elif " news" in q_lc or q_lc.startswith("news ") or q_lc.endswith(" news"):
                    time_filter = "week"
            loop = asyncio.get_running_loop()
            text, sources = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: comprehensive_web_search(
                        query,
                        max_pages=max_pages,
                        time_filter=time_filter,
                        return_sources=True,
                    ),
                ),
                timeout=30,
            )
            output = text[:MAX_OUTPUT_CHARS] if len(text) > MAX_OUTPUT_CHARS else text
            if sources:
                output += "\n\n<!-- SOURCES:" + _json.dumps(sources) + " -->"
            return {"output": output, "exit_code": 0}

        if tool == "web_fetch":
            # Lightweight single-URL fetch. Wraps the SSRF-safe fetcher used
            # by deep research, so private/loopback/metadata addresses are
            # already blocked there.
            try:
                from src.search.content import fetch_webpage_content
            except ImportError as e:
                logger.warning("[core.tools.execution] web_fetch: src.search.content not available (%s)", e)
                return {"error": "web_fetch module not available", "exit_code": 1}
            raw = content.strip()
            url = ""
            # Accept either a JSON arg ({"url": "..."}) or a plain URL/domain.
            if raw.startswith("{"):
                try:
                    parsed = _json.loads(raw)
                    if isinstance(parsed, dict):
                        url = str(parsed.get("url") or "").strip()
                except _json.JSONDecodeError:
                    url = ""
            if not url:
                # Non-JSON (or JSON without a usable url): take the first line
                # only, so a URL followed by commentary still parses.
                url = raw.split("\n")[0].strip()
            # Reject anything that isn't a single bare URL/domain token.
            if not url or url.startswith("{") or any(c in url for c in (" ", "\t", "\n")):
                return {"error": "web_fetch: provide a single URL or domain, e.g. example.com", "exit_code": 1}
            low = url.lower()
            if "://" in low and not low.startswith(("http://", "https://")):
                return {"error": f"web_fetch: unsupported URL scheme (only http/https): {url[:80]}", "exit_code": 1}
            # Accept bare domains like "example.com" by defaulting to https.
            if not low.startswith(("http://", "https://")):
                url = "https://" + url
            loop = asyncio.get_running_loop()
            try:
                result = await asyncio.wait_for(
                    loop.run_in_executor(None, lambda: fetch_webpage_content(url, timeout=10)),
                    timeout=30,
                )
            except TimeoutError:
                return {"error": f"web_fetch: timed out fetching {url}", "exit_code": 1}
            except Exception as e:
                # Direct URL fetches can hit bot protection / auth walls
                # (e.g. eBay 403). Treat that as a tool failure the model can
                # reason around, not an uncaught chat-stream 500.
                return {"error": f"web_fetch: {url}: {e}", "exit_code": 1}
            err = result.get("error")
            text = (result.get("content") or "").strip()
            title = result.get("title") or ""

            if not text:
                if err:
                    return {"error": f"web_fetch: {url}: {err}", "exit_code": 1}
                # No extractable text: non-HTML body, or a pure client-rendered
                # shell. The agent can fall back to the builtin_browser tool.
                return {"error": f"web_fetch: {url}: no readable text content (not HTML, or the page needs JS/login)", "exit_code": 1}

            header = (f"# {title}\n" if title else "") + f"Source: {url}\n\n"
            output = header + text
            if len(output) > MAX_OUTPUT_CHARS:
                output = output[:MAX_OUTPUT_CHARS] + "\n\n[...truncated]"
            return {"output": output, "exit_code": 0}

        # manage_memory / generate_image still live as MCP servers
        # (mcp_servers/{memory,image_gen}_server.py); the MCP path above
        # handles them.
    except Exception as e:
        return {"error": f"{tool}: {e}", "exit_code": 1}

    return None


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

# ── Direct filesystem edit tool (bypasses document DB) ────────────────

_BACKUP_DIR = None


def _get_backup_dir() -> str:
    global _BACKUP_DIR
    if _BACKUP_DIR is None:
        from core.constants import DATA_DIR
        _BACKUP_DIR = os.path.join(str(DATA_DIR), "file_backups")
        os.makedirs(_BACKUP_DIR, exist_ok=True)
    return _BACKUP_DIR


async def do_edit_file(content: str, owner: str | None = None) -> dict:
    """Edit a file on the filesystem directly.

    Content format:
        Line 1: file path (relative to workspace or absolute)
        Then: FIND/REPLACE blocks or unified diff

    Creates a backup before editing. Verifies Python files with compile().
    Auto-formats Python/JS/TS files. Generates a diff preview. Suggests tests.
    """
    import difflib

    from core.tools.document_tools import (
        _apply_edit_to_text,
        _apply_unified_diff,
        _normalize_text,
        parse_edit_blocks,
    )

    lines = content.split("\n", 1)
    first_line = lines[0].strip()

    if first_line.startswith("--- "):
        edit_content = content
        diff_match = re.search(r"--- a/(.+)", edit_content)
        raw_path = diff_match.group(1).split("\t")[0] if diff_match else None
        if not raw_path:
            return {"error": "Cannot determine file path from unified diff", "exit_code": 1}
        try:
            file_path = _resolve_tool_path(raw_path)
        except ValueError as e:
            return {"error": str(e), "exit_code": 1}
    else:
        file_path = first_line
        if not file_path:
            return {"error": "No file path provided", "exit_code": 1}
        edit_content = lines[1] if len(lines) > 1 else ""

    try:
        resolved = _resolve_tool_path(file_path)
    except ValueError as e:
        return {"error": str(e), "exit_code": 1}
    path = Path(resolved)

    if not path.exists():
        return {"error": f"File not found: {path}", "exit_code": 1}
    if not path.is_file():
        return {"error": f"Not a file: {path}", "exit_code": 1}

    try:
        original = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return {"error": f"Cannot read {path}: {e}", "exit_code": 1}

    stripped = edit_content.strip()
    if stripped.startswith("--- "):
        new_text, err = _apply_unified_diff(original, stripped)
        if new_text is None:
            return {"error": f"Unified diff failed: {err}", "exit_code": 1}
        applied = 1
        failed = 0
        details = [{"status": "ok", "match": "diff"}]
    else:
        edits = parse_edit_blocks(edit_content)
        if not edits:
            return {"error": "No FIND/REPLACE blocks or unified diff found", "exit_code": 1}
        current = _normalize_text(original)
        applied = 0
        failed = 0
        details = []
        for ed in edits:
            new_text_part, detail = _apply_edit_to_text(current, ed)
            if new_text_part is None:
                details.append(detail)
                failed += 1
            else:
                current = new_text_part
                details.append(detail)
                applied += 1
        if applied == 0:
            return {"error": "No edits matched file content", "details": details, "exit_code": 1}
        new_text = current

    if new_text == original:
        return {"error": "No changes — edited content matches original", "exit_code": 1}

    # Generate diff preview
    diff_lines = list(difflib.unified_diff(
        original.splitlines(keepends=True),
        new_text.splitlines(keepends=True),
        fromfile=f"a/{path.name}",
        tofile=f"b/{path.name}",
    ))
    diff_text = "".join(diff_lines)

    # Create backup
    try:
        backup_dir = _get_backup_dir()
        import hashlib
        backup_name = f"{path.name}.{hashlib.md5(str(path).encode()).hexdigest()[:8]}.bak"
        backup_path = os.path.join(backup_dir, backup_name)
        with open(backup_path, "w", encoding="utf-8") as fh:
            fh.write(original)
    except Exception as e:
        logger.warning("backup failed for %s: %s", path, e)

    # Write new content
    try:
        path.write_text(new_text, encoding="utf-8")
    except Exception as e:
        return {"error": f"Cannot write {path}: {e}", "exit_code": 1}

    # Auto-format with ruff for Python, prettier for JS/TS
    format_result = None
    try:
        if path.suffix == ".py":
            proc = await asyncio.create_subprocess_exec(
                "ruff", "format", str(path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            if proc.returncode == 0:
                format_result = "ruff format"
            elif stderr:
                logger.debug("ruff format failed: %s", stderr.decode("utf-8", errors="replace")[:200])
        elif path.suffix in (".js", ".ts", ".tsx", ".jsx", ".css", ".json", ".md"):
            proc = await asyncio.create_subprocess_exec(
                "npx", "prettier", "--write", str(path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            if proc.returncode == 0:
                format_result = "prettier"
            elif stderr:
                logger.debug("prettier format failed: %s", stderr.decode("utf-8", errors="replace")[:200])
    except Exception as e:
        logger.debug("auto-format skipped: %s", e)

    # Verify (parse .py files with ast for safety)
    verify_note = ""
    if path.suffix == ".py":
        try:
            import ast
            ast.parse(new_text, filename=str(path))
        except SyntaxError as se:
            verify_note = f"⚠ SyntaxError: {se}"
            details.append({"status": "verify", "note": verify_note})

    # Suggest related tests
    test_suggestions = []
    try:
        base = path.stem
        parent = path.parent
        test_patterns = [
            parent / f"test_{path.name}",
            parent / f"test_{base}.py",
            parent.parent / "tests" / f"test_{base}.py",
            parent.parent / "tests" / f"test_{path.name}",
            Path.cwd() / "tests" / f"test_{base}.py",
        ]
        for tp in test_patterns:
            if tp.exists():
                test_suggestions.append(str(tp.relative_to(Path.cwd())))
    except Exception as e:
        logger.warning("[core.tools.execution] handle_parallel_execution failed: %s", e)

    rel_path = str(path.relative_to(Path.cwd())) if path.is_relative_to(Path.cwd()) else str(path)
    # Track hot file for live context
    try:
        from core.tools.hot_files import touch_file
        touch_file(rel_path)
    except Exception as e:
        logger.warning("[core.tools.execution] handle_parallel_execution failed: %s", e)

    return {
        "action": "edit_file",
        "path": rel_path,
        "applied": applied,
        "failed": failed,
        "size": len(new_text),
        "diff": diff_text,
        "format": format_result,
        "verify": verify_note or None,
        "test_suggestions": test_suggestions or None,
        "details": details,
    }


async def do_refactor(content: str, owner: str | None = None) -> dict:
    """Decompose a high-level refactoring goal into steps and execute them.

    Content format:
        Line 1: goal description
        Line 2: comma-separated file paths
        Then: optional FIND/REPLACE blocks (if model provides specific edits)

    Falls back to generating the steps from the goal if no specific edits given.
    """
    from core.codebase_indexer import search_codebase

    lines = content.split("\n", 2)
    goal = lines[0].strip()
    if len(lines) > 1:
        file_list = [f.strip() for f in lines[1].split(",") if f.strip()]
    else:
        file_list = []
    edit_blocks = lines[2] if len(lines) > 2 else ""

    if not goal:
        return {"error": "No refactoring goal provided", "exit_code": 1}

    # If the model provided specific edits, apply them directly
    if edit_blocks.strip():
        from core.tools.document_tools import _apply_edit_to_text, _normalize_text, parse_edit_blocks
        edits = parse_edit_blocks(edit_blocks)
        if edits and file_list:
            results = []
            for fp_str in file_list:
                fp = Path(fp_str.strip())
                if not fp.is_absolute():
                    fp = Path.cwd() / fp
                try:
                    _resolve_tool_path(str(fp))
                except ValueError as e:
                    results.append({"file": fp_str, "error": f"path blocked: {e}"})
                    continue
                if not fp.exists():
                    results.append({"file": fp_str, "error": "not found"})
                    continue
                try:
                    original = fp.read_text(encoding="utf-8")
                except Exception as e:
                    results.append({"file": fp_str, "error": str(e)})
                    continue
                current = _normalize_text(original)
                applied = 0
                for ed in edits:
                    new_text, _ = _apply_edit_to_text(current, ed)
                    if new_text is not None:
                        current = new_text
                        applied += 1
                if applied > 0:
                    fp.write_text(current, encoding="utf-8")
                    results.append({"file": fp_str, "applied": applied})
                else:
                    results.append({"file": fp_str, "applied": 0})
            return {
                "action": "refactor",
                "goal": goal,
                "results": results,
                "total_files": len(results),
            }

    # No specific edits — use semantic search to find relevant files,
    # then generate a plan as a suggestion for the model
    if not file_list:
        results = search_codebase(goal, k=5, owner=owner)
        search_hits = results.count("\n# ") if results else 0
    else:
        search_hits = len(file_list)

    plan_steps = _generate_refactor_plan(goal, file_list)
    return {
        "action": "refactor",
        "goal": goal,
        "plan": plan_steps,
        "search_hits": search_hits,
        "note": "Use the plan steps above to guide your edits. Call edit_file or batch_edit_file for each step.",
        "exit_code": 0,
    }


def _generate_refactor_plan(goal: str, files: list[str]) -> list[dict]:
    """Generate a step-by-step refactoring plan from a high-level goal."""
    plan = [{"step": 1, "action": "Understand current code", "detail": f"Read the relevant files to understand current structure: {', '.join(files) if files else '(use semantic_search to find them)'}"},
            {"step": 2, "action": "Make the changes", "detail": "Use edit_file or batch_edit_file for each change"},
            {"step": 3, "action": "Verify", "detail": "Run tests to verify the changes work"}]
    return plan


async def do_undo_edit_file(path_str: str) -> dict:
    """Restore the most recent backup of a file."""
    path = Path(path_str)
    if not path.is_absolute():
        path = Path.cwd() / path
    path = path.resolve()
    try:
        _resolve_tool_path(str(path))
    except ValueError as e:
        return {"error": f"path blocked: {e}", "exit_code": 1}

    backup_dir = _get_backup_dir()
    import hashlib
    prefix = f"{path.name}.{hashlib.md5(str(path).encode()).hexdigest()[:8]}."
    backups = sorted(
        [f for f in os.listdir(backup_dir) if f.startswith(prefix)],
        key=lambda f: os.path.getmtime(os.path.join(backup_dir, f)),
        reverse=True,
    )
    if not backups:
        return {"error": f"No backups found for {path.name}", "exit_code": 1}

    latest = os.path.join(backup_dir, backups[0])
    try:
        with open(latest, encoding="utf-8") as fh:
            restored = fh.read()
        path.write_text(restored, encoding="utf-8")
        rel = str(path.relative_to(Path.cwd())) if path.is_relative_to(Path.cwd()) else str(path)
        return {"action": "undo_edit_file", "path": rel, "size": len(restored), "exit_code": 0}
    except Exception as e:
        return {"error": f"Undo failed: {e}", "exit_code": 1}


async def do_batch_edit_file(content: str) -> dict:
    """Edit multiple files matching a glob pattern.

    Content format:
        Line 1: glob pattern
        Then: FIND/REPLACE blocks
    """
    from core.tools.document_tools import _apply_edit_to_text, _normalize_text, parse_edit_blocks

    lines = content.split("\n", 1)
    pattern = lines[0].strip()
    edit_blocks = lines[1] if len(lines) > 1 else ""
    if not pattern or not edit_blocks:
        return {"error": "Usage: <glob_pattern>\\n<FIND/REPLACE blocks>", "exit_code": 1}

    edits = parse_edit_blocks(edit_blocks)
    if not edits:
        return {"error": "No FIND/REPLACE blocks found", "exit_code": 1}

    matched = list(Path.cwd().glob(pattern))
    if not matched:
        return {"error": f"No files matching '{pattern}'", "exit_code": 1}

    results = []
    total_applied = 0
    total_failed = 0
    for fp in matched:
        try:
            _resolve_tool_path(str(fp))
        except ValueError as e:
            results.append({"path": str(fp), "error": f"path blocked: {e}"})
            total_failed += 1
            continue
        if not fp.is_file():
            continue
        try:
            original = fp.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            results.append({"path": str(fp), "error": str(e)})
            continue

        current = _normalize_text(original)
        applied = 0
        failed = 0
        file_details = []
        for ed in edits:
            new_text_part, detail = _apply_edit_to_text(current, ed)
            if new_text_part is None:
                file_details.append(detail)
                failed += 1
            else:
                current = new_text_part
                file_details.append(detail)
                applied += 1

        if applied == 0:
            results.append({"path": str(fp), "applied": 0, "details": file_details})
            continue

        try:
            fp.write_text(current, encoding="utf-8")
        except Exception as e:
            results.append({"path": str(fp), "error": str(e)})
            continue

        total_applied += applied
        total_failed += failed
        results.append({"path": str(fp), "applied": applied, "failed": failed})

    return {
        "action": "batch_edit_file",
        "files_edited": len([r for r in results if r.get("applied", 0) > 0]),
        "total_applied": total_applied,
        "total_failed": total_failed,
        "results": results,
    }


# Browser artifact cache (module-level to persist across execute_tool_block calls)
_BROWSER_ARTIFACT_DIR: str | None = None

def _ensure_browser_artifact_dir(wf_id: str) -> str:
    global _BROWSER_ARTIFACT_DIR
    if _BROWSER_ARTIFACT_DIR is None:
        base = Path(__file__).resolve().parent.parent.parent / "data" / "workflow_artifacts"
        base.mkdir(parents=True, exist_ok=True)
        _BROWSER_ARTIFACT_DIR = str(base)
    wf_dir = os.path.join(_BROWSER_ARTIFACT_DIR, wf_id)
    os.makedirs(wf_dir, exist_ok=True)
    return wf_dir


def _resolve_artifact_attachments(attachments: list, ctx_any: Any) -> list:
    """Resolve artifact: prefixed attachment references to file paths."""
    from core.workflow.artifact_store import ArtifactStore
    from core.workflow.storage import WorkflowStore
    wf_id = getattr(ctx_any, "workflow_id", None)
    if wf_id is None:
        return attachments
    store_path = getattr(ctx_any, "metadata", {}).get("_store_path")
    store = WorkflowStore(store_path) if store_path else WorkflowStore()
    art_store = ArtifactStore(store)
    resolved = []
    for att in attachments:
        if isinstance(att, str) and att.startswith("artifact:"):
            art_id = att[len("artifact:"):].strip()
            ref = art_store.get_artifact(art_id)
            if ref is not None and os.path.isfile(ref.path):
                resolved.append(ref.path)
            else:
                resolved.append(att)
        else:
            resolved.append(att)
    return resolved


async def _register_email_artifact(result: dict, ctx_any: Any) -> dict[str, str]:
    """Register a sent email as an artifact."""
    from core.workflow.artifact_store import ArtifactStore
    from core.workflow.context import ContextManager
    from core.workflow.storage import WorkflowStore
    wf_id = getattr(ctx_any, "workflow_id", None)
    if wf_id is None:
        return {}
    store_path = getattr(ctx_any, "metadata", {}).get("_store_path")
    store = WorkflowStore(store_path) if store_path else WorkflowStore()
    art_store = ArtifactStore(store)
    artifacts: dict[str, str] = {}
    meta = {
        "to": result.get("to", ""),
        "subject": result.get("subject", ""),
        "message_id": result.get("message_id", ""),
        "sent_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    try:
        ref = art_store.register_artifact(
            workflow_id=wf_id,
            name=f"email_sent_{time.strftime('%Y%m%d_%H%M%S')}",
            artifact_type="email_sent",
            path="",
            metadata=meta,
        )
        artifacts["email_sent"] = ref.artifact_id
        cm = ContextManager(store)
        ctx = cm.get_context(wf_id)
        if ctx is not None:
            ctx.artifacts.update(artifacts)
            cm.update_context(ctx)
    except Exception:
        pass
    return artifacts


async def execute_tool_block(
    block: Any,
    session_id: str | None = None,
    disabled_tools: set | None = None,
    owner: str | None = None,
    progress_cb: Callable[[dict], Awaitable[None]] | None = None,
    context: Any | None = None,
) -> tuple[str, dict]:
    """Execute a single tool block via the centralized ActionEngine."""
    from core.action_engine import action_engine
    
    tool_type = block.tool_type
    content = block.content

    # Map core tool types to ActionEngine methods
    CORE_MAPPING = {
        "read_file": "read_file",
        "write_file": "write_file",
        "list_folder": "list_folder",
        "bash": "run_command",
        "shell": "run_command",
    }

    if tool_type in CORE_MAPPING:
        # Support both legacy fenced-code-block format (path\ncontent)
        # and JSON format ({"path":"...","content":"..."}) from engine steps
        params = {}
        import json as _json
        try:
            parsed = _json.loads(content)
            if isinstance(parsed, dict):
                if tool_type in ("read_file", "list_folder"):
                    params = {"path": parsed.get("path", parsed.get("file", ""))}
                elif tool_type == "write_file":
                    params = {"path": parsed.get("path", ""), "content": parsed.get("content", "")}
                else:  # bash/shell
                    params = {"command": parsed.get("command", parsed.get("code", content))}
        except (_json.JSONDecodeError, ValueError):
            if tool_type == "read_file":
                params = {"path": content.split("\n", 1)[0].strip()}
            elif tool_type == "write_file":
                lines = content.split("\n", 1)
                params = {"path": lines[0].strip(), "content": lines[1] if len(lines) > 1 else ""}
            elif tool_type == "list_folder":
                params = {"path": content.split("\n", 1)[0].strip()}
            else:  # bash/shell
                params = {"command": content}

        res = await action_engine.execute(CORE_MAPPING[tool_type], params, session_id=session_id)
        
        # Return description + result in legacy dict format for AgentState
        desc = f"{tool_type}: {params.get('path', params.get('command', ''))[:60]}"
        return desc, {
            "output": res["result"],
            "error": res["error"],
            "exit_code": 0 if res["success"] else 1
        }

    # If not a core tool, use existing dispatch implementations
    from core.tools.implementations import (
        do_adopt_served_model,
        do_api_call,
        do_app_api,
        do_browser_click,
        do_browser_close_tab,
        do_browser_current_state,
        do_browser_evaluate,
        do_browser_fill,
        do_browser_find,
        do_browser_find_interactive,
        do_browser_get_history,
        do_browser_get_title,
        do_browser_get_url,
        do_browser_health,
        do_browser_list_tabs,
        do_browser_navigate,
        do_browser_new_tab,
        do_browser_press,
        do_browser_screenshot,
        do_browser_shadow_query,
        do_browser_snapshot,
        do_browser_switch_tab,
        do_browser_wait_interactive,
        do_browser_wait_text,
        do_browser_wait_visible,
        do_cancel_download,
        do_create_document,
        do_create_skill,
        do_download_model,
        do_edit_document,
        do_edit_image,
        do_list_cached_models,
        do_list_cookbook_servers,
        do_list_downloads,
        do_list_serve_presets,
        do_list_served_models,
        do_manage_calendar,
        do_manage_contact,
        do_manage_documents,
        do_manage_endpoints,
        do_manage_mcp,
        do_manage_notes,
        do_manage_research,
        do_manage_settings,
        do_manage_skills,
        do_manage_tasks,
        do_manage_tokens,
        do_manage_webhooks,
        do_resolve_contact,
        do_search_chats,
        do_search_hf_models,
        do_serve_model,
        do_serve_preset,
        do_stop_served_model,
        do_suggest_document,
        do_trigger_research,
        do_update_document,
        do_vault_get,
        do_vault_search,
        do_vault_unlock,
        do_vision_browser,
    )

    _CHR = chr(10)

    async def _hdl_create_document(content, session_id=None, owner=None, **kw):
        title = content.split("\n")[0].strip()[:60]
        return f"create_document: {title}", await do_create_document(content, session_id=session_id, owner=owner)

    async def _hdl_update_document(content, session_id=None, owner=None, **kw):
        return f"update_document: {content.split(_CHR)[0][:60]}", await do_update_document(content, owner=owner)

    async def _hdl_edit_document(content, session_id=None, owner=None, **kw):
        r = await do_edit_document(content, owner=owner)
        return f"edit_document: {r.get('title', '')}", r

    async def _hdl_edit_file(content, session_id=None, owner=None, **kw):
        r = await do_edit_file(content, owner=owner)
        return f"edit_file: {r.get('path', '')}", r

    async def _hdl_undo_edit_file(content, session_id=None, owner=None, **kw):
        r = await do_undo_edit_file(content.strip())
        return f"undo_edit_file: {r.get('path', '')}", r

    async def _hdl_batch_edit_file(content, session_id=None, owner=None, **kw):
        r = await do_batch_edit_file(content)
        return f"batch_edit_file: {r.get('files_edited', 0)} files", r

    async def _hdl_refactor(content, session_id=None, owner=None, **kw):
        r = await do_refactor(content, owner=owner)
        return f"refactor: {r.get('goal', '')[:60]}", r

    async def _hdl_shell_command(content, session_id=None, owner=None, **kw):
        """Execute a command in a persistent shell session (preserves cwd, env).
        Prefix command with 'sandbox:' to run in Docker sandbox."""
        from core.tools.persistent_shell import get_or_create_shell
        raw = content.strip()
        use_sandbox = raw.startswith("sandbox:")
        if use_sandbox:
            raw = raw[len("sandbox:"):].strip()
        lines = raw.split("\n", 1)
        command = lines[0].strip()
        timeout_str = lines[1].strip() if len(lines) > 1 else ""
        timeout = float(timeout_str) if timeout_str else 60.0

        if use_sandbox:
            from core.sandbox.docker_sandbox import docker_sandbox
            r = await docker_sandbox.exec_bash(command, timeout=int(timeout))
            return f"shell[sandbox]: {command[:60]}", r

        sid = session_id or "default"
        shell = get_or_create_shell(sid)
        r = await shell.exec(command, timeout=timeout)
        return f"shell: {command[:60]}", r

    async def _hdl_close_shell(content, session_id=None, owner=None, **kw):
        from core.tools.persistent_shell import close_shell
        sid = content.strip() or session_id or "default"
        await close_shell(sid)
        return f"close_shell: {sid}", {"output": "Shell session closed", "exit_code": 0}

    async def _hdl_semantic_search(content, session_id=None, owner=None, **kw):
        from core.codebase_indexer import search_codebase
        lines = content.split("\n", 1)
        query = lines[0].strip()
        k = int(lines[1].strip()) if len(lines) > 1 and lines[1].strip().isdigit() else 5
        result = search_codebase(query, k=k, owner=owner)
        return f"semantic_search: {query[:60]}", {"output": result or "No results found.", "exit_code": 0}

    async def _hdl_watch_file(content, session_id=None, owner=None, **kw):
        """Watch a file for new lines (log tailing).

        Content: path|poll_interval_sec|start_line
        Returns new lines appended since start_line.
        """
        parts = content.split("|")
        path_str = parts[0].strip()
        start_line = int(parts[2]) if len(parts) > 2 and parts[2].strip() else -1
        try:
            rpath = _resolve_tool_path(path_str)
        except ValueError as e:
            return f"watch_file: {e}", {"error": str(e), "exit_code": 1}

        # Read file, return lines after start_line
        try:
            def _read():
                with open(rpath, encoding="utf-8", errors="replace") as f:
                    return f.read(MAX_READ_CHARS + 1)
            data = await asyncio.to_thread(_read)
        except FileNotFoundError:
            return "watch_file: not found", {"error": f"File not found: {rpath}", "exit_code": 1}
        except OSError as e:
            return f"watch_file: {e}", {"error": str(e), "exit_code": 1}

        lines = data.split("\n")
        total = len(lines)
        if start_line < 0 or start_line > total:
            start_line = max(0, total - 20)
        new_lines = lines[start_line:]
        new_text = "\n".join(new_lines)
        truncated = len(data) > MAX_READ_CHARS
        if truncated:
            new_text = new_text[:MAX_READ_CHARS] + "\n... [truncated]"

        return f"watch_file: {path_str} ({len(new_lines)} new lines)", {
            "output": new_text,
            "meta": {"path": path_str, "total_lines": total, "start_line": start_line, "new_lines": len(new_lines)},
            "exit_code": 0,
        }

    async def _hdl_suggest_document(content, session_id=None, owner=None, **kw):
        r = await do_suggest_document(content, owner=owner)
        return f"suggest_document: {r.get('count', 0)} suggestions", r

    async def _hdl_search_chats(content, session_id=None, owner=None, **kw):
        query = content.split("\n")[0].strip()
        return f"search_chats: {query[:80]}", await do_search_chats(query, owner=owner)

    async def _hdl_manage_tasks(content, session_id=None, owner=None, **kw):
        return "manage_tasks", await do_manage_tasks(content, owner=owner)

    async def _hdl_create_skill(content, session_id=None, owner=None, **kw):
        return "create_skill", await do_create_skill(content, owner=owner)

    async def _hdl_manage_skills(content, session_id=None, owner=None, **kw):
        return "manage_skills", await do_manage_skills(content, owner=owner)

    async def _hdl_api_call(content, session_id=None, owner=None, **kw):
        fl = content.split("\n")[0].strip()[:60]
        return f"api_call: {fl}", await do_api_call(content, owner=owner)

    async def _hdl_manage_endpoints(content, session_id=None, owner=None, **kw):
        return "manage_endpoints", await do_manage_endpoints(content, owner=owner)

    async def _hdl_manage_mcp(content, session_id=None, owner=None, **kw):
        return "manage_mcp", await do_manage_mcp(content, owner=owner)

    async def _hdl_manage_webhooks(content, session_id=None, owner=None, **kw):
        return "manage_webhooks", await do_manage_webhooks(content, owner=owner)

    async def _hdl_manage_tokens(content, session_id=None, owner=None, **kw):
        return "manage_tokens", await do_manage_tokens(content, owner=owner)

    async def _hdl_manage_documents(content, session_id=None, owner=None, **kw):
        return "manage_documents", await do_manage_documents(content, owner=owner)

    async def _hdl_manage_settings(content, session_id=None, owner=None, **kw):
        return "manage_settings", await do_manage_settings(content, owner=owner)

    async def _hdl_sessions_spawn(content, session_id=None, owner=None, **kw):
        return "sessions_spawn", await do_sessions_spawn(content, _session_key=session_id)

    async def _hdl_manage_notes(content, session_id=None, owner=None, **kw):
        return "manage_notes", await do_manage_notes(content, owner=owner)

    async def _hdl_manage_calendar(content, session_id=None, owner=None, **kw):
        return "manage_calendar", await do_manage_calendar(content, owner=owner)

    async def _hdl_download_model(content, session_id=None, owner=None, **kw):
        return "download_model", await do_download_model(content, owner=owner)

    async def _hdl_serve_model(content, session_id=None, owner=None, **kw):
        return "serve_model", await do_serve_model(content, owner=owner)

    async def _hdl_list_served_models(content, session_id=None, owner=None, **kw):
        return "list_served_models", await do_list_served_models(content, owner=owner)

    async def _hdl_stop_served_model(content, session_id=None, owner=None, **kw):
        return "stop_served_model", await do_stop_served_model(content, owner=owner)

    async def _hdl_list_downloads(content, session_id=None, owner=None, **kw):
        return "list_downloads", await do_list_downloads(content, owner=owner)

    async def _hdl_cancel_download(content, session_id=None, owner=None, **kw):
        return "cancel_download", await do_cancel_download(content, owner=owner)

    async def _hdl_search_hf_models(content, session_id=None, owner=None, **kw):
        return "search_hf_models", await do_search_hf_models(content, owner=owner)

    async def _hdl_list_cached_models(content, session_id=None, owner=None, **kw):
        return "list_cached_models", await do_list_cached_models(content, owner=owner)

    async def _hdl_app_api(content, session_id=None, owner=None, **kw):
        return "app_api", await do_app_api(content, owner=owner)

    async def _hdl_list_serve_presets(content, session_id=None, owner=None, **kw):
        return "list_serve_presets", await do_list_serve_presets(content, owner=owner)

    async def _hdl_serve_preset(content, session_id=None, owner=None, **kw):
        return "serve_preset", await do_serve_preset(content, owner=owner)

    async def _hdl_adopt_served_model(content, session_id=None, owner=None, **kw):
        return "adopt_served_model", await do_adopt_served_model(content, owner=owner)

    async def _hdl_list_cookbook_servers(content, session_id=None, owner=None, **kw):
        return "list_cookbook_servers", await do_list_cookbook_servers(content, owner=owner)

    async def _hdl_edit_image(content, session_id=None, owner=None, **kw):
        return "edit_image", await do_edit_image(content, owner=owner)

    async def _hdl_trigger_research(content, session_id=None, owner=None, **kw):
        return "trigger_research", await do_trigger_research(content, owner=owner)

    async def _hdl_manage_research(content, session_id=None, owner=None, **kw):
        return "manage_research", await do_manage_research(content, owner=owner)

    async def _hdl_resolve_contact(content, session_id=None, owner=None, **kw):
        return "resolve_contact", await do_resolve_contact(content, owner=owner)

    async def _hdl_manage_contact(content, session_id=None, owner=None, **kw):
        return "manage_contact", await do_manage_contact(content, owner=owner)

    async def _hdl_vault_search(content, session_id=None, owner=None, **kw):
        return "vault_search", await do_vault_search(content, owner=owner)

    async def _hdl_vault_get(content, session_id=None, owner=None, **kw):
        return "vault_get", await do_vault_get(content, owner=owner)

    async def _hdl_vault_unlock(content, session_id=None, owner=None, **kw):
        return "vault_unlock", await do_vault_unlock(content, owner=owner)

    async def _hdl_vision_browser(content, session_id=None, owner=None, **kw):
        return "vision_browser", await do_vision_browser(content, owner=owner)

    # ── Browser artifact helpers ─────────────────────────────────────

    async def _register_browser_artifacts(tool_type: str, result: dict, ctx_any: Any) -> dict[str, str]:
        """Save browser output (screenshot/snapshot) to disk and register as artifacts."""
        if ctx_any is None:
            return {}
        from core.workflow.artifact_store import ArtifactStore
        from core.workflow.context import ContextManager
        from core.workflow.storage import WorkflowStore

        wf_id = getattr(ctx_any, "workflow_id", None)
        if wf_id is None:
            return {}
        artifacts_dir = os.path.join(_BROWSER_ARTIFACT_DIR, wf_id) if _BROWSER_ARTIFACT_DIR else _ensure_browser_artifact_dir(wf_id)
        os.makedirs(artifacts_dir, exist_ok=True)

        store_path = getattr(ctx_any, "metadata", {}).get("_store_path")
        store = WorkflowStore(store_path) if store_path else WorkflowStore()
        artifact_store = ArtifactStore(store)
        artifacts: dict[str, str] = {}
        ts = time.strftime("%Y%m%d_%H%M%S")

        if tool_type == "browser_screenshot" and result.get("screenshot"):
            fname = f"screenshot_{ts}_{uuid.uuid4().hex[:8]}.png"
            fpath = os.path.join(artifacts_dir, fname)
            try:
                png_bytes = base64.b64decode(result["screenshot"])
                with open(fpath, "wb") as f:
                    f.write(png_bytes)
                ref = artifact_store.register_artifact(
                    workflow_id=wf_id,
                    name=f"screenshot_{fname}",
                    artifact_type="screenshot",
                    path=fpath,
                    metadata={"tool": tool_type, "url": result.get("url", ""), "title": result.get("title", "")},
                )
                artifacts["screenshot"] = ref.artifact_id
            except Exception:
                pass

        elif tool_type == "browser_snapshot" and isinstance(result, dict):
            snapshot_data = {k: v for k, v in result.items() if k not in ("error", "error_type", "title", "url")}
            if snapshot_data:
                fname = f"snapshot_{ts}_{uuid.uuid4().hex[:8]}.json"
                fpath = os.path.join(artifacts_dir, fname)
                try:
                    with open(fpath, "w", encoding="utf-8") as f:
                        json.dump(snapshot_data, f, indent=2, default=str)
                    ref = artifact_store.register_artifact(
                        workflow_id=wf_id,
                        name=f"snapshot_{fname}",
                        artifact_type="html_snapshot",
                        path=fpath,
                        metadata={"tool": tool_type, "url": result.get("url", ""), "title": result.get("title", "")},
                    )
                    artifacts["snapshot"] = ref.artifact_id
                except Exception:
                    pass

        if artifacts:
            cm = ContextManager(store)
            ctx = cm.get_context(wf_id)
            if ctx is not None:
                ctx.artifacts.update(artifacts)
                cm.update_context(ctx)
        return artifacts

    # ── Browser tool handlers ────────────────────────────────────────

    async def _hdl_browser_navigate(content, session_id=None, owner=None, **kw):
        return "browser_navigate", await do_browser_navigate(content, session_id=session_id)

    async def _hdl_browser_find(content, session_id=None, owner=None, **kw):
        return "browser_find", await do_browser_find(content, session_id=session_id)

    async def _hdl_browser_find_interactive(content, session_id=None, owner=None, **kw):
        return "browser_find_interactive", await do_browser_find_interactive(content, session_id=session_id)

    async def _hdl_browser_click(content, session_id=None, owner=None, **kw):
        return "browser_click", await do_browser_click(content, session_id=session_id)

    async def _hdl_browser_fill(content, session_id=None, owner=None, **kw):
        parts = content.split("\n", 1)
        selector = parts[0].strip()
        text = parts[1].strip() if len(parts) > 1 else ""
        return "browser_fill", await do_browser_fill(selector, text, session_id=session_id)

    async def _hdl_browser_press(content, session_id=None, owner=None, **kw):
        parts = content.split("\n", 1)
        selector = parts[0].strip()
        key = parts[1].strip() if len(parts) > 1 else "Enter"
        return "browser_press", await do_browser_press(selector, key, session_id=session_id)

    async def _hdl_browser_snapshot(content, session_id=None, owner=None, **kw):
        result = await do_browser_snapshot(session_id=session_id)
        if result and not result.get("error"):
            artifacts = await _register_browser_artifacts("browser_snapshot", result, kw.get("context"))
            if artifacts:
                result["_artifacts"] = artifacts
        return "browser_snapshot", result

    async def _hdl_browser_get_url(content, session_id=None, owner=None, **kw):
        return "browser_get_url", await do_browser_get_url(session_id=session_id)

    async def _hdl_browser_get_title(content, session_id=None, owner=None, **kw):
        return "browser_get_title", await do_browser_get_title(session_id=session_id)

    async def _hdl_browser_screenshot(content, session_id=None, owner=None, **kw):
        result = await do_browser_screenshot(session_id=session_id)
        if result and not result.get("error"):
            artifacts = await _register_browser_artifacts("browser_screenshot", result, kw.get("context"))
            if artifacts:
                result["_artifacts"] = artifacts
        return "browser_screenshot", result

    async def _hdl_browser_current_state(content, session_id=None, owner=None, **kw):
        return "browser_current_state", await do_browser_current_state(session_id=session_id)

    async def _hdl_browser_evaluate(content, session_id=None, owner=None, **kw):
        return "browser_evaluate", await do_browser_evaluate(content, session_id=session_id)

    async def _hdl_browser_health(content, session_id=None, owner=None, **kw):
        return "browser_health", await do_browser_health(session_id=session_id)

    async def _hdl_browser_get_history(content, session_id=None, owner=None, **kw):
        return "browser_get_history", await do_browser_get_history(session_id=session_id)

    async def _hdl_browser_get_facts(content, session_id=None, owner=None, **kw):
        from core.fact_extraction.store import BrowserFactStore
        q = content.strip() if content else ""
        store = BrowserFactStore()
        if q:
            facts = store.search_facts(q, limit=20)
        else:
            facts = store.get_all_facts(limit=50)
        serialized = []
        for f in facts:
            serialized.append({
                "fact_id": f.fact_id,
                "entity": f.entity,
                "claim": f.claim,
                "source_url": f.source_url,
                "source_type": f.source_type,
                "category": f.category,
                "confidence": f.confidence,
                "tags": f.tags,
            })
        return "browser_get_facts", {"facts": serialized, "count": len(serialized)}

    async def _hdl_browser_research(content, session_id=None, owner=None, **kw):
        from core.tools.browser_research import do_browser_research
        try:
            args = json.loads(content) if content and content.strip() else {}
        except (json.JSONDecodeError, ValueError):
            args = {"question": content.strip()} if content and content.strip() else {}
        question = args.get("question", "") if isinstance(args, dict) else str(args)
        max_pages = args.get("max_pages", 5) if isinstance(args, dict) else 5
        result = await do_browser_research(
            question=question,
            session_id=session_id,
            max_pages=max_pages,
        )
        return "browser_research", result

    async def _hdl_browser_list_tabs(content, session_id=None, owner=None, **kw):
        return "browser_list_tabs", await do_browser_list_tabs(session_id=session_id)

    async def _hdl_browser_switch_tab(content, session_id=None, owner=None, **kw):
        idx = int(content.strip()) if content and content.strip().lstrip("-").isdigit() else 0
        return "browser_switch_tab", await do_browser_switch_tab(index=idx, session_id=session_id)

    async def _hdl_browser_new_tab(content, session_id=None, owner=None, **kw):
        url = content.strip() or None
        return "browser_new_tab", await do_browser_new_tab(url=url, session_id=session_id)

    async def _hdl_browser_close_tab(content, session_id=None, owner=None, **kw):
        idx = int(content.strip()) if content and content.strip().lstrip("-").isdigit() else 0
        return "browser_close_tab", await do_browser_close_tab(index=idx, session_id=session_id)

    async def _hdl_browser_wait_visible(content, session_id=None, owner=None, **kw):
        return "browser_wait_visible", await do_browser_wait_visible(content, session_id=session_id)

    async def _hdl_browser_wait_text(content, session_id=None, owner=None, **kw):
        return "browser_wait_text", await do_browser_wait_text(content, session_id=session_id)

    async def _hdl_browser_wait_interactive(content, session_id=None, owner=None, **kw):
        return "browser_wait_interactive", await do_browser_wait_interactive(content, session_id=session_id)

    async def _hdl_browser_shadow_query(content, session_id=None, owner=None, **kw):
        return "browser_shadow_query", await do_browser_shadow_query(content, session_id=session_id)

    async def _hdl_mcp_tool(content, session_id=None, owner=None, **kw):
        fl = content.split(_CHR)[0][:80]
        return f"{tool}: {fl}", await _call_mcp_tool(tool, content, progress_cb=kw.get("progress_cb"), session_id=session_id)

    async def _hdl_ai_tool(content, session_id=None, owner=None, **kw):
        return await dispatch_ai_tool(tool, content, session_id, owner=owner)

    # Build automation handlers — bridge to AutomationLoop
    _BUILD_DIR_CACHE: dict[str, str] = {}
    _BUILD_EXEC_ID: int = 0

    async def _register_build_artifacts(project_dir: str, ctx_any: Any, result: dict) -> dict[str, str]:
        """Scan project_dir for build outputs and register as artifacts. Returns {name: artifact_id}."""
        if ctx_any is None:
            return {}
        from core.workflow.artifact_store import ArtifactStore
        from core.workflow.context import ContextManager
        from core.workflow.storage import WorkflowStore

        wf_id = getattr(ctx_any, "workflow_id", None)
        if wf_id is None:
            return {}
        store = WorkflowStore()
        artifact_store = ArtifactStore(store)
        artifacts: dict[str, str] = {}
        output_patterns = [
            ("apk", ".apk"), ("aab", ".aab"),
            ("build_log", "build.log"), ("build_log", ".log"),
            ("report", ".html"), ("coverage", "coverage.xml"),
            ("test_result", "test-results.xml"),
        ]
        scanned = set()
        for root, _dirs, files in os.walk(project_dir):
            for fname in files:
                fpath = os.path.join(root, fname)
                if fpath in scanned:
                    continue
                scanned.add(fpath)
                for art_name, suffix in output_patterns:
                    if fname.endswith(suffix) and art_name not in artifacts:
                        try:
                            ref = artifact_store.register_artifact(
                                workflow_id=wf_id,
                                name=f"{art_name}_{fname}",
                                artifact_type=art_name,
                                path=fpath,
                                metadata={"project_dir": project_dir, "source": "build"},
                            )
                            artifacts[art_name] = ref.artifact_id
                        except Exception:
                            pass
        if artifacts:
            cm = ContextManager(store)
            ctx = cm.get_context(wf_id)
            if ctx is not None:
                ctx.artifacts.update(artifacts)
                cm.update_context(ctx)
        return artifacts

    async def _hdl_build_project(content, **kw):
        import json as _json
        import uuid as _uuid
        try:
            args = _json.loads(content) if content.strip() else {}
        except _json.JSONDecodeError:
            args = {}
        task = args.get("task", content.split("\n")[0] if "\n" in content else content)
        proj_dir = args.get("project_dir", "")
        if not proj_dir and _BUILD_DIR_CACHE:
            proj_dir = next(iter(_BUILD_DIR_CACHE.values()), "")
        if not proj_dir:
            proj_dir = os.getcwd()
        _BUILD_DIR_CACHE["last"] = proj_dir
        exec_id = _uuid.uuid4().hex[:12]
        exec_task = asyncio.create_task(do_build_project(task, proj_dir, progress_cb=kw.get("progress_cb")))
        from core.tools.build_tools import _BUILD_EXECUTIONS
        _BUILD_EXECUTIONS[exec_id] = exec_task
        try:
            r = await exec_task
        except asyncio.CancelledError:
            return "build_project", {"success": False, "status": "cancelled", "execution_id": exec_id}
        finally:
            _BUILD_EXECUTIONS.pop(exec_id, None)
        r["execution_id"] = exec_id
        if r.get("success"):
            artifacts = await _register_build_artifacts(proj_dir, kw.get("context"), r)
            if artifacts:
                r["_artifacts"] = artifacts
        return "build_project", r

    async def _hdl_repair_project(content, **kw):
        import json as _json
        import uuid as _uuid
        try:
            args = _json.loads(content) if content.strip() else {}
        except _json.JSONDecodeError:
            args = {}
        proj_dir = args.get("project_dir", _BUILD_DIR_CACHE.get("last", os.getcwd()))
        build_output = args.get("build_output", "")
        exec_id = _uuid.uuid4().hex[:12]
        exec_task = asyncio.create_task(do_repair_project(proj_dir, build_output, progress_cb=kw.get("progress_cb")))
        from core.tools.build_tools import _BUILD_EXECUTIONS
        _BUILD_EXECUTIONS[exec_id] = exec_task
        try:
            r = await exec_task
        except asyncio.CancelledError:
            return "repair_project", {"success": False, "status": "cancelled", "execution_id": exec_id}
        finally:
            _BUILD_EXECUTIONS.pop(exec_id, None)
        r["execution_id"] = exec_id
        if r.get("success"):
            artifacts = await _register_build_artifacts(proj_dir, kw.get("context"), r)
            if artifacts:
                r["_artifacts"] = artifacts
        return "repair_project", r

    async def _hdl_run_tests(content, **kw):
        import json as _json
        import uuid as _uuid
        try:
            args = _json.loads(content) if content.strip() else {}
        except _json.JSONDecodeError:
            args = {}
        proj_dir = args.get("project_dir", _BUILD_DIR_CACHE.get("last", os.getcwd()))
        exec_id = _uuid.uuid4().hex[:12]
        exec_task = asyncio.create_task(do_run_tests(proj_dir, progress_cb=kw.get("progress_cb")))
        from core.tools.build_tools import _BUILD_EXECUTIONS
        _BUILD_EXECUTIONS[exec_id] = exec_task
        try:
            r = await exec_task
        except asyncio.CancelledError:
            return "run_tests", {"success": False, "status": "cancelled", "execution_id": exec_id}
        finally:
            _BUILD_EXECUTIONS.pop(exec_id, None)
        r["execution_id"] = exec_id
        if r.get("success"):
            artifacts = await _register_build_artifacts(proj_dir, kw.get("context"), r)
            if artifacts:
                r["_artifacts"] = artifacts
        return "run_tests", r

    async def _hdl_runtime_validate(content, **kw):
        import json as _json
        import uuid as _uuid
        try:
            args = _json.loads(content) if content.strip() else {}
        except _json.JSONDecodeError:
            args = {}
        proj_dir = args.get("project_dir", _BUILD_DIR_CACHE.get("last", os.getcwd()))
        exec_id = _uuid.uuid4().hex[:12]
        exec_task = asyncio.create_task(do_runtime_validate(proj_dir, progress_cb=kw.get("progress_cb")))
        from core.tools.build_tools import _BUILD_EXECUTIONS
        _BUILD_EXECUTIONS[exec_id] = exec_task
        try:
            r = await exec_task
        except asyncio.CancelledError:
            return "runtime_validate", {"success": False, "status": "cancelled", "execution_id": exec_id}
        finally:
            _BUILD_EXECUTIONS.pop(exec_id, None)
        r["execution_id"] = exec_id
        if r.get("success"):
            artifacts = await _register_build_artifacts(proj_dir, kw.get("context"), r)
            if artifacts:
                r["_artifacts"] = artifacts
        return "runtime_validate", r

    async def _hdl_manage_memory(content, **kw):
        r = await do_manage_memory(content)
        return "manage_memory", r

    async def _hdl_create_session(content, **kw):
        r = await do_create_session(content)
        return "create_session", r

    async def _hdl_chat_with_model(content, **kw):
        r = await do_chat_with_model(content)
        return "chat_with_model", r

    async def _hdl_list_sessions(content, **kw):
        import json as _json
        try:
            args = _json.loads(content) if content.strip() else {}
        except _json.JSONDecodeError:
            args = {}
        _filter = args.get("filter", "")
        from core.session import SESSION_DIR, ConversationManager
        if not SESSION_DIR.exists():
            return "list_sessions", {"output": "No sessions found.", "sessions": [], "exit_code": 0}
        _files = sorted(SESSION_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        _sessions = []
        for _p in _files:
            try:
                _data = _json.loads(_p.read_text(encoding="utf-8"))
                _sid = _data.get("session_id", _p.stem)
                _name = _data.get("name", "") or _sid
                if _filter and _filter.lower() not in _name.lower() and _filter.lower() not in _sid.lower():
                    continue
                _msgs = _data.get("messages", [])
                _last = _msgs[-1]["content"][:200] if _msgs else ""
                _sessions.append({
                    "session_key": _sid,
                    "label": _name,
                    "message_count": len(_msgs),
                    "last_message": _last,
                    "updated_at": _msgs[-1]["timestamp"] if _msgs else "",
                })
            except Exception:
                continue
            if len(_sessions) >= 100:
                break
        _lines = [f"Found {len(_sessions)} chat(s):"] if _sessions else ["No sessions found."]
        for _s in _sessions:
            _lines.append(f"  [{_s['session_key']}] {_s['label']} ({_s['message_count']} msgs)")
        return "list_sessions", {"output": "\n".join(_lines), "sessions": _sessions, "exit_code": 0}

    async def _hdl_manage_session(content, **kw):
        import json as _json
        try:
            args = _json.loads(content) if content.strip() else {}
        except _json.JSONDecodeError:
            return "manage_session", {"error": "Invalid JSON", "exit_code": 1}
        _action = args.get("action", "")
        _sid = args.get("session_id", "")
        _value = args.get("value", "")
        if not _action:
            return "manage_session", {"error": "No action provided", "exit_code": 1}
        from core.session import SESSION_DIR, ConversationManager
        _found = None
        for _p in SESSION_DIR.glob("*.json"):
            try:
                _data = _json.loads(_p.read_text(encoding="utf-8"))
                if _data.get("session_id") == _sid or _p.stem == _sid:
                    _found = _p
                    break
            except Exception:
                if _p.stem == _sid:
                    _found = _p
                    break
        if _action == "rename":
            if not _found:
                return "manage_session", {"error": f"Session '{_sid}' not found", "exit_code": 1}
            _conv = ConversationManager(session_id=_found.stem)
            _conv.load()
            _conv.rename(_value or "Renamed Chat")
            return "manage_session", {"output": f"Session '{_sid}' renamed to '{_value}'", "exit_code": 0}
        elif _action == "archive":
            _archive_dir = SESSION_DIR / "archive"
            _archive_dir.mkdir(exist_ok=True)
            _target = _archive_dir / _found.name
            _found.rename(_target) if _found else None
            return "manage_session", {"output": f"Session '{_sid}' archived", "exit_code": 0}
        elif _action == "delete":
            _found.unlink() if _found and _found.exists() else None
            return "manage_session", {"output": f"Session '{_sid}' deleted", "exit_code": 0}
        elif _action == "fork":
            _conv = ConversationManager(session_id=_found.stem) if _found else ConversationManager()
            _conv.load() if _found else None
            _fork = _conv.fork()
            _fork.save()
            return "manage_session", {"output": f"Session forked as '{_fork.session_id}'", "fork_id": _fork.session_id, "exit_code": 0}
        elif _action in ("important", "unimportant", "truncate"):
            if not _found:
                return "manage_session", {"error": f"Session '{_sid}' not found", "exit_code": 1}
            _conv = ConversationManager(session_id=_found.stem)
            _conv.load()
            if _action == "truncate":
                _keep = int(_value) if _value and _value.isdigit() else 10
                _conv.compact(keep_last=_keep)
                _conv.save()
            return "manage_session", {"output": f"Session '{_sid}' {_action}d", "exit_code": 0}
        else:
            return "manage_session", {"error": f"Unknown action: {_action}", "exit_code": 1}

    async def _hdl_list_models(content, **kw):
        import json as _json
        try:
            args = _json.loads(content) if content.strip() else {}
        except _json.JSONDecodeError:
            args = {}
        _filter = args.get("filter", "")
        _models = []
        try:
            from core.llm_router import get_config_router
            _router = get_config_router()
            _config_models = _router.get_all_models()
            for _group, _model in _config_models.items():
                if _model and (not _filter or _filter.lower() in str(_model).lower() or _filter.lower() in _group.lower()):
                    _models.append({"group": _group, "model": _model, "source": "config"})
        except Exception as e:
            logger.debug("config models lookup: %s", e)
        try:
            from core.database_models import ModelEndpoint, SessionLocal
            from core.database import get_async_session
            _db = SessionLocal()
            try:
                _eps = _db.query(ModelEndpoint).filter(ModelEndpoint.is_enabled == True).all()
                for _ep in _eps:
                    _name = _ep.name or _ep.id
                    if _filter and _filter.lower() not in _name.lower():
                        continue
                    _models.append({"id": _ep.id, "name": _name, "url": _ep.base_url, "source": "endpoint"})
            finally:
                _db.close()
        except Exception as e:
            logger.debug("db models lookup: %s", e)
        if not _models:
            return "list_models", {"output": "No models configured.", "models": [], "exit_code": 0}
        _lines = [f"Found {len(_models)} model(s):"]
        for _m in _models:
            if _m.get("source") == "config":
                _lines.append(f"  [{_m['group']}] {_m['model']} (config)")
            else:
                _lines.append(f"  [{_m['id']}] {_m['name']} ({_m['url']})")
        return "list_models", {"output": "\n".join(_lines), "models": _models, "exit_code": 0}

    async def _hdl_ui_control(content, **kw):
        import json as _json
        try:
            args = _json.loads(content) if content.strip() else {}
        except _json.JSONDecodeError:
            return "ui_control", {"error": "Invalid JSON", "exit_code": 1}
        _action = args.get("action", "")
        _name = args.get("name", "")
        _value = args.get("value", "")
        if _action == "get_toggles":
            return "ui_control", {"output": "Current toggles: web=on, bash=on, research=on, incognito=off, document_editor=on", "toggles": {"web": True, "bash": True, "research": True, "incognito": False, "document_editor": True}, "exit_code": 0}
        elif _action == "toggle":
            _state = "enabled" if _value == "on" else "disabled"
            return "ui_control", {"output": f"Tool '{_name}' toggled {_state}", "toggle_name": _name, "state": _value, "ui_event": {"action": "toggle", "name": _name, "value": _value}, "exit_code": 0}
        elif _action in ("set_mode", "switch_model"):
            return "ui_control", {"output": f"Set {_action.replace('_', ' ')} to '{_name or _value}'", _action: _name or _value, "ui_event": {"action": _action, "name": _name, "value": _value}, "exit_code": 0}
        elif _action == "set_theme":
            _presets = {"dark", "light", "midnight", "paper", "nord", "monokai", "gruvbox", "dracula", "cyberpunk", "retrowave", "forest", "ocean", "ume", "copper", "terminal", "vaporwave", "lavender", "gpt", "coffee", "claude"}
            if _name in _presets:
                return "ui_control", {"output": f"Theme set to '{_name}'", "theme_name": _name, "ui_event": {"action": "set_theme", "name": _name}, "exit_code": 0}
            return "ui_control", {"output": f"Unknown theme '{_name}'. Use create_theme for custom themes.", "exit_code": 0}
        elif _action == "create_theme":
            _colors = args.get("colors", {})
            return "ui_control", {"output": f"Custom theme '{_name}' created", "theme_name": _name, "colors": _colors, "ui_event": {"action": "create_theme", "name": _name, "colors": _colors}, "exit_code": 0}
        elif _action == "open_panel":
            return "ui_control", {"output": f"Opening panel: {_name}", "ui_event": {"action": "open_panel", "name": _name}, "exit_code": 0}
        elif _action == "open_email_reply":
            _uid = args.get("uid", "")
            _folder = args.get("folder", "INBOX")
            _mode = args.get("mode", "reply")
            return "ui_control", {"output": f"Opening email reply draft (uid={_uid}, folder={_folder}, mode={_mode})", "ui_event": {"action": "open_email_reply", "uid": _uid, "folder": _folder, "mode": _mode}, "exit_code": 0}
        return "ui_control", {"error": f"Unknown action: {_action}", "exit_code": 1}

    async def _hdl_pipeline(content, **kw):
        import json as _json
        try:
            args = _json.loads(content) if content.strip() else {}
        except _json.JSONDecodeError:
            return "pipeline", {"error": "Invalid JSON", "exit_code": 1}
        _steps = args.get("steps", [])
        if not _steps:
            return "pipeline", {"error": "No steps provided", "exit_code": 1}
        from core.llm_router import complete as _llm_complete
        _context = ""
        _results = []
        for _i, _step in enumerate(_steps):
            _model = _step.get("model", "")
            _instruction = _step.get("instruction", "")
            _prompt = f"Context from previous step:\n{_context}\n\nTask: {_instruction}" if _context else _instruction
            try:
                _resp = await _llm_complete(
                    _model or "chat",
                    [{"role": "user", "content": _prompt}],
                    timeout=120,
                )
                _text = _resp.unwrap() if hasattr(_resp, 'unwrap') else str(_resp)
            except Exception as _e:
                _text = f"<error: {_e}>"
            _results.append({"step": _i, "model": _model, "output": _text})
            _context = _text
        _lines = [f"Pipeline complete ({len(_results)} steps):"]
        for _r in _results:
            _out = _r["output"][:300]
            _lines.append(f"  Step {_r['step']+1} ({_r['model']}): {_out}")
        return "pipeline", {"output": "\n".join(_lines), "steps": _results, "exit_code": 0}

    async def _hdl_send_to_session(content, **kw):
        import json as _json
        try:
            args = _json.loads(content) if content.strip() else {}
        except _json.JSONDecodeError:
            return "send_to_session", {"error": "Invalid JSON", "exit_code": 1}
        _target_sid = args.get("session_id", "")
        _message = args.get("message", "")
        if not _target_sid or not _message:
            return "send_to_session", {"error": "session_id and message required", "exit_code": 1}
        from core.session import SESSION_DIR, ConversationManager
        _conv = ConversationManager(session_id=_target_sid)
        _conv.load()
        _conv.add_message("user", _message)
        from core.llm_router import complete as _llm_complete
        try:
            _resp = await _llm_complete(
                "chat",
                _conv.get_context(last_n=20),
                timeout=60,
            )
            _reply = _resp.unwrap() if hasattr(_resp, 'unwrap') else str(_resp)
        except Exception as _e:
            _reply = f"<error: {_e}>"
        _conv.add_message("assistant", _reply)
        _conv.save()
        return "send_to_session", {"output": _reply, "session_id": _target_sid, "exit_code": 0}

    async def _hdl_ask_teacher(content, **kw):
        import json as _json
        try:
            args = _json.loads(content) if content.strip() else {}
        except _json.JSONDecodeError:
            return "ask_teacher", {"error": "Invalid JSON", "exit_code": 1}
        _problem = args.get("problem", "")
        _model = args.get("model", "")
        if not _problem:
            return "ask_teacher", {"error": "No problem provided", "exit_code": 1}
        from core.llm_router import complete as _llm_complete
        try:
            from core.config_registry import config as _cfg
            _teacher = _model or _cfg.get("role_models.teacher") or _cfg.get("llm.teacher_model") or "teacher"
        except Exception:
            _teacher = _model or "teacher"
        _system = "You are a highly capable teacher AI. Explain your reasoning clearly and thoroughly."
        try:
            _resp = await _llm_complete(
                _teacher,
                [{"role": "system", "content": _system}, {"role": "user", "content": _problem}],
                timeout=120,
            )
            _answer = _resp.unwrap() if hasattr(_resp, 'unwrap') else str(_resp)
        except Exception as _e:
            _answer = f"<teacher unavailable: {_e}>"
        return "ask_teacher", {"output": _answer, "model": _teacher, "exit_code": 0}

    async def _hdl_automated_build(content, **kw):
        import json as _json
        import uuid as _uuid
        try:
            args = _json.loads(content) if content.strip() else {}
        except _json.JSONDecodeError:
            args = {}
        task = args.get("task", content.split("\n")[0] if "\n" in content else content)
        proj_dir = args.get("project_dir", _BUILD_DIR_CACHE.get("last", os.getcwd()))
        exec_id = _uuid.uuid4().hex[:12]
        from core.tools.automated_build import do_automated_build
        try:
            record = await do_automated_build(
                task, proj_dir, progress_cb=kw.get("progress_cb"),
            )
        except Exception as exc:
            return "automated_build", {
                "success": False, "status": "failed",
                "error": str(exc)[:200], "execution_id": exec_id,
            }
        result = record.to_dict()
        result["execution_id"] = exec_id
        return "automated_build", result

    async def _hdl_cancel_build(content, **kw):
        import json as _json
        try:
            args = _json.loads(content) if content.strip() else {}
        except _json.JSONDecodeError:
            args = {}
        exec_id = args.get("execution_id", content.strip())
        r = await do_cancel_build(exec_id)
        return "cancel_build", r

    async def _hdl_workflow_start(content, **kw):
        r = await do_workflow_start(content, session_id=kw.get("session_id"), owner=kw.get("owner"))
        return "workflow_start", r

    async def _hdl_workflow_resume(content, **kw):
        r = await do_workflow_resume(content)
        return "workflow_resume", r

    async def _hdl_workflow_cancel(content, **kw):
        r = await do_workflow_cancel(content)
        return "workflow_cancel", r

    async def _hdl_workflow_status(content, **kw):
        r = await do_workflow_status(content)
        return "workflow_status", r

    async def _hdl_workflow_list(content, **kw):
        r = await do_workflow_list(content)
        return "workflow_list", r

    # ── Scheduler Tools ──────────────────────────────────────────────────
    async def _hdl_scheduler_submit(content, **kw):
        from core.tools.scheduler_tools import do_scheduler_submit
        try:
            args = json.loads(content) if content and content.strip() else {}
        except (json.JSONDecodeError, ValueError):
            args = {"goal": content.strip()} if content and content.strip() else {}
        r = await do_scheduler_submit(
            goal=args.get("goal", "") if isinstance(args, dict) else str(args),
            priority=args.get("priority", 0) if isinstance(args, dict) else 0,
            activity_id=args.get("activity_id") if isinstance(args, dict) else None,
            node_type=args.get("node_type", "goal") if isinstance(args, dict) else "goal",
            depends_on=args.get("depends_on") if isinstance(args, dict) else None,
            metadata=args.get("metadata") if isinstance(args, dict) else None,
        )
        return "scheduler_submit", r

    async def _hdl_scheduler_list(content, **kw):
        from core.tools.scheduler_tools import do_scheduler_list
        try:
            args = json.loads(content) if content and content.strip() else {}
        except (json.JSONDecodeError, ValueError):
            args = {}
        r = await do_scheduler_list(
            status_filter=args.get("status") if isinstance(args, dict) else None,
        )
        return "scheduler_list", r

    async def _hdl_scheduler_status(content, **kw):
        from core.tools.scheduler_tools import do_scheduler_status
        aid = content.strip() if content and content.strip() else ""
        r = await do_scheduler_status(aid)
        return "scheduler_status", r

    async def _hdl_scheduler_cancel(content, **kw):
        from core.tools.scheduler_tools import do_scheduler_cancel
        aid = content.strip() if content and content.strip() else ""
        r = await do_scheduler_cancel(aid)
        return "scheduler_cancel", r

    async def _hdl_scheduler_set_priority(content, **kw):
        from core.tools.scheduler_tools import do_scheduler_set_priority
        try:
            args = json.loads(content) if content and content.strip() else {}
        except (json.JSONDecodeError, ValueError):
            args = {}
        aid = args.get("activity_id", "") if isinstance(args, dict) else ""
        pri = args.get("priority", 0) if isinstance(args, dict) else 0
        r = await do_scheduler_set_priority(aid, pri)
        return "scheduler_set_priority", r

    async def _hdl_scheduler_tick(content, **kw):
        from core.tools.scheduler_tools import do_scheduler_tick
        r = await do_scheduler_tick()
        return "scheduler_tick", r

    async def _hdl_scheduler_chain_submit(content, **kw):
        from core.tools.scheduler_tools import do_scheduler_chain_submit
        try:
            args = json.loads(content) if content and content.strip() else {}
        except (json.JSONDecodeError, ValueError):
            args = {}
        r = await do_scheduler_chain_submit(
            name=args.get("name", "Chain") if isinstance(args, dict) else "Chain",
            steps=args.get("steps", []) if isinstance(args, dict) else [],
            priority=args.get("priority", 0) if isinstance(args, dict) else 0,
        )
        return "scheduler_chain_submit", r

    async def _hdl_scheduler_chain_list(content, **kw):
        from core.tools.scheduler_tools import do_scheduler_chain_list
        r = await do_scheduler_chain_list()
        return "scheduler_chain_list", r

    async def _hdl_scheduler_chain_status(content, **kw):
        from core.tools.scheduler_tools import do_scheduler_chain_status
        chain_id = content.strip() if content and content.strip() else ""
        r = await do_scheduler_chain_status(chain_id)
        return "scheduler_chain_status", r

    async def _hdl_scheduler_chain_cancel(content, **kw):
        from core.tools.scheduler_tools import do_scheduler_chain_cancel
        chain_id = content.strip() if content and content.strip() else ""
        r = await do_scheduler_chain_cancel(chain_id)
        return "scheduler_chain_cancel", r

    # ── Agent Dispatch ──────────────────────────────────────────────────
    async def _hdl_agent_exec(content, **kw):
        """Route to a registered agent via the multi-agent graph.

        Content JSON:
          {"agent_id": "build", "action": {...}, "goal": "..."}
        """
        import json as _json
        try:
            args = _json.loads(content) if isinstance(content, str) and content.strip() else {}
        except _json.JSONDecodeError:
            args = {}
        agent_id = args.get("agent_id", "")
        if not agent_id:
            return "agent_exec", {"error": "No agent_id provided", "exit_code": 1}
        from core.agents.router import get_agent as _get_agent
        agent = _get_agent(agent_id)
        if not agent:
            return "agent_exec", {"error": f"Unknown agent: {agent_id}", "exit_code": 1}
        context = kw.get("context")
        if context and args.get("action"):
            for k, v in args["action"].items():
                context.variables[k] = v
        result = await agent.execute(context=context)
        return "agent_exec", result

    _TOOL_HANDLERS = {
        "create_document": _hdl_create_document,
        "update_document": _hdl_update_document,
        "edit_document": _hdl_edit_document,
        "edit_file": _hdl_edit_file,
        "undo_edit_file": _hdl_undo_edit_file,
        "batch_edit_file": _hdl_batch_edit_file,
        "refactor": _hdl_refactor,
        "shell": _hdl_shell_command,
        "shell_command": _hdl_shell_command,
        "close_shell": _hdl_close_shell,
        "semantic_search": _hdl_semantic_search,
        "watch_file": _hdl_watch_file,
        "suggest_document": _hdl_suggest_document,
        "search_chats": _hdl_search_chats,
        "manage_tasks": _hdl_manage_tasks,
        "create_skill": _hdl_create_skill,
        "manage_skills": _hdl_manage_skills,
        "api_call": _hdl_api_call,
        "manage_endpoints": _hdl_manage_endpoints,
        "manage_mcp": _hdl_manage_mcp,
        "manage_webhooks": _hdl_manage_webhooks,
        "manage_tokens": _hdl_manage_tokens,
        "manage_documents": _hdl_manage_documents,
        "manage_settings": _hdl_manage_settings,
        "sessions_spawn": _hdl_sessions_spawn,
        "manage_notes": _hdl_manage_notes,
        "manage_calendar": _hdl_manage_calendar,
        "download_model": _hdl_download_model,
        "serve_model": _hdl_serve_model,
        "list_served_models": _hdl_list_served_models,
        "stop_served_model": _hdl_stop_served_model,
        "list_downloads": _hdl_list_downloads,
        "cancel_download": _hdl_cancel_download,
        "search_hf_models": _hdl_search_hf_models,
        "list_cached_models": _hdl_list_cached_models,
        "app_api": _hdl_app_api,
        "list_serve_presets": _hdl_list_serve_presets,
        "serve_preset": _hdl_serve_preset,
        "adopt_served_model": _hdl_adopt_served_model,
        "list_cookbook_servers": _hdl_list_cookbook_servers,
        "edit_image": _hdl_edit_image,
        "trigger_research": _hdl_trigger_research,
        "manage_research": _hdl_manage_research,
        "resolve_contact": _hdl_resolve_contact,
        "manage_contact": _hdl_manage_contact,
        "vault_search": _hdl_vault_search,
        "vault_get": _hdl_vault_get,
        "vault_unlock": _hdl_vault_unlock,
        "vision_browser": _hdl_vision_browser,
        "browser_navigate": _hdl_browser_navigate,
        "browser_find": _hdl_browser_find,
        "browser_find_interactive": _hdl_browser_find_interactive,
        "browser_click": _hdl_browser_click,
        "browser_fill": _hdl_browser_fill,
        "browser_press": _hdl_browser_press,
        "browser_snapshot": _hdl_browser_snapshot,
        "browser_get_url": _hdl_browser_get_url,
        "browser_get_title": _hdl_browser_get_title,
        "browser_screenshot": _hdl_browser_screenshot,
        "browser_current_state": _hdl_browser_current_state,
        "browser_evaluate": _hdl_browser_evaluate,
        "browser_health": _hdl_browser_health,
        "browser_get_history": _hdl_browser_get_history,
        "browser_get_facts": _hdl_browser_get_facts,
        "browser_research": _hdl_browser_research,
        "browser_list_tabs": _hdl_browser_list_tabs,
        "browser_switch_tab": _hdl_browser_switch_tab,
        "browser_new_tab": _hdl_browser_new_tab,
        "browser_close_tab": _hdl_browser_close_tab,
        "browser_wait_visible": _hdl_browser_wait_visible,
        "browser_wait_text": _hdl_browser_wait_text,
        "browser_wait_interactive": _hdl_browser_wait_interactive,
        "browser_shadow_query": _hdl_browser_shadow_query,
        "automated_build": _hdl_automated_build,
        "build_project": _hdl_build_project,
        "repair_project": _hdl_repair_project,
        "run_tests": _hdl_run_tests,
        "runtime_validate": _hdl_runtime_validate,
        "manage_memory": _hdl_manage_memory,
        "create_session": _hdl_create_session,
        "chat_with_model": _hdl_chat_with_model,
        "list_sessions": _hdl_list_sessions,
        "manage_session": _hdl_manage_session,
        "list_models": _hdl_list_models,
        "ui_control": _hdl_ui_control,
        "pipeline": _hdl_pipeline,
        "send_to_session": _hdl_send_to_session,
        "ask_teacher": _hdl_ask_teacher,
        "cancel_build": _hdl_cancel_build,
        "workflow_start": _hdl_workflow_start,
        "workflow_resume": _hdl_workflow_resume,
        "workflow_cancel": _hdl_workflow_cancel,
        "workflow_status": _hdl_workflow_status,
        "workflow_list": _hdl_workflow_list,
        "scheduler_submit": _hdl_scheduler_submit,
        "scheduler_list": _hdl_scheduler_list,
        "scheduler_status": _hdl_scheduler_status,
        "scheduler_cancel": _hdl_scheduler_cancel,
        "scheduler_set_priority": _hdl_scheduler_set_priority,
        "scheduler_tick": _hdl_scheduler_tick,
        "scheduler_chain_submit": _hdl_scheduler_chain_submit,
        "scheduler_chain_list": _hdl_scheduler_chain_list,
        "scheduler_chain_status": _hdl_scheduler_chain_status,
        "scheduler_chain_cancel": _hdl_scheduler_chain_cancel,
        "agent_exec": _hdl_agent_exec,
    }

    for _t in _MCP_TOOL_MAP:
        _TOOL_HANDLERS[_t] = _hdl_mcp_tool

    tool = block.tool_type
    content = block.content

    # Map bare email tool names to MCP-prefixed equivalents for engine step dispatch
    _BARE_EMAIL_TOOLS = {"send_email", "delete_email", "list_emails", "read_email",
                         "reply_to_email", "archive_email", "mark_email_read",
                         "bulk_email", "list_email_accounts"}
    if tool in _BARE_EMAIL_TOOLS:
        tool = f"mcp__email__{tool}"

    # Misformatted tool call detection: model put JSON inside ```python``` (or
    # similar) without naming the tool. Common with MiniMax-style outputs.
    # Return a helpful error so the model retries with the correct format.
    if tool in ("python", "json", "xml") and content.strip().startswith("{") and content.strip().endswith("}"):
        try:
            import json as _json
            parsed = _json.loads(content.strip())
            if isinstance(parsed, dict):
                desc = f"{tool}: misformatted tool call"
                result = {
                    "error": (
                        f"You wrote a JSON object inside a ```{tool}``` block, but that's not a tool call.\n"
                        "To call a tool, use the tool name as the fence tag, e.g.\n"
                        "```resolve_contact\n"
                        "{\"name\": \"...\"}\n"
                        "```\n"
                        "or\n"
                        "```send_email\n"
                        "{\"to\": \"...\", \"subject\": \"...\", \"body\": \"...\"}\n"
                        "```"
                    ),
                    "exit_code": 1,
                }
                return desc, result
        except (ValueError, TypeError) as _e:
            logger.debug("[core.tools.execution] line range parse failed: %s", _e)

    # Reject broken tools (registered but not implemented)
    if tool in BROKEN_TOOLS:
        desc = f"{tool}: DISABLED"
        result = {"status": "disabled", "reason": "not implemented", "exit_code": 1}
        logger.info(f"Tool disabled (not implemented): {tool}")
        return desc, result

    # Reject tools that the user has disabled for this request
    if disabled_tools and tool in disabled_tools:
        desc = f"{tool}: BLOCKED"
        result = {"error": f"Tool '{tool}' is disabled by user.", "exit_code": 1}
        logger.info(f"Tool blocked by user: {tool}")
        return desc, result

    # Phase 1e: RBAC Authorization Gate
    from core.auth import get_auth_manager
    from core.tools.security import is_authorized_to_execute

    ctx = get_auth_manager().resolve_context(owner or "guest")

    if not is_authorized_to_execute(tool, ctx):
        desc = f"{tool}: UNAUTHORIZED"
        result = {
            "error": (
                f"Tool '{tool}' requires higher permissions than granted to your role ({', '.join(ctx.roles)}). "
                "Contact an administrator to request the necessary access."
            ),
            "exit_code": 1,
        }
        logger.warning("RBAC blocked execution: owner=%r tool=%s roles=%r", owner, tool, ctx.roles)
        return desc, result

    # Phase 6: Check for approval via MCP Bridge if tool needs confirmation
    from core.tools.policy import policy_engine
    policy = policy_engine.get_policy(tool)
    if policy and policy.needs_confirmation:
        from mcp.server import mcp_server
        # Only wait if mcp_server is running
        if mcp_server.is_running:
            approval_id = uuid.uuid4().hex
            decision = await mcp_server.wait_for_approval(
                kind="exec",
                approval_id=approval_id,
                tool_name=tool,
                description=policy.description or f"Execution of {tool}",
                input_preview=str(content)[:1000]
            )
            if decision == "deny":
                desc = f"{tool}: DENIED"
                result = {"error": f"Tool '{tool}' execution was denied by user via MCP Bridge.", "exit_code": 1}
                logger.info(f"Tool denied by user via MCP Bridge: {tool}")
                return desc, result
            logger.info(f"Tool approved by user via MCP Bridge: {tool} ({decision})")

    # Track tool execution in metrics
    from core.observability.metrics import inc_tool_calls_total
    inc_tool_calls_total(tool)

    # Background execution: a `bash` block whose first line is the `#!bg`
    # marker runs DETACHED — returns a job id immediately so the chat stream
    # isn't held open for a multi-minute install/ffmpeg/download. The always-on
    # monitor re-invokes the agent with the full output when the job finishes.
    if tool == "bash" and session_id:
        _is_bg, _bg_cmd = _split_bg_marker(content)
        if _is_bg and _bg_cmd:
            try:
                from core.tools.bg_jobs import launch as _launch_bg
                rec = _launch_bg(_bg_cmd, session_id=session_id)
            except ImportError:
                return "bash (background)", {"error": "bg_jobs module not available", "exit_code": 1}
            short = _bg_cmd.strip().split(chr(10))[0][:80]
            desc = f"bash (background): {short}"
            result = {
                "output": (
                    f"Started background job `{rec['id']}`. It is running detached — "
                    f"do NOT wait for it or poll it. You will be automatically re-invoked "
                    f"with its full output when it finishes. Continue with other work, or "
                    f"end your turn now and resume when the result arrives."
                ),
                "exit_code": 0,
                "bg_job_id": rec["id"],
            }
            logger.info(f"Tool executed: {desc} -> bg job {rec['id']}")
            return desc, result

    handler = _TOOL_HANDLERS.get(tool)
    if handler is not None:
        desc, result = await handler(content, session_id=session_id, owner=owner, progress_cb=progress_cb, context=context)
    elif tool.startswith("mcp__"):
        mcp = get_mcp_manager()
        if mcp:
            try:
                args = json.loads(content) if content.strip().startswith("{") else {}
            except (json.JSONDecodeError, TypeError):
                args = {}
            # Resolve artifact: prefixed attachment refs for email tools
            if tool == "mcp__email__send_email" and args.get("attachments") and context is not None:
                args["attachments"] = _resolve_artifact_attachments(args["attachments"], context)
            desc = f"mcp: {tool}"
            result = await mcp.call_tool(tool, args)
            # Register sent email as artifact
            if tool == "mcp__email__send_email" and isinstance(result, dict) and result.get("sent") and context is not None:
                _artifacts = await _register_email_artifact(result, context)
                if _artifacts:
                    result["_artifacts"] = _artifacts
        else:
            desc = f"mcp: {tool}"
            result = {"error": "MCP manager not available", "exit_code": 1}
    else:
        desc = f"unknown: {tool}"
        result = {"error": f"Unknown tool type: {tool}", "exit_code": 1}

    logger.info(f"Tool executed: {desc} -> exit_code={result.get('exit_code', 'n/a')}")
    return desc, result


# ---------------------------------------------------------------------------
# Result formatting
# ---------------------------------------------------------------------------

# Keys handled by the dedicated branches below — never echo them as raw JSON.
_FORMATTER_HANDLED_KEYS = {
    "stdout", "stderr", "exit_code", "content", "size",
    "response", "results", "session_id", "name", "model", "session_name",
    "success", "path", "action", "title", "doc_id", "version", "applied",
    "error", "output", "failed", "details", "diff", "format", "verify",
    "test_suggestions", "files_edited", "total_applied", "total_failed",
}

_ERROR_PATTERNS: list[tuple[str, str]] = [
    (r"Traceback \(most recent call last\)", "python_exception"),
    (r"Error:?\s", "generic_error"),
    (r"SyntaxError", "python_syntax_error"),
    (r"ImportError|ModuleNotFoundError", "python_import_error"),
    (r"FileNotFoundError|No such file or directory", "file_not_found"),
    (r"Permission denied", "permission_error"),
    (r"FAILED|FAILURES", "test_failure"),
    (r"AssertionError|assert ", "assertion_failure"),
    (r"cannot find module|Cannot find name", "module_not_found"),
    (r"is not assignable to type", "typescript_type_error"),
    (r"error CS\d+:", "csharp_error"),
    (r"Error: listen EADDRINUSE|port.*already in use", "port_in_use"),
    (r"Error: connect ECONNREFUSED", "connection_refused"),
    (r"npm ERR!|pip install.*error", "package_install_error"),
]


def _detect_errors(text: str) -> list[str]:
    """Return a list of error categories found in ``text``."""
    if not text:
        return []
    found: list[str] = []
    for pattern, label in _ERROR_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            found.append(label)
    return found


def format_tool_result(description: str, result: dict) -> str:
    """Format a tool result into text for feeding back to the LLM."""
    parts = [f"### {description}"]

    if "stdout" in result:
        if result["stdout"]:
            parts.append(f"**stdout:**\n```\n{result['stdout']}\n```")
        if result["stderr"]:
            parts.append(f"**stderr:**\n```\n{result['stderr']}\n```")
        parts.append(f"**exit_code:** {result.get('exit_code', 'unknown')}")
    elif "output" in result:
        # bash / python canonical result shape: {"output": ..., "exit_code": ...}
        parts.append(f"```\n{result['output']}\n```")
        if result.get("exit_code") not in (0, None):
            parts.append(f"**exit_code:** {result['exit_code']}")
    elif "content" in result:
        parts.append(f"**content ({result.get('size', '?')} chars):**\n```\n{result['content']}\n```")
    elif "response" in result:
        model = result.get("model", result.get("session_name", ""))
        if model:
            parts.append(f"**{model} responded:**\n{result['response']}")
        else:
            parts.append(result["response"])
    elif "results" in result:
        parts.append(result["results"])
    elif "session_id" in result and "name" in result:
        parts.append(f"Session created: **{result['name']}** (id: `{result['session_id']}`, model: {result.get('model', 'unknown')})")
    elif "success" in result:
        if result["success"]:
            parts.append(f"File written: {result['path']} ({result['size']} bytes)")
        else:
            parts.append(f"Error: {result.get('error', 'unknown')}")
    elif "action" in result:
        action = result["action"]
        if action == "create":
            parts.append(f"Document created: \"{result.get('title', '')}\" (id: {result['doc_id']}, v{result['version']})")
        elif action == "update":
            parts.append(f"Document updated: \"{result.get('title', '')}\" (v{result['version']})")
        elif action == "edit":
            details = result.get("details", [])
            summary = f'Document edited: "{result.get("title", "")}" (v{result.get("version", "?")})'
            if details:
                ok_count = sum(1 for d in details if d["status"] == "ok")
                verify_count = sum(1 for d in details if d["status"] == "verify")
                fail_count = sum(1 for d in details if d["status"] not in ("ok", "verify"))
                summary += f" — {ok_count} applied"
                if verify_count:
                    summary += f", {verify_count} warnings"
                if fail_count:
                    summary += f", {fail_count} failed"
                    fail_lines = []
                    for d in details:
                        if d["status"] not in ("ok", "verify"):
                            fail_lines.append(f"  - NOT FOUND: {d.get('find_preview', '?')}")
                    summary += "\n" + "\n".join(fail_lines)
                # Show verification warnings inline
                for d in details:
                    if d["status"] == "verify" and d.get("note"):
                        summary += f"\n  ⚠ {d['note']}"
                match_types = [d.get("match") for d in details if d.get("match") and d["status"] == "ok"]
                if match_types and any(m != "exact" for m in match_types):
                    summary += f" (matches: {', '.join(m for m in set(match_types) if m != 'exact')})"
            parts.append(summary)
        elif action == "edit_file":
            details = result.get("details", [])
            summary = f'File edited: {result.get("path", "?")} ({result.get("size", 0)} bytes)'
            if details:
                ok_count = sum(1 for d in details if d["status"] == "ok")
                verify_count = sum(1 for d in details if d["status"] == "verify")
                fail_count = sum(1 for d in details if d["status"] not in ("ok", "verify"))
                summary += f" — {ok_count} applied"
                if verify_count:
                    summary += f", {verify_count} warnings"
                if fail_count:
                    summary += f", {fail_count} failed"
                    fail_lines = []
                    for d in details:
                        if d["status"] not in ("ok", "verify"):
                            fail_lines.append(f"  - NOT FOUND: {d.get('find_preview', '?')}")
                    summary += "\n" + "\n".join(fail_lines)
                for d in details:
                    if d["status"] == "verify" and d.get("note"):
                        summary += f"\n  ⚠ {d['note']}"
            parts.append(summary)
            # Diff preview
            diff_text = result.get("diff", "")
            if diff_text:
                diff_lines = diff_text.split("\n")
                if len(diff_lines) > 50:
                    diff_text = "\n".join(diff_lines[:50]) + f"\n... ({len(diff_lines) - 50} more lines)"
                parts.append(f"**diff:**\n```diff\n{diff_text}\n```")
            # Format info
            fmt = result.get("format")
            if fmt:
                parts.append(f"_Auto-formatted with {fmt}_")
            # Verify note
            vn = result.get("verify")
            if vn:
                parts.append(f"⚠ {vn}")
            # Test suggestions
            tests = result.get("test_suggestions")
            if tests:
                test_str = ", ".join(tests)
                parts.append(f"> Suggested tests: {test_str}")
        elif action == "batch_edit_file":
            parts.append(f'Batch edit: {result.get("files_edited", 0)} files edited, {result.get("total_applied", 0)} edits applied, {result.get("total_failed", 0)} failed')
            for res in result.get("results", []):
                p = res.get("path", "?")
                a = res.get("applied", 0)
                f = res.get("failed", 0)
                err = res.get("error")
                if err:
                    parts.append(f"  - {p}: ERROR {err}")
                elif a > 0:
                    parts.append(f"  - {p}: {a} applied" + (f", {f} failed" if f else ""))
                else:
                    parts.append(f"  - {p}: no matches")
        elif action == "undo_edit_file":
            parts.append(f'Restored: {result.get("path", "?")} ({result.get("size", 0)} bytes)')
    elif "error" in result:
        parts.append(f"**Error:** {result['error']}")

    # Error detection: scan result text for common error patterns
    _scan_text = ""
    if "stderr" in result:
        _scan_text += "\n" + str(result["stderr"])
    if "output" in result:
        _scan_text += "\n" + str(result["output"])
    if result.get("exit_code") not in (None, 0):
        _scan_text += f"\nexit_code={result['exit_code']}"
    if "error" in result and isinstance(result["error"], str):
        _scan_text += "\n" + result["error"]
    if "content" in result and isinstance(result["content"], str):
        _scan_text += "\n" + result["content"]
    if _scan_text:
        err_categories = _detect_errors(_scan_text)
        if err_categories:
            parts.append(f"> Error categories: {', '.join(err_categories)}")
            # Auto-fix hint: extract file:line references from stderr/output
            fix_hints = []
            for m in re.finditer(r'(?:File\s+"([^"]+)",\s*line\s+(\d+)|at\s+(\S+):(\d+):\d+)', _scan_text):
                fpath = m.group(1) or m.group(3)
                fline = m.group(2) or m.group(4)
                if fpath and fline:
                    fix_hints.append(f"`read_file {fpath}:{fline}`")
            if fix_hints:
                unique_hints = list(dict.fromkeys(fix_hints))
                parts.append(f"> Suggested: {' '.join(unique_hints)} — read the error location to see the context")

    # Surface any additional structured payload (events, tasks, notes, calendars,
    # documents, attachments, etc.) that the dedicated branches above don't show.
    # Without this, tools that return {"response": "...", "events": [...]} would
    # silently drop the events list and the model would only see the summary line.
    extra = {k: v for k, v in result.items() if k not in _FORMATTER_HANDLED_KEYS}
    if extra:
        try:
            extra_json = json.dumps(extra, indent=2, default=str, ensure_ascii=False)
            # Cap to avoid blowing the context window on huge payloads.
            if len(extra_json) > 8000:
                extra_json = extra_json[:8000] + f"\n... (truncated, {len(extra_json)} chars total)"
            parts.append(f"**data:**\n```json\n{extra_json}\n```")
        except (TypeError, ValueError) as _e:
            logger.debug("[core.tools.execution] _format_result extra_json serialization failed: %s", _e)

    return "\n".join(parts)
