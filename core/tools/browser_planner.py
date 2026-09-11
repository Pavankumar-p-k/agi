"""Deterministic planning guards for browser tool calls.

This module deliberately plans actions only.  It never reports that a browser
action succeeded; execution and read-back verification remain the responsibility
of the browser tool layer.
"""
from __future__ import annotations

import re
from typing import Any


def extract_query(task: str) -> str | None:
    text = str(task or "").strip()
    find_match = re.match(r"""find\s+(.+)$""", text, re.I)
    if find_match:
        return find_match.group(1).strip().strip("\"'")
    match = re.search(r"""(?:search|find)(?:\s+\w+)?\s+for\s+["'](.+?)["']""", text, re.I)
    if match:
        return match.group(1)
    match = re.search(r"""(?:search|find)(?:\s+\w+)?(?:\s+for)?\s+(.+)$""", text, re.I)
    if match:
        return match.group(1).strip()
    return None


def detect_loop(history: list[Any]) -> bool:
    values = [str(item) for item in history]
    return len(values) >= 6 and values[-6:-4] == values[-4:-2] == values[-2:]


def _name(block: Any) -> str:
    if isinstance(block, dict):
        return str(block.get("name") or block.get("tool") or "")
    return str(getattr(block, "tool_type", getattr(block, "tool", "")))


def _block(name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"name": name, "arguments": arguments or {}}


class BrowserPlanner:
    @staticmethod
    def init(task: str) -> dict[str, Any]:
        return {
            "task": str(task or ""),
            "query": extract_query(task),
            "fsm": {"state": "START", "actions_in_state": 0, "total_actions": 0,
                    "consecutive_same_tool": 0, "last_tool": "", "_initialized": True},
            "history": [],
            "decisions": [],
        }

    @staticmethod
    def pre_plan(calls: list[Any], ctx: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
        planned: list[Any] = []
        browser_tools = {"browser_navigate", "browser_snapshot", "browser_click",
                         "browser_fill", "browser_press", "browser_find"}
        has_browser = any(_name(call) in browser_tools for call in calls)
        state = ctx.get("fsm", {}).get("state", "START")
        query = ctx.get("query")
        if query and not has_browser and state == "START":
            planned.append(_block("browser_navigate", {"url": "https://www.google.com"}))
            ctx.setdefault("decisions", []).append({"rule": "intent_router"})
        for call in calls:
            planned.append(call)
            if _name(call) == "browser_navigate":
                planned.append(_block("browser_snapshot"))
                ctx.setdefault("decisions", []).append({"rule": "auto_snapshot"})
        return planned, ctx

    @staticmethod
    def post_plan(results: list[Any], calls: list[Any], ctx: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
        history = ctx.setdefault("history", [])
        for call in calls:
            history.append({"name": _name(call)})
        fsm = ctx.setdefault("fsm", {})
        fsm["total_actions"] = int(fsm.get("total_actions", 0)) + len(calls)
        if calls:
            fsm["state"] = "SEARCH_PAGE" if (
                any(_name(c) in {"browser_navigate", "browser_snapshot"} for c in calls)
                and fsm.get("state") in {"START", "NAVIGATE"}
            ) else fsm.get("state", "START")
        return [], ctx
