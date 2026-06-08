"""core/llm_messages.py — LLM message sanitization and normalization."""
from __future__ import annotations

import logging
from typing import Dict, List

logger = logging.getLogger(__name__)


def _as_content_blocks(content) -> List[Dict]:
    if isinstance(content, list):
        return content
    if content:
        return [{"type": "text", "text": str(content)}]
    return []


def _sanitize_llm_messages(messages: List[Dict]) -> List[Dict]:
    allowed = {"role", "content", "name", "tool_call_id", "tool_calls", "function_call"}
    cleaned = []
    for msg in messages or []:
        if not isinstance(msg, dict):
            continue
        item = {k: v for k, v in msg.items() if k in allowed and v is not None}
        role = item.get("role")
        if not role:
            continue
        if role == "assistant":
            if "content" not in item and item.get("tool_calls"):
                item["content"] = None
            if "content" in item or item.get("tool_calls"):
                cleaned.append(item)
        elif role == "tool":
            if "content" in item and "tool_call_id" in item:
                cleaned.append(item)
        elif "content" in item:
            cleaned.append(item)

    repaired: List[Dict] = []
    i = 0
    while i < len(cleaned):
        msg = cleaned[i]
        role = msg.get("role")

        if role == "tool":
            logger.debug("Dropping orphan tool message before provider request")
            i += 1
            continue

        tool_calls = msg.get("tool_calls") if role == "assistant" else None
        if not tool_calls:
            repaired.append(msg)
            i += 1
            continue

        call_ids = [
            str(tc.get("id"))
            for tc in tool_calls
            if isinstance(tc, dict) and tc.get("id")
        ]
        expected = set(call_ids)
        answered_ids = []
        tool_batch = []
        j = i + 1
        while j < len(cleaned) and cleaned[j].get("role") == "tool":
            tid = str(cleaned[j].get("tool_call_id") or "")
            if tid in expected and tid not in answered_ids:
                answered_ids.append(tid)
                tool_batch.append(cleaned[j])
            else:
                logger.debug("Dropping unmatched/duplicate tool message before provider request")
            j += 1

        if not tool_batch:
            plain = {k: v for k, v in msg.items() if k != "tool_calls"}
            if (plain.get("content") or "").strip():
                repaired.append(plain)
            else:
                logger.debug("Dropping unanswered assistant tool_calls before provider request")
            i = j
            continue

        answered = set(answered_ids)
        pruned_calls = [
            tc for tc in tool_calls
            if isinstance(tc, dict) and str(tc.get("id")) in answered
        ]
        fixed = dict(msg)
        fixed["tool_calls"] = pruned_calls
        if "content" not in fixed:
            fixed["content"] = None
        repaired.append(fixed)
        repaired.extend(tool_batch)
        if len(pruned_calls) != len(tool_calls):
            logger.debug("Pruned unanswered assistant tool_calls before provider request")
        i = j

    merged: List[Dict] = []
    for item in repaired:
        if not merged:
            merged.append(item)
            continue
        last = merged[-1]
        if last.get("role") == "user" and item.get("role") == "user":
            last_copy = dict(last)
            lc = last_copy.get("content")
            ic = item.get("content")
            if isinstance(lc, list) or isinstance(ic, list):
                merged_blocks = _as_content_blocks(lc) + _as_content_blocks(ic)
                if merged_blocks:
                    last_copy["content"] = merged_blocks
                else:
                    last_copy.pop("content", None)
            else:
                last_str = str(lc) if lc is not None else ""
                item_str = str(ic) if ic is not None else ""
                new_content = "\n\n".join(part for part in (last_str, item_str) if part)
                if new_content:
                    last_copy["content"] = new_content
                else:
                    last_copy.pop("content", None)
            merged[-1] = last_copy
        else:
            merged.append(item)
    return merged
