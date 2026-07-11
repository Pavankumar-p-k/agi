import json
import logging
import re

logger = logging.getLogger(__name__)

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
    if not text:
        return []
    found: list[str] = []
    for pattern, label in _ERROR_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            found.append(label)
    return found


def format_tool_result(description: str, result: dict) -> str:
    parts = [f"### {description}"]

    if "stdout" in result:
        if result["stdout"]:
            parts.append(f"**stdout:**\n```\n{result['stdout']}\n```")
        if result["stderr"]:
            parts.append(f"**stderr:**\n```\n{result['stderr']}\n```")
        parts.append(f"**exit_code:** {result.get('exit_code', 'unknown')}")
    elif "output" in result:
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
            diff_text = result.get("diff", "")
            if diff_text:
                diff_lines = diff_text.split("\n")
                if len(diff_lines) > 50:
                    diff_text = "\n".join(diff_lines[:50]) + f"\n... ({len(diff_lines) - 50} more lines)"
                parts.append(f"**diff:**\n```diff\n{diff_text}\n```")
            fmt = result.get("format")
            if fmt:
                parts.append(f"_Auto-formatted with {fmt}_")
            vn = result.get("verify")
            if vn:
                parts.append(f"⚠ {vn}")
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
            fix_hints = []
            for m in re.finditer(r'(?:File\s+"([^"]+)",\s*line\s+(\d+)|at\s+(\S+):(\d+):\d+)', _scan_text):
                fpath = m.group(1) or m.group(3)
                fline = m.group(2) or m.group(4)
                if fpath and fline:
                    fix_hints.append(f"`read_file {fpath}:{fline}`")
            if fix_hints:
                unique_hints = list(dict.fromkeys(fix_hints))
                parts.append(f"> Suggested: {' '.join(unique_hints)} — read the error location to see the context")

    extra = {k: v for k, v in result.items() if k not in _FORMATTER_HANDLED_KEYS}
    if extra:
        try:
            extra_json = json.dumps(extra, indent=2, default=str, ensure_ascii=False)
            if len(extra_json) > 8000:
                extra_json = extra_json[:8000] + f"\n... (truncated, {len(extra_json)} chars total)"
            parts.append(f"**data:**\n```json\n{extra_json}\n```")
        except (TypeError, ValueError) as _e:
            logger.debug("extra_json serialization failed: %s", _e)

    return "\n".join(parts)
