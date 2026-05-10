from __future__ import annotations

import json
import time
from pathlib import Path

from ..contracts import ToolSpec


def register_automation_tools(registry) -> None:
    registry.register(
        ToolSpec("schedule_task", "Schedule a recurring task descriptor.", ["name", "command", "interval_s"], parameters={"name": {"type": "string", "required": True}, "command": {"type": "string", "required": True}, "interval_s": {"type": "integer", "required": False, "default": 3600}}, category="automation", keywords=["schedule", "repeat", "automation"]),
        lambda name, command, interval_s=3600, **_: _schedule_task(registry, name, command, interval_s),
    )
    registry.register(
        ToolSpec("repeat_task", "Alias for recurring task scheduling.", ["name", "command", "interval_s"], parameters={"name": {"type": "string", "required": True}, "command": {"type": "string", "required": True}, "interval_s": {"type": "integer", "required": False, "default": 3600}}, category="automation", keywords=["repeat", "schedule", "task"]),
        lambda name, command, interval_s=3600, **_: _schedule_task(registry, name, command, interval_s),
    )
    registry.register(
        ToolSpec("workflow_runner", "Run a simple workflow of steps.", ["workflow"], parameters={"workflow": {"type": "array", "required": True}}, category="automation", keywords=["workflow", "pipeline", "run"]),
        lambda workflow, **_: _workflow_runner(registry, workflow),
    )
    registry.register(
        ToolSpec("list_schedules", "List scheduled tasks.", [], category="automation", read_only=True, keywords=["schedule", "list", "jobs"]),
        lambda **_: _read_schedule_file(registry),
    )
    registry.register(
        ToolSpec("cancel_schedule", "Cancel a scheduled task.", ["name"], parameters={"name": {"type": "string", "required": True}}, category="automation", keywords=["cancel", "schedule", "remove"]),
        lambda name, **_: _cancel_schedule(registry, name),
    )


def _schedule_file(registry) -> Path:
    return Path(registry.config.data_dir) / "schedules.json"


def _read_schedule_file(registry) -> dict:
    target = _schedule_file(registry)
    if not target.exists():
        return {"items": []}
    raw = target.read_text(encoding="utf-8").strip()
    if not raw:
        return {"items": []}
    try:
        items = json.loads(raw)
    except json.JSONDecodeError:
        items = []
    normalized = []
    for item in items:
        normalized.append(
            {
                "name": item["name"],
                "command": item["command"],
                "interval_s": int(item.get("interval_s", 3600)),
                "created_at": float(item.get("created_at", time.time())),
                "last_run_at": item.get("last_run_at"),
                "next_run_at": float(item.get("next_run_at", time.time())),
                "enabled": bool(item.get("enabled", True)),
                "last_job_id": item.get("last_job_id", ""),
            }
        )
    return {"items": normalized}


def _write_schedule_file(registry, items: list[dict]) -> None:
    target = _schedule_file(registry)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(items, indent=2), encoding="utf-8")


def _schedule_task(registry, name: str, command: str, interval_s: int) -> dict:
    now = time.time()
    items = _read_schedule_file(registry)["items"]
    items = [item for item in items if item["name"] != name]
    items.append(
        {
            "name": name,
            "command": command,
            "interval_s": int(interval_s),
            "created_at": now,
            "last_run_at": None,
            "next_run_at": now + int(interval_s),
            "enabled": True,
            "last_job_id": "",
        }
    )
    _write_schedule_file(registry, items)
    return {"scheduled": True, "name": name, "interval_s": int(interval_s), "next_run_at": now + int(interval_s)}


def _cancel_schedule(registry, name: str) -> dict:
    items = _read_schedule_file(registry)["items"]
    updated = [item for item in items if item["name"] != name]
    _write_schedule_file(registry, updated)
    return {"cancelled": True, "name": name}


def _workflow_runner(registry, workflow) -> dict:
    results = []
    for step in workflow:
        if isinstance(step, dict):
            tool = step.get("tool", "summarize_text")
            arguments = step.get("arguments", {})
        else:
            tool = "summarize_text"
            arguments = {"text": str(step)}
        results.append({"tool": tool, "output": registry.invoke(tool, **arguments)})
    return {"steps": len(results), "results": results}
