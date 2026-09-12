"""Tool execution dispatch: block → handler → verified result.

Completed from the committed contracts in tests/unit/test_execution_dispatch.py,
tests/contract/test_tool_dispatch_fuzz.py and
tests/unit/test_workflow_email_artifacts.py (the auto-reconstructed stub that
previously occupied this file silently swallowed every call).

Dispatch order for ``execute_tool_block(block, ...)``:
1. misformatted JSON in a python block → blocked
2. disabled_tools → blocked
3. RBAC via core.authz (unknown tool → blocked)
4. plugin handlers (_PLUGIN_TOOL_HANDLERS)
5. mcp__server__tool → MCP manager (module-level for patchability)
6. email send tools → artifact registration on success
7. core.tools.implementations.do_<tool> / async_do_<tool>

Path helpers (_tool_path_roots/_resolve_tool_path/_is_sensitive_path) enforce
the existing filesystem safety boundary: tool file access stays inside allowed
roots and away from credential/shell-config paths.  This module never widens
permissions — it only consults the existing authz/policy engines.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable, Optional

from core.constants import DATA_DIR

logger = logging.getLogger(__name__)

BROKEN_TOOLS = "BROKEN_TOOLS"
MAX_OUTPUT_CHARS = 1000

# Tools known to be broken (dispatch refuses them with a clear error).
_BROKEN_TOOL_SET: set[str] = set()

# Plugin tool handlers (overridable at runtime via register_plugin_tool).
_PLUGIN_TOOL_HANDLERS: dict[str, Callable[..., Any]] = {}


# ── Output helpers ──────────────────────────────────────────────────────────


def _truncate(text: str, limit: int = MAX_OUTPUT_CHARS) -> str:
    """Truncate long output with a visible marker (never crashes)."""
    try:
        text = str(text)
    except Exception:
        text = repr(text)
    if len(text) <= limit:
        return text
    return f"{text[: max(0, limit - 60)]} ... [truncated {len(text) - limit} chars)"


def _result(exit_code: int = 0, output: str = "", error: str = "", **extra: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "exit_code": exit_code,
        "output": _truncate(output),
    }
    if error:
        result["error"] = _truncate(error)
    result.update(extra)
    return result


# ── Sensitive-path protection (existing safety boundary) ────────────────────

_SENSITIVE_DIRS = {
    ".ssh", ".gnupg", ".gpg", ".gitconfig", ".git-credentials",
    ".bashrc", ".bash_profile", ".bash_logout", ".zshrc", ".zprofile",
    ".zshenv", ".profile", ".tcshrc", ".cshrc", ".env", ".netrc",
    ".aws", ".kube", ".docker",
}

_SENSITIVE_FILES = {
    "authorized_keys", "id_rsa", "id_ed25519", "id_ecdsa", "id_dsa",
    "known_hosts", ".netrc", ".git-credentials", ".npmrc", ".pypirc",
}


def _is_sensitive_path(path: str) -> bool:
    """True when a path touches credentials or shell-config locations."""
    try:
        if not path:
            return False
        normalized = os.path.normpath(str(path))
        parts = [p for p in normalized.replace("\\", "/").split("/") if p]
        for part in parts[:-1]:
            if part.lower() in _SENSITIVE_DIRS:
                return True
        name = parts[-1].lower() if parts else ""
        if name in _SENSITIVE_FILES or name in _SENSITIVE_DIRS:
            return True
        return False
    except Exception:
        return False


def _tool_path_roots() -> list[str]:
    """Absolute roots tool file operations are confined to.

    ``tempfile.gettempdir()`` is consulted live (never cached at import time)
    so test/process TMPDIR overrides are honoured.
    """
    try:
        data_root = str(Path(DATA_DIR).resolve()) if DATA_DIR else ""
    except Exception:
        data_root = str(Path.cwd() / "data")
    try:
        temp_root = tempfile.gettempdir()
    except Exception:
        temp_root = ""
    # Cross-platform scratch root inside the data boundary (on Windows the
    # system temp dir may not contain a literal "tmp" component).
    try:
        scratch = Path(DATA_DIR) / "tmp" if DATA_DIR else Path.cwd() / "data" / "tmp"
        scratch.mkdir(parents=True, exist_ok=True)
        scratch_root = str(scratch.resolve())
    except Exception:
        scratch_root = ""
    roots = [data_root, scratch_root, temp_root, str(Path.cwd())]
    return [os.path.abspath(r) for r in roots if r]


def _resolve_tool_path(path: str) -> str:
    """Resolve a tool-supplied path, refusing empty/escaped/sensitive paths."""
    if path is None or not str(path).strip():
        raise ValueError("path is required")
    raw = str(path).strip()
    expanded = os.path.expanduser(raw)
    resolved = os.path.realpath(expanded)
    if _is_sensitive_path(resolved):
        raise ValueError(f"path is in a sensitive directory: {raw}")
    if not os.path.isabs(expanded):
        for root in _tool_path_roots():
            if resolved.startswith(os.path.realpath(root)):
                return resolved
        raise ValueError(f"path is outside allowed tool roots: {raw}")
    for root in _tool_path_roots():
        if resolved.startswith(os.path.realpath(root)):
            return resolved
    raise ValueError(f"path is outside allowed tool roots: {raw}")


# ── MCP + email integration points (imported lazily where needed) ───────────


def get_mcp_manager() -> Any:
    """Return the MCP manager when the real one is importable, else None."""
    try:
        from core.mcp_manager import MCPManager  # noqa: F401  (real layer: jarvis_mcp/)
        return MCPManager()
    except Exception:
        return None


def _register_email_artifact(result: dict[str, Any], args: dict[str, Any]) -> Optional[str]:
    """Register a sent email as an artifact; artifact id or None on failure."""
    try:
        if not result or result.get("sent") is False or result.get("success") is False:
            return None
        from core.workflow.artifacts import register_email_artifact  # existing store
        return register_email_artifact(result, args)
    except Exception as exc:
        logger.debug("[execution] email artifact registration failed: %s", exc)
        return None


def _resolve_artifact_attachments(args: dict[str, Any]) -> dict[str, Any]:
    """Replace ``artifact:<id>`` attachment refs with real file paths."""
    resolved = dict(args or {})
    attachments = resolved.get("attachments")
    if not isinstance(attachments, list):
        return resolved
    fixed: list[str] = []
    for item in attachments:
        if isinstance(item, str) and item.startswith("artifact:"):
            ref = item.split(":", 1)[1]
            try:
                from core.workflow.artifacts import resolve_artifact_path
                path = resolve_artifact_path(ref)
            except Exception:
                try:
                    from core.workflow.artifact_store import resolve_artifact_path
                    path = resolve_artifact_path(ref)
                except Exception:
                    path = None
            if path:
                fixed.append(str(path))
        else:
            fixed.append(item)
    resolved["attachments"] = fixed
    return resolved


# ── Plugin tool registration ────────────────────────────────────────────────


def register_plugin_tool(name: str, handler: Callable[..., Any]) -> None:
    _PLUGIN_TOOL_HANDLERS[name] = handler


async def async_register_plugin_tool(name: str, handler: Callable[..., Any]) -> None:
    register_plugin_tool(name, handler)


def unregister_plugin_tool(name: str) -> None:
    _PLUGIN_TOOL_HANDLERS.pop(name, None)


async def async_unregister_plugin_tool(name: str) -> None:
    unregister_plugin_tool(name)


def _direct_fallback(tool_type: str, content: str) -> dict[str, Any]:
    """Last-resort result for tools with no registered implementation."""
    return _result(
        exit_code=1,
        error=f"tool '{tool_type}' has no registered handler",
        output="",
    )


# ── Subprocess streaming (used by shell-type tools) ─────────────────────────


def _run_subprocess_streaming(
    command: str,
    cwd: Optional[str] = None,
    timeout: float = 120.0,
) -> dict[str, Any]:
    """Run a shell command synchronously, returning stdout/stderr/exit_code."""
    try:
        proc = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
        )
        return _result(
            exit_code=proc.returncode,
            output=proc.stdout or "",
            error=proc.stderr or "",
        )
    except subprocess.TimeoutExpired:
        return _result(exit_code=1, error=f"command timed out after {timeout}s")
    except Exception as exc:
        return _result(exit_code=1, error=f"{type(exc).__name__}: {exc}")


# ── Main dispatch ───────────────────────────────────────────────────────────


def _looks_like_json(content: str) -> bool:
    text = (content or "").strip()
    return text.startswith("{") or text.startswith("[")


def _rbac_allows(tool_type: str, owner: Optional[str]) -> bool:
    """Consult the existing authz/policy engines; unknown tools are denied.

    The existing single-user security model (core.tools.security) governs the
    default: an admin/single-user owner passes the authz gate; a non-admin
    owner must be explicitly granted the tool scope.  This gate only ever
    narrows execution — it never widens permissions.
    """
    try:
        from core.authz import AuthContext
        from core.authz.engine import authz_engine
        from core.tools.security import owner_is_admin_or_single_user
        if owner_is_admin_or_single_user(owner):
            context = AuthContext(
                user_id=owner or "single_user",
                scopes={"tools:execute:*"},
            )
        else:
            context = AuthContext(user_id=str(owner or "user"), scopes=set())
        return bool(authz_engine.evaluate(context, "tools:execute:" + tool_type))
    except Exception as exc:
        logger.debug("[execution] authz unavailable, denying %s: %s", tool_type, exc)
        return False


async def execute_tool_block(
    block: Any,
    owner: Optional[str] = None,
    execution_context: Optional[dict[str, Any]] = None,
    disabled_tools: Optional[set[str]] = None,
) -> tuple[str, dict[str, Any]]:
    """Execute one tool block, returning (description, result dict)."""
    tool_type = str(getattr(block, "tool_type", "") or "")
    content = str(getattr(block, "content", "") or "")

    # 1. Misformatted JSON inside a python block is never executed.
    if tool_type == "python" and _looks_like_json(content):
        return (
            "BLOCKED: misformatted tool call (JSON content in python block)",
            _result(exit_code=1, error="misformatted tool call: JSON in python block"),
        )

    # 2. Explicitly disabled tools.
    if disabled_tools and tool_type in disabled_tools:
        return (
            f"BLOCKED: tool '{tool_type}' is disabled",
            _result(exit_code=1, error=f"tool '{tool_type}' is disabled"),
        )

    # 3. RBAC gate (also denies unknown tools with no handler).
    known = (
        tool_type in _PLUGIN_TOOL_HANDLERS
        or tool_type.startswith("mcp__")
        or tool_type in _BROKEN_TOOL_SET
        or _has_implementation(tool_type)
    )
    if not known or not _rbac_allows(tool_type, owner):
        label = "unknown tool (no handler)" if not known else f"tool '{tool_type}' denied by RBAC"
        return (
            f"BLOCKED: {label}",
            _result(exit_code=1, error=label),
        )

    if tool_type in _BROKEN_TOOL_SET:
        return (
            f"BLOCKED: tool '{tool_type}' is marked broken",
            _result(exit_code=1, error=BROKEN_TOOLS),
        )

    # 4. Plugin handlers win (override built-ins).
    handler = _PLUGIN_TOOL_HANDLERS.get(tool_type)
    if handler is not None:
        try:
            outcome = handler(content)
            if hasattr(outcome, "__await__"):
                outcome = await outcome
            outcome = outcome if isinstance(outcome, dict) else {"result": outcome}
            return f"plugin tool '{tool_type}' executed", dict(outcome)
        except Exception as exc:
            return (
                f"plugin tool '{tool_type}' failed",
                _result(exit_code=1, error=f"{type(exc).__name__}: {exc}"),
            )

    # 5. MCP tools: mcp__server__tool.
    if tool_type.startswith("mcp__"):
        return await _dispatch_mcp(tool_type, content)

    # 6. Built-in implementations.
    return await _dispatch_implementation(tool_type, content, owner)


async def _dispatch_mcp(tool_type: str, content: str) -> tuple[str, dict[str, Any]]:
    parts = tool_type.split("__")
    server = parts[1] if len(parts) > 1 else ""
    tool = parts[2] if len(parts) > 2 else tool_type
    manager = get_mcp_manager()
    if manager is None:
        return (
            f"mcp tool '{tool_type}' unavailable (no manager)",
            _result(exit_code=1, error="mcp manager unavailable"),
        )
    try:
        args = json.loads(content) if _looks_like_json(content) else {}
        if not isinstance(args, dict):
            args = {"input": content}
        args = _resolve_artifact_attachments(args)
        result = await manager.call_tool(server, tool, args)
        result = result if isinstance(result, dict) else {"result": result}
        if server == "email" and tool in ("send_email", "email_send"):
            artifact_id = _register_email_artifact(result, args)
            if artifact_id:
                result["artifact_id"] = artifact_id
        return f"mcp tool '{tool_type}' executed", result
    except Exception as exc:
        return (
            f"mcp tool '{tool_type}' failed",
            _result(exit_code=1, error=f"{type(exc).__name__}: {exc}"),
        )


def _has_implementation(tool_type: str) -> bool:
    try:
        from core.tools import implementations
        return hasattr(implementations, f"do_{tool_type}") or hasattr(
            implementations, f"async_do_{tool_type}"
        )
    except Exception:
        return False


async def _dispatch_implementation(
    tool_type: str,
    content: str,
    owner: Optional[str],
) -> tuple[str, dict[str, Any]]:
    try:
        from core.tools import implementations
    except Exception as exc:
        return (
            f"tool '{tool_type}' unavailable",
            _result(exit_code=1, error=f"implementations unavailable: {exc}"),
        )

    func = getattr(implementations, f"async_do_{tool_type}", None) or getattr(
        implementations, f"do_{tool_type}", None
    )
    if func is None:
        return (
            f"unknown tool '{tool_type}'",
            _result(exit_code=1, error=f"unknown tool: {tool_type}"),
        )

    kwargs: dict[str, Any] = {}
    if _looks_like_json(content):
        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict):
                kwargs = parsed
        except Exception:
            kwargs = {}
    if not kwargs:
        kwargs = {"input": content}
    kwargs.setdefault("owner", owner)

    try:
        outcome = func(**kwargs)
        if hasattr(outcome, "__await__"):
            outcome = await outcome
        outcome = outcome if isinstance(outcome, dict) else {"result": outcome}
        return f"tool '{tool_type}' executed", dict(outcome)
    except Exception as exc:
        return (
            f"tool '{tool_type}' failed",
            _result(exit_code=1, error=f"{type(exc).__name__}: {exc}"),
        )


async def async_execute_tool_block(
    block: Any,
    owner: Optional[str] = None,
    execution_context: Optional[dict[str, Any]] = None,
    disabled_tools: Optional[set[str]] = None,
) -> tuple[str, dict[str, Any]]:
    """Async alias retained for existing importers."""
    return await execute_tool_block(
        block,
        owner=owner,
        execution_context=execution_context,
        disabled_tools=disabled_tools,
    )
