"""
agent_helpers.py

Helper functions extracted from agent_loop.py — prompt-independent utilities
for admin intent detection, message extraction, tool resolution, result
appending, verifier subagent, and the empty-response fallback.
"""

import json
import logging
import re
import time

from core.agent_tools import (
    function_call_to_tool_block,
    parse_tool_blocks,
)

logger = logging.getLogger(__name__)

# ── MCP disabled-tools cache ────────────────────────────────────────────

_mcp_disabled_cache: dict | None = None
_mcp_disabled_cache_ts: float = 0.0
_MCP_CACHE_TTL: float = 60.0


def _load_mcp_disabled_map() -> dict[str, set]:
    """Load per-server disabled tool sets from the database, cached for 60s."""
    global _mcp_disabled_cache, _mcp_disabled_cache_ts
    now = time.time()
    if _mcp_disabled_cache is not None and (now - _mcp_disabled_cache_ts) < _MCP_CACHE_TTL:
        return _mcp_disabled_cache
    from core.database_models import McpServer, SessionLocal
    disabled_map: dict[str, set] = {}
    db = SessionLocal()
    try:
        for srv in db.query(McpServer).all():
            if srv.disabled_tools:
                try:
                    names = json.loads(srv.disabled_tools)
                    if names:
                        disabled_map[srv.id] = set(names)
                except (json.JSONDecodeError, TypeError) as _e:
                    logger.warning("[agent_helpers] disabled tools decode failed: %s", _e)
    finally:
        db.close()
    _mcp_disabled_cache = disabled_map
    _mcp_disabled_cache_ts = time.time()
    return disabled_map


# ── Host / keyword constants ──────────────────────────────────────────

_API_HOSTS = frozenset([
    "api.openai.com", "api.anthropic.com",
    "openrouter.ai", "api.groq.com",
    "api.mistral.ai", "api.cohere.com",
    "api.deepseek.com", "deepseek.com",
    "api.together.xyz", "api.fireworks.ai",
    "api.perplexity.ai", "api.x.ai",
    "ollama.com", "api.venice.ai",
    "localhost", "127.0.0.1", "host.docker.internal",
])
_MCP_KEYWORDS = frozenset(["browse", "browser", "website", "calendar", "event", "email",
                           "gmail", "screenshot", "navigate", "click", "miniflux", "rss", "feed"])
_ADMIN_SCHEMA_NAMES = frozenset([
    "manage_session",     "create_skill", "manage_skills", "manage_tasks",
    "manage_endpoints", "manage_mcp", "manage_webhooks", "manage_tokens",
    "create_session", "list_sessions", "send_to_session", "pipeline",
    "ask_teacher", "list_models", "search_chats",
])
_TOOL_SELECTION_TIMEOUT_SECONDS = 1.5

_ADMIN_KEYWORDS = [
    "session", "sessions", "chat", "chats", "conversation", "conversations",
    "delete", "fork", "truncate",
    "archive", "rename", "endpoint", "endpoints", "api key",
    "webhook", "webhooks", "token", "tokens", "mcp", "server", "skill", "skills",
    "task", "tasks", "schedule", "cron", "setting", "settings", "preference",
    "configure", "config", "setup", "manage", "admin", "pipeline", "second opinion",
    "list models", "switch model", "change model", "theme", "create theme",
    "document", "documents", "doc", "docs", "library", "tidy",
    "note", "notes", "todo", "todos", "reminder", "reminders",
]


# ── Intent / message helpers ────────────────────────────────────────────

def _detect_admin_intent(messages: list[dict]) -> bool:
    """Check if the last user message suggests admin/management tool usage."""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg.get("content", "")
            if isinstance(content, list):
                content = " ".join(b.get("text", "") for b in content if isinstance(b, dict))
            content_lower = content.lower()
            return any(kw in content_lower for kw in _ADMIN_KEYWORDS)
    return False


def detect_file_references(text: str) -> list[dict]:
    """Scan user text for filename:line-number references.

    Detects patterns like:
      - foo.py:42
      - foo/bar.ts:10-30
      - L42: some text
      - at line 42 in foo.py

    Returns list of dicts with keys: path (str or None), line_start (int), line_end (int).
    """
    refs = []

    # Pattern 1: path:line or path:start-end
    for m in re.finditer(r'(?<![a-zA-Z0-9_])([\w./\\-]+\.\w+):(\d+)(?:-(\d+))?', text):
        path = m.group(1)
        ls = int(m.group(2))
        le = int(m.group(3)) if m.group(3) else ls
        refs.append({"path": path, "line_start": ls, "line_end": le})

    # Pattern 2: L42: at line start (GitHub-style line references)
    for m in re.finditer(r'(?:^|\s)L(\d+):\s*', text):
        ls = int(m.group(1))
        refs.append({"path": None, "line_start": ls, "line_end": ls})

    # Pattern 3: "at line 42 in foo.py"
    for m in re.finditer(r'at line (\d+).*?\bin\b\s+([\w./\\-]+\.\w+)', text):
        ls = int(m.group(1))
        path = m.group(2)
        refs.append({"path": path, "line_start": ls, "line_end": ls})

    # Pattern 4: standalone "line 42" near a filename mention
    for m in re.finditer(r'(?:^|\s)([\w./\\-]+\.\w+).*?line\s+(\d+)', text):
        path = m.group(1)
        ls = int(m.group(2))
        refs.append({"path": path, "line_start": ls, "line_end": ls})

    return refs


def _extract_last_user_message(messages: list[dict]) -> str:
    """Return the most recent user message as plain text."""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg.get("content", "")
            if isinstance(content, list):
                content = " ".join(b.get("text", "") for b in content if isinstance(b, dict))
            return content
    return ""


def _recent_context_for_retrieval(messages: list[dict], max_user: int = 3, max_chars: int = 600) -> str:
    """Build the tool-retrieval query from the last few USER turns."""
    collected = []
    for msg in reversed(messages):
        if msg.get("role") != "user":
            continue
        content = msg.get("content", "")
        if isinstance(content, list):
            content = " ".join(b.get("text", "") for b in content if isinstance(b, dict))
        content = (content or "").strip()
        if not content or content.startswith("[Tool execution results]"):
            continue
        collected.append(content)
        if len(collected) >= max_user:
            break
    return "\n".join(collected)[:max_chars]


# ── Tool block resolution ───────────────────────────────────────────────

def _resolve_tool_blocks(round_response: str, native_tool_calls: list, round_num: int):
    """Choose native function calls or fenced code block parsing."""
    used_native = False
    if native_tool_calls:
        tool_blocks = []
        for tc in native_tool_calls:
            tc_name = tc.get("name", "")
            tc_args = tc.get("arguments", "{}")
            block = function_call_to_tool_block(tc_name, tc_args)
            if block:
                tool_blocks.append(block)
                logger.info(f"  -> converted: {tc_name} -> {block.tool_type}")
            else:
                logger.warning(f"  -> FAILED to convert native call: {tc_name} args={tc_args[:200]}")
        if tool_blocks:
            used_native = True
    if not used_native:
        tool_blocks = parse_tool_blocks(round_response)
        if tool_blocks:
            logger.info(f"Agent round {round_num}: {len(tool_blocks)} fenced tool block(s) detected")

    resp_preview = round_response[:200].replace('\n', '\\n') if round_response else "(empty)"
    logger.info(f"Agent round {round_num} summary: {len(round_response)} chars, "
                f"{len(native_tool_calls)} native calls, "
                f"{len(tool_blocks)} tool blocks. Preview: {resp_preview}")

    return tool_blocks, used_native


# ── Tool result appending ───────────────────────────────────────────────

def _append_tool_results(
    messages: list[dict],
    round_response: str,
    native_tool_calls: list,
    tool_results: list,
    tool_result_texts: list,
    used_native: bool,
    round_num: int,
    round_reasoning: str = "",
):
    """Append tool execution results back into the message history."""
    for _m in messages:
        if _m.get("role") == "assistant":
            _m.pop("reasoning_content", None)
    if used_native and native_tool_calls:
        assistant_msg = {"role": "assistant"}
        assistant_msg["content"] = round_response if round_response.strip() else None
        if round_reasoning:
            assistant_msg["reasoning_content"] = round_reasoning
        assistant_msg["tool_calls"] = [
            {
                "id": tc.get("id", f"call_{round_num}_{j}"),
                "type": "function",
                "function": {
                    "name": tc.get("name", ""),
                    "arguments": tc.get("arguments", "{}"),
                },
                **({"extra_content": tc["extra_content"]} if tc.get("extra_content") else {}),
            }
            for j, tc in enumerate(native_tool_calls)
        ]
        messages.append(assistant_msg)
        for j, tc in enumerate(native_tool_calls):
            result_text = tool_result_texts[j] if j < len(tool_result_texts) else ""
            messages.append({
                "role": "tool",
                "tool_call_id": tc.get("id", f"call_{round_num}_{j}"),
                "content": result_text,
            })
    else:
        tool_output_text = "\n\n".join(tool_results)
        msg = {"role": "assistant", "content": round_response}
        if round_reasoning:
            msg["reasoning_content"] = round_reasoning
        messages.append(msg)
        messages.append(
            {"role": "user", "content": f"[Tool execution results]\n\n{tool_output_text}"}
        )


# ── Completion verifier ─────────────────────────────────────────────

_VERIFIER_EFFECTFUL_TOOLS = {
    "create_document", "update_document", "edit_document",
    "bash", "python", "write_file",
}
_VERIFIER_MAX_ROUNDS = 2


def _build_actions_snapshot(tool_events: list, limit: int = 8000) -> str:
    """Compact record of what the agent actually did this turn."""
    parts = []
    for ev in tool_events:
        tool = ev.get("tool", "?")
        cmd = (ev.get("command") or "").strip()
        out = (ev.get("output") or "").strip()
        rc = ev.get("exit_code")
        head = f"[{tool}] {cmd}" if cmd else f"[{tool}]"
        rc_s = f" (exit {rc})" if rc not in (None, 0) else ""
        body = (out[:1200] + " …") if len(out) > 1200 else (out or "(no output)")
        parts.append(f"{head}{rc_s}\n-> {body}")
    snap = "\n\n".join(parts)
    return snap[:limit] if len(snap) > limit else snap


async def _run_verifier_subagent(
    instruction: str, actions_snapshot: str,
    *, endpoint_url: str, model: str, headers: dict,
) -> list:
    """Fresh-context completion verifier."""
    from core.llm_core import llm_call_async
    prompt = (
        "You are an independent verifier. Another assistant just claimed the "
        "following task is complete. Using ONLY the request and the record of "
        "what it actually did, decide whether that claim is correct. Be strict: "
        "only say SUCCESS if the work genuinely satisfies the request.\n\n"
        f"<user_request>\n{(instruction or '')[:4000]}\n</user_request>\n\n"
        f"<actions_taken>\n{actions_snapshot[:8000]}\n</actions_taken>\n\n"
        "<checklist>\n"
        "1. Every concrete deliverable the request asked for was actually produced\n"
        "2. Outputs/edits match what was asked — nothing missing, no extra or unrequested changes\n"
        "3. Tool results show success, not errors or empty output that got ignored\n"
        "4. Anything the request said to leave alone was left unchanged\n"
        "</checklist>\n\n"
        "Reason briefly (2-3 sentences max). Then output EXACTLY one of:\n"
        "  VERIFICATION: SUCCESS\n"
        "  VERIFICATION: FAIL: <one short sentence per issue, semicolon-separated>\n"
        "Output nothing after the VERIFICATION line."
    )
    try:
        raw = await llm_call_async(
            url=endpoint_url, model=model,
            messages=[{"role": "user", "content": prompt}],
            headers=headers, temperature=0.0, max_tokens=600, timeout=60,
        )
    except Exception as e:
        logger.warning(f"[agent] verifier subagent failed: {e}")
        return []
    raw = re.sub(r"<think>.*?</think>", "", raw or "", flags=re.DOTALL | re.IGNORECASE)
    last_v = None
    for line in raw.splitlines():
        if "VERIFICATION:" in line:
            last_v = line.strip()
    if not last_v or "VERIFICATION: FAIL:" not in last_v:
        return []
    reasons = last_v.split("VERIFICATION: FAIL:", 1)[1].strip()
    return [r.strip() for r in reasons.split(";") if r.strip()]


# ── Empty-response fallback ─────────────────────────────────────────────

def _empty_response_fallback(
    full_response: str,
    round_reasoning: str,
    tool_events: list,
) -> tuple:
    """Return (final_response, sse_chunk_or_none) for the end-of-loop empty-response guard."""
    if full_response.strip() or tool_events:
        return full_response, None
    if round_reasoning.strip():
        return round_reasoning, None
    _error_msg = "The model returned an empty response. Please try again or switch to a different model."
    return _error_msg, f'data: {json.dumps({"delta": _error_msg})}\n\n'
