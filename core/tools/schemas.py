"""
tool_schemas.py

OpenAI-compatible function tool schemas and the converter that turns
native function calls back into ToolBlocks for the execution pipeline.

Extracted from agent_tools.py to keep schema definitions separate from
tool parsing / execution logic.
"""

import json
import logging
from typing import Optional

from core.tools._constants import ToolBlock, TOOL_TAGS
from core.tools.parsing import _TOOL_NAME_MAP
from core.tools.validation import validate_tool_call

from core.tools.schemas_shell_web import FUNCTION_TOOL_SCHEMAS as _SHELL_WEB
from core.tools.schemas_document import FUNCTION_TOOL_SCHEMAS as _DOCUMENT
from core.tools.schemas_chat import FUNCTION_TOOL_SCHEMAS as _CHAT
from core.tools.schemas_admin import FUNCTION_TOOL_SCHEMAS as _ADMIN
from core.tools.schemas_calendar import FUNCTION_TOOL_SCHEMAS as _CALENDAR
from core.tools.schemas_model import FUNCTION_TOOL_SCHEMAS as _MODEL
from core.tools.schemas_research import FUNCTION_TOOL_SCHEMAS as _RESEARCH
from core.tools.schemas_email import FUNCTION_TOOL_SCHEMAS as _EMAIL

logger = logging.getLogger(__name__)

FUNCTION_TOOL_SCHEMAS = (
    _SHELL_WEB + _DOCUMENT + _CHAT + _ADMIN + _CALENDAR + _MODEL + _RESEARCH + _EMAIL
)


def function_call_to_tool_block(name: str, arguments: str) -> Optional[ToolBlock]:
    """Convert a native function call into a ToolBlock for the existing execution pipeline."""
    try:
        if not arguments or (isinstance(arguments, str) and not arguments.strip()):
            args = {}
        else:
            args = json.loads(arguments) if isinstance(arguments, str) else arguments
    except (json.JSONDecodeError, TypeError):
        logger.error(f"Failed to parse function call arguments for {name}: {arguments}")
        return None

    if not isinstance(args, dict):
        logger.warning(f"Non-object function call arguments for {name}: {args!r}; treating as empty")
        args = {}

    valid, err = validate_tool_call(name, args)
    if not valid:
        logger.warning(f"Tool call validation failed for {name}: {err}")
        return None

    tool_type = _TOOL_NAME_MAP.get(name, name)

    if tool_type.startswith("mcp__"):
        content = json.dumps(args) if args else "{}"
        return ToolBlock(tool_type, content)
    _BUILTIN_EMAIL_TOOLS = {"list_email_accounts", "send_email", "list_emails", "read_email", "reply_to_email",
                            "archive_email", "delete_email", "mark_email_read", "bulk_email", "download_attachment"}
    if name in _BUILTIN_EMAIL_TOOLS:
        return ToolBlock(f"mcp__email__{name}", json.dumps(args) if args else "{}")
    if tool_type not in TOOL_TAGS:
        logger.warning(f"Unknown function call: {name}")
        return None

    if tool_type == "bash":
        content = args.get("command", "")
    elif tool_type == "python":
        content = args.get("code", "")
    elif tool_type == "web_search":
        queries = args.get("queries")
        if isinstance(queries, list) and queries:
            content = str(queries[0])
        elif queries:
            content = str(queries)
        else:
            content = args.get("query", "")
    elif tool_type == "read_file":
        content = args.get("path", "")
    elif tool_type == "watch_file":
        parts = [args.get("path", "")]
        interval = args.get("poll_interval")
        start = args.get("start_line")
        if interval is not None:
            parts.append(str(interval))
        elif start is not None:
            parts.append("")
        if start is not None:
            parts.append(str(start))
        content = "|".join(parts)
    elif tool_type == "write_file":
        content = args.get("path", "") + "\n" + args.get("content", "")
    elif tool_type == "create_document":
        parts = [args.get("title", "Untitled")]
        if args.get("language"):
            parts.append(args["language"])
        parts.append(args.get("content", ""))
        content = "\n".join(parts)
    elif tool_type == "edit_document":
        blocks = []
        for edit in args.get("edits", []):
            doc_id = edit.get("doc_id", "")
            if doc_id:
                blocks.append(
                    f'<<<FIND>>>\n{edit.get("find", "")}\n<<<REPLACE>>>\n{edit.get("replace", "")}\n<<<DOC_ID>>>\n{doc_id}\n<<<END>>>'
                )
            else:
                blocks.append(
                    f'<<<FIND>>>\n{edit.get("find", "")}\n<<<REPLACE>>>\n{edit.get("replace", "")}\n<<<END>>>'
                )
        content = "\n".join(blocks)
    elif tool_type == "edit_file":
        file_path = args.get("file_path", "")
        edits = args.get("edits", [])
        blocks = []
        for ed in edits:
            find_text = ed.get("find", "")
            replace_text = ed.get("replace", "")
            blocks.append(
                f'<<<FIND>>>\n{find_text}\n<<<REPLACE>>>\n{replace_text}\n<<<END>>>'
            )
        content = f"{file_path}\n" + "\n".join(blocks)
    elif tool_type == "undo_edit_file":
        content = args.get("path", "")
    elif tool_type == "batch_edit_file":
        pattern = args.get("pattern", "")
        edits = args.get("edits", [])
        blocks = []
        for ed in edits:
            find_text = ed.get("find", "")
            replace_text = ed.get("replace", "")
            blocks.append(
                f'<<<FIND>>>\n{find_text}\n<<<REPLACE>>>\n{replace_text}\n<<<END>>>'
            )
        content = f"{pattern}\n" + "\n".join(blocks)
    elif tool_type == "shell":
        cmd = args.get("command", "")
        timeout = args.get("timeout")
        content = cmd + ("\n" + str(timeout) if timeout is not None else "")
    elif tool_type == "close_shell":
        content = args.get("session_id", "")
    elif tool_type == "refactor":
        goal = args.get("goal", "")
        files = args.get("files", "")
        edits = args.get("edits", [])
        blocks = []
        for ed in edits:
            blocks.append(f'<<<FIND>>>\n{ed.get("find", "")}\n<<<REPLACE>>>\n{ed.get("replace", "")}\n<<<END>>>')
        content = goal + "\n" + files
        if blocks:
            content += "\n" + "\n".join(blocks)
    elif tool_type == "semantic_search":
        parts = [args.get("query", "")]
        k = args.get("k")
        if k is not None:
            parts.append(str(k))
        content = "\n".join(parts)
    elif tool_type == "suggest_document":
        blocks = []
        for s in args.get("suggestions", []):
            blocks.append(
                f'<<<FIND>>>\n{s.get("find", "")}\n<<<SUGGEST>>>\n{s.get("replace", "")}\n<<<REASON>>>\n{s.get("reason", "")}\n<<<END>>>'
            )
        content = "\n".join(blocks)
    elif tool_type == "update_document":
        content = args.get("content", "")
    elif tool_type == "search_chats":
        content = args.get("query", "")
    elif tool_type == "chat_with_model":
        content = args.get("model", "") + "\n" + args.get("message", "")
    elif tool_type == "create_session":
        content = args.get("name", "Untitled") + "\n" + args.get("model", "")
    elif tool_type == "list_sessions":
        content = args.get("filter", "")
    elif tool_type == "send_to_session":
        content = args.get("session_id", "") + "\n" + args.get("message", "")
    elif tool_type == "pipeline":
        content = json.dumps({"steps": args.get("steps", [])})
    elif tool_type == "manage_session":
        action = args.get("action", "")
        value = args.get("value", "")
        if action == "list":
            keyword = args.get("session_id", "") or args.get("keyword", "") or value
            content = "list" + (("\n" + keyword) if keyword and keyword.lower() != "current" else "")
        else:
            sid = args.get("session_id", "current")
            content = action + "\n" + sid
            if value:
                content += "\n" + value
    elif tool_type == "manage_memory":
        action = args.get("action", "")
        if action == "add":
            content = "add\n" + args.get("text", "")
            if args.get("category"):
                content += "\n" + args["category"]
        elif action == "edit":
            content = "edit\n" + args.get("memory_id", "") + "\n" + args.get("text", "")
        elif action == "delete":
            content = "delete\n" + args.get("memory_id", "")
        elif action == "search":
            content = "search\n" + args.get("text", "")
        elif action == "list":
            content = "list"
            if args.get("category"):
                content += "\n" + args["category"]
        else:
            content = action
    elif tool_type == "list_models":
        content = args.get("filter", "")
    elif tool_type == "ui_control":
        action = args.get("action", "")
        name = args.get("name", "")
        value = args.get("value", "")
        if action == "toggle":
            content = f"toggle {name} {value}"
        elif action == "open_panel":
            content = f"open_panel {name or value}"
        elif action == "open_email_reply":
            uid = args.get("uid") or name
            folder = args.get("folder") or value or "INBOX"
            mode = args.get("mode") or "reply"
            content = f"open_email_reply {uid} {folder} {mode}"
        elif action == "set_mode":
            content = f"set_mode {value or name}"
        elif action == "switch_model":
            content = f"switch_model {value or name}"
        elif action == "set_theme":
            content = f"set_theme {value or name}"
        elif action == "create_theme":
            colors = args.get("colors", {})
            theme_name = name or value or "custom"
            bg = colors.get("bg", "#282c34")
            fg = colors.get("fg", "#9cdef2")
            panel = colors.get("panel", "#111111")
            border = colors.get("border", "#355a66")
            accent = colors.get("accent", "#e06c75")
            content = f"create_theme {theme_name} {bg} {fg} {panel} {border} {accent}"
            adv_keys = [
                "userBubbleBg", "aiBubbleBg", "bubbleBorder", "sidebarBg",
                "sectionAccent", "brandColor", "inputBg", "inputBorder",
                "sendBtnBg", "sendBtnHover", "codeBg", "codeFg",
                "toggleBg", "toggleActive", "accentPrimary", "accentError",
            ]
            for ak in adv_keys:
                if colors.get(ak):
                    content += f" {ak}={colors[ak]}"
        else:
            content = action
    elif tool_type in ("manage_tasks", "manage_skills", "api_call",
                        "manage_endpoints", "manage_mcp", "manage_webhooks",
                        "manage_tokens", "manage_documents", "manage_settings",
                        "sessions_spawn"):
        content = json.dumps(args)
    elif tool_type == "ask_teacher":
        content = args.get("model", "auto") + "\n" + args.get("problem", "")
    else:
        content = json.dumps(args)

    return ToolBlock(tool_type, content)
