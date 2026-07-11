import asyncio
import json as _json
import logging
import os
import sys

from core.config_schema import jarvis_config
from core.sandbox.docker_sandbox import docker_sandbox as _docker_sandbox

from core.tools.execution.security import _resolve_tool_path
from core.tools.execution.subprocess import (
    _run_subprocess_streaming,
    DEFAULT_BASH_TIMEOUT,
    DEFAULT_PYTHON_TIMEOUT,
)
from core.tools._constants import MAX_OUTPUT_CHARS, MAX_READ_CHARS

logger = logging.getLogger(__name__)

_BG_MARKERS = {"#!bg", "#bg", "# bg", "#background", "# background", "@background", "# @background"}


def _split_bg_marker(content: str):
    lines = content.split("\n")
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i < len(lines) and lines[i].strip().lower() in _BG_MARKERS:
        del lines[i]
        return True, "\n".join(lines).strip()
    return False, content


def _truncate(text: str, limit: int = MAX_OUTPUT_CHARS) -> str:
    if len(text) > limit:
        return text[:limit] + f"\n... (truncated, {len(text)} chars total)"
    return text


async def _direct_fallback(
    tool: str,
    content: str,
    progress_cb=None,
    session_id: str | None = None,
) -> dict | None:
    _subproc_env = {
        **os.environ,
        "TERM": "xterm-256color",
        "COLUMNS": "120",
        "LINES": "40",
    }

    try:
        if tool == "bash":
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
            from core.sandbox.sandbox_manager import sandbox_manager
            if jarvis_config.sandbox.enabled:
                res = await sandbox_manager.exec(session_id or "default", tool, ["python", "-c", content])
                if res["success"]:
                    output = res["stdout"].rstrip()
                    return {"output": output or "(no output)", "exit_code": res["exit_code"]}
                else:
                    return {"error": res["error"], "exit_code": 1}

            proc = await asyncio.create_subprocess_exec(
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

            try:
                from core.tools.hot_files import touch_file
                base = raw_path.split(":")[0] if ":" in raw_path else raw_path
                touch_file(base, session_id=session_id or "default")
            except Exception as e:
                logger.warning("execute_tool failed: %s", e)

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
                    logger.debug("parse line range failed: %s", _e)

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
            try:
                from core.tools.hot_files import touch_file
                touch_file(str(path), session_id=session_id or "default")
            except Exception as e:
                logger.warning("process_tool_result failed: %s", e)
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
                logger.warning("web_search: src.search not available (%s)", e)
                return {"error": "web_search module not available", "exit_code": 1}
            raw = content.strip()
            query = raw
            time_filter = None
            max_pages = 5
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
                    logger.debug("web_search extra config JSON parse failed: %s", _e)
            if not query:
                query = raw.split("\n")[0].strip()
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
            try:
                from src.search.content import fetch_webpage_content
            except ImportError as e:
                logger.warning("web_fetch: src.search.content not available (%s)", e)
                return {"error": "web_fetch module not available", "exit_code": 1}
            raw = content.strip()
            url = ""
            if raw.startswith("{"):
                try:
                    parsed = _json.loads(raw)
                    if isinstance(parsed, dict):
                        url = str(parsed.get("url") or "").strip()
                except _json.JSONDecodeError:
                    url = ""
            if not url:
                url = raw.split("\n")[0].strip()
            if not url or url.startswith("{") or any(c in url for c in (" ", "\t", "\n")):
                return {"error": "web_fetch: provide a single URL or domain, e.g. example.com", "exit_code": 1}
            low = url.lower()
            if "://" in low and not low.startswith(("http://", "https://")):
                return {"error": f"web_fetch: unsupported URL scheme (only http/https): {url[:80]}", "exit_code": 1}
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
                return {"error": f"web_fetch: {url}: {e}", "exit_code": 1}
            err = result.get("error")
            text = (result.get("content") or "").strip()
            title = result.get("title") or ""

            if not text:
                if err:
                    return {"error": f"web_fetch: {url}: {err}", "exit_code": 1}
                return {"error": f"web_fetch: {url}: no readable text content (not HTML, or the page needs JS/login)", "exit_code": 1}

            header = (f"# {title}\n" if title else "") + f"Source: {url}\n\n"
            output = header + text
            if len(output) > MAX_OUTPUT_CHARS:
                output = output[:MAX_OUTPUT_CHARS] + "\n\n[...truncated]"
            return {"output": output, "exit_code": 0}

    except Exception as e:
        return {"error": f"{tool}: {e}", "exit_code": 1}

    return None
