import asyncio
import base64
import json
import logging
import os
import re
import time
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from core.ai_interaction import dispatch_ai_tool
from core.tools.execution.authorization import check_rbac, check_approval
from core.tools.execution.direct_tools import _direct_fallback, _split_bg_marker, _truncate
from core.tools.execution.edit_tools import (
    do_edit_file,
    do_refactor,
    do_undo_edit_file,
    do_batch_edit_file,
)
from core.tools.execution.mcp import get_mcp_manager, _call_mcp_tool, _MCP_TOOL_MAP
from core.tools.execution.metrics import record_tool_metric
from core.tools.execution.plugins import _PLUGIN_TOOL_HANDLERS
from core.tools.execution.security import _resolve_tool_path
from core.tools.security import owner_is_admin_or_single_user

from core.tools.build_tools import (
    do_build_project,
    do_repair_project,
    do_run_tests,
    do_runtime_validate,
    cancel_build as do_cancel_build,
)
from core.tools.chat_tools import (
    do_manage_memory,
    do_create_session,
    do_chat_with_model,
)
from core.tools.sub_agent_spawn import do_sessions_spawn
from core.tools.workflow_tools import (
    do_workflow_start,
    do_workflow_resume,
    do_workflow_cancel,
    do_workflow_status,
    do_workflow_list,
)
from core.tools._constants import MAX_OUTPUT_CHARS, MAX_READ_CHARS

logger = logging.getLogger(__name__)

BROKEN_TOOLS: set[str] = set()

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
    return owner_is_admin_or_single_user(owner)


_BROWSER_ARTIFACT_DIR: str | None = None


def _ensure_browser_artifact_dir(wf_id: str) -> str:
    global _BROWSER_ARTIFACT_DIR
    if _BROWSER_ARTIFACT_DIR is None:
        base = Path(__file__).resolve().parent.parent.parent.parent / "data" / "workflow_artifacts"
        base.mkdir(parents=True, exist_ok=True)
        _BROWSER_ARTIFACT_DIR = str(base)
    wf_dir = os.path.join(_BROWSER_ARTIFACT_DIR, wf_id)
    os.makedirs(wf_dir, exist_ok=True)
    return wf_dir


def _resolve_artifact_attachments(attachments: list, ctx_any: Any) -> list:
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


def get_registered_tools() -> dict[str, str]:
    known = {}
    for t in _MCP_TOOL_MAP:
        known[t] = "mcp"
    from core.tools._constants import TOOL_TAGS
    for t in TOOL_TAGS:
        known[t] = "native"
    known.update({
        "edit_file": "native",
        "undo_edit_file": "native",
        "batch_edit_file": "native",
        "refactor": "native",
        "shell": "native",
        "shell_command": "native",
        "close_shell": "native",
        "semantic_search": "native",
        "watch_file": "native",
        "create_skill": "native",
        "sessions_spawn": "native",
        "automated_build": "native",
        "build_project": "native",
        "repair_project": "native",
        "run_tests": "native",
        "runtime_validate": "native",
        "cancel_build": "native",
        "manage_memory": "native",
        "create_session": "native",
        "chat_with_model": "native",
        "list_sessions": "native",
        "manage_session": "native",
        "list_models": "native",
        "ui_control": "native",
        "pipeline": "native",
        "send_to_session": "native",
        "ask_teacher": "native",
        "workflow_start": "native",
        "workflow_resume": "native",
        "workflow_cancel": "native",
        "workflow_status": "native",
        "workflow_list": "native",
        "agent_exec": "native",
        "browser_research": "native",
        "browser_get_facts": "native",
    })
    for t in _PLUGIN_TOOL_HANDLERS:
        known[t] = "plugin"
    return known


async def execute_tool_block(
    block: Any,
    session_id: str | None = None,
    disabled_tools: set | None = None,
    owner: str | None = None,
    progress_cb: Callable[[dict], Awaitable[None]] | None = None,
    context: Any | None = None,
) -> tuple[str, dict]:
    from core.action_engine import action_engine

    tool_type = block.tool_type
    content = block.content

    CORE_MAPPING = {
        "read_file": "read_file",
        "write_file": "write_file",
        "list_folder": "list_folder",
        "bash": "run_command",
        "shell": "run_command",
    }

    if tool_type in CORE_MAPPING:
        params = {}
        import json as _json
        try:
            parsed = _json.loads(content)
            if isinstance(parsed, dict):
                if tool_type in ("read_file", "list_folder"):
                    params = {"path": parsed.get("path", parsed.get("file", ""))}
                elif tool_type == "write_file":
                    params = {"path": parsed.get("path", ""), "content": parsed.get("content", "")}
                else:
                    params = {"command": parsed.get("command", parsed.get("code", content))}
        except (_json.JSONDecodeError, ValueError):
            if tool_type == "read_file":
                params = {"path": content.split("\n", 1)[0].strip()}
            elif tool_type == "write_file":
                lines = content.split("\n", 1)
                params = {"path": lines[0].strip(), "content": lines[1] if len(lines) > 1 else ""}
            elif tool_type == "list_folder":
                params = {"path": content.split("\n", 1)[0].strip()}
            else:
                params = {"command": content}

        res = await action_engine.execute(CORE_MAPPING[tool_type], params, session_id=session_id)
        desc = f"{tool_type}: {params.get('path', params.get('command', ''))[:60]}"
        return desc, {
            "output": res["result"],
            "error": res["error"],
            "exit_code": 0 if res["success"] else 1
        }

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
        do_manage_google_calendar,
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
        parts = content.split("|")
        path_str = parts[0].strip()
        start_line = int(parts[2]) if len(parts) > 2 and parts[2].strip() else -1
        try:
            rpath = _resolve_tool_path(path_str)
        except ValueError:
            return "watch_file: invalid path", {"error": "Invalid file path", "exit_code": 1}

        try:
            def _read():
                with open(rpath, encoding="utf-8", errors="replace") as f:
                    return f.read(MAX_READ_CHARS + 1)
            data = await asyncio.to_thread(_read)
        except FileNotFoundError:
            return "watch_file: not found", {"error": f"File not found: {rpath}", "exit_code": 1}
        except OSError:
            return "watch_file: read error", {"error": "Failed to read file", "exit_code": 1}

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

    async def _hdl_manage_google_calendar(content, session_id=None, owner=None, **kw):
        return "manage_google_calendar", await do_manage_google_calendar(content, owner=owner)

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

    async def _register_browser_artifacts(tool_type: str, result: dict, ctx_any: Any) -> dict[str, str]:
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

    _BUILD_DIR_CACHE: dict[str, str] = {}
    _BUILD_EXEC_ID: int = 0

    async def _register_build_artifacts(project_dir: str, ctx_any: Any, result: dict) -> dict[str, str]:
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

    async def _hdl_agent_exec(content, **kw):
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
        "manage_google_calendar": _hdl_manage_google_calendar,
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

    _BARE_EMAIL_TOOLS = {"send_email", "delete_email", "list_emails", "read_email",
                         "reply_to_email", "archive_email", "mark_email_read",
                         "bulk_email", "list_email_accounts"}
    if tool in _BARE_EMAIL_TOOLS:
        tool = f"mcp__email__{tool}"

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
            logger.debug("line range parse failed: %s", _e)

    if tool in BROKEN_TOOLS:
        desc = f"{tool}: DISABLED"
        result = {"status": "disabled", "reason": "not implemented", "exit_code": 1}
        logger.info("Tool disabled (not implemented): %s", tool)
        return desc, result

    if disabled_tools and tool in disabled_tools:
        desc = f"{tool}: BLOCKED"
        result = {"error": f"Tool '{tool}' is disabled by user.", "exit_code": 1}
        logger.info("Tool blocked by user: %s", tool)
        return desc, result

    authorized, auth_result = check_rbac(tool, owner)
    if not authorized:
        return f"{tool}: UNAUTHORIZED", auth_result

    approved, approval_result = await check_approval(tool, content)
    if not approved:
        return f"{tool}: DENIED", approval_result

    record_tool_metric(tool)

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
            logger.info("Tool executed: %s -> bg job %s", desc, rec['id'])
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
            if tool == "mcp__email__send_email" and args.get("attachments") and context is not None:
                args["attachments"] = _resolve_artifact_attachments(args["attachments"], context)
            desc = f"mcp: {tool}"
            result = await mcp.call_tool(tool, args)
            if tool == "mcp__email__send_email" and isinstance(result, dict) and result.get("sent") and context is not None:
                _artifacts = await _register_email_artifact(result, context)
                if _artifacts:
                    result["_artifacts"] = _artifacts
        else:
            desc = f"mcp: {tool}"
            result = {"error": "MCP manager not available", "exit_code": 1}
    elif tool in _PLUGIN_TOOL_HANDLERS:
        plugin_handler = _PLUGIN_TOOL_HANDLERS[tool]
        desc, result = await plugin_handler(content, session_id=session_id, owner=owner, progress_cb=progress_cb, context=context)
    else:
        desc = f"unknown: {tool}"
        result = {"error": f"Unknown tool type: {tool}", "exit_code": 1}

    logger.info("Tool executed: %s -> exit_code=%s", desc, result.get('exit_code', 'n/a'))
    return desc, result
