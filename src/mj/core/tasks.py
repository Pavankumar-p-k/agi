"""Task lifecycle helpers over the store and event log.

Task state machine (plan section 6):
  received -> planned -> policy_checked -> [awaiting_approval ->]
  executing -> verifying -> done | failed | blocked
Every transition is an event; a crash resumes from the last event.
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

from . import audit, events
from .store import Store, canonical_json


def create(store: Store, goal: str, trust_level: str, actor: str = "user") -> dict[str, Any]:
    """Create a task in state received."""
    if not goal.strip():
        raise ValueError("goal text is required (empty goal is ambiguous, see failure mode 16)")
    task_id = f"t-{uuid.uuid4().hex[:12]}"
    now = time.time()
    store.conn.execute(
        "INSERT INTO tasks (id, goal, state, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        (task_id, goal, "received", now, now),
    )
    events.append(store, "task.created", {"goal": goal, "trust_level": trust_level}, task_id=task_id)
    audit.append(store, actor, "task.create", {"id": task_id, "goal": goal, "trust_level": trust_level})
    return {"id": task_id, "goal": goal, "state": "received", "created_at": now}


def get(store: Store, task_id: str) -> dict[str, Any] | None:
    row = store.one("SELECT id, goal, state, created_at, updated_at, report_json FROM tasks WHERE id = ?", (task_id,))
    if row is None:
        return None
    d = dict(row)
    d["report"] = None if row["report_json"] is None else json.loads(row["report_json"])
    return d


def transition(store: Store, task_id: str, to_state: str, detail: dict[str, Any] | None = None) -> None:
    row = store.one("SELECT state FROM tasks WHERE id = ?", (task_id,))
    if row is None:
        raise ValueError(f"unknown task {task_id!r}")
    events.record_transition(store, task_id, row["state"], to_state, detail)


def set_report(store: Store, task_id: str, report: dict[str, Any]) -> None:
    store.conn.execute(
        "UPDATE tasks SET report_json = ?, updated_at = ? WHERE id = ?",
        (canonical_json(report), time.time(), task_id),
    )
    events.append(store, "task.report", {"summary": report.get("summary", "")}, task_id=task_id)
