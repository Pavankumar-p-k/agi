"""Agent-loop helpers: admin-intent detection + tool-result message appending."""

import re

# Admin intents detected on the LAST user message.
_ADMIN_PATTERNS = [
    r"\badd\b.*\bendpoint\b",
    r"\bcreate\b.*\bendpoint\b",
    r"\blist\b.*\bsessions?\b",
    r"\bmanage\b.*\bsessions?\b",
    r"\brename\b.*\bsession\b",
    r"\barchive\b.*\bsessions?\b",
    r"\bconfigure\b.*\bsettings?\b",
    r"\badd\b.*\bmcp\b.*\bserver\b",
    r"\bupdate\b.*\bapi\s*key\b",
    r"\blist\b.*\bmodels?\b",
    r"\bswitch\b.*\bmodel\b",
    r"\b(manage|show)\b.*\bskills?\b",
    r"\bschedule\b.*\b(cron\s*)?task\b",
]

_COMPILE = [re.compile(p, re.IGNORECASE) for p in _ADMIN_PATTERNS]


def _last_user_text(messages: list) -> str:
    """Text of the last user message (handles multimodal content lists)."""
    for msg in reversed(messages or []):
        if not isinstance(msg, dict) or msg.get("role") != "user":
            continue
        content = msg.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = [
                str(p.get("text", "")) for p in content
                if isinstance(p, dict) and p.get("type") == "text"
            ]
            return " ".join(parts)
        return ""
    return ""


def _detect_admin_intent(messages: list) -> bool:
    """True when the last user message asks for admin/management actions."""
    text = _last_user_text(messages)
    if not text:
        return False
    return any(p.search(text) for p in _COMPILE)


def _append_tool_results(
    messages: list,
    text: str,
    native_tool_calls: list,
    tool_outputs: list,
    tool_texts: list,
    used_native: bool,
    round_num: int,
    **kwargs,
) -> None:
    """Append the assistant turn + tool results to `messages` in place.

    Native path: assistant message carries `tool_calls`; each tool output is a
    separate `role=tool` message with matching `tool_call_id`.
    Non-native path: assistant text, then a user message with the outputs.
    """
    if used_native and native_tool_calls:
        assistant: dict = {"role": "assistant", "content": text if text and text.strip() else None}
        calls = []
        for i, tc in enumerate(native_tool_calls):
            entry: dict = {
                "id": tc.get("id", f"call_{round_num}_{i}"),
                "type": "function",
                "function": {
                    "name": tc.get("name", ""),
                    "arguments": tc.get("arguments", "{}"),
                },
            }
            extra = tc.get("extra_content")
            if extra is not None:
                entry["extra_content"] = extra
            calls.append(entry)
        assistant["tool_calls"] = calls
        messages.append(assistant)

        for i, output in enumerate(tool_outputs):
            call_id = native_tool_calls[i].get("id", f"call_{round_num}_{i}") \
                if i < len(native_tool_calls) else f"call_{round_num}_{i}"
            messages.append({
                "role": "tool",
                "tool_call_id": call_id,
                "content": tool_texts[i] if i < len(tool_texts) else str(output),
            })
    else:
        messages.append({"role": "assistant", "content": text})
        joined = "\n".join(str(o) for o in tool_outputs)
        messages.append({"role": "user", "content": f"Tool output:\n{joined}"})


__all__ = ["_detect_admin_intent", "_append_tool_results"]
