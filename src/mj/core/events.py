"""Append-only event log and the task state machine.

Every task transition is an event (plan section 6); a crash resumes from the
last event. Events are never updated or deleted by MJ code — the audit log and
the event log are the record of what happened.
"""

from __future__ import annotations

import json
import time
from typing import Any

from .store import Store, canonical_json

# Task states (plan section 6):
#   received -> planned -> policy_checked -> [awaiting_approval ->]
#   executing -> verifying -> done | failed | blocked
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "received": {"planned", "blocked"},
    "planned": {"policy_checked", "blocked"},
    "policy_checked": {"awaiting_approval", "executing", "blocked"},
    "awaiting_approval": {"executing", "blocked"},
    "executing": {"verifying", "failed"},
    "verifying": {"done", "failed"},
    "failed": set(),
    "done": set(),
    "blocked": {"planned"},  # a blocked task may be re-planned once the blocker clears
}


def append(
    store: Store,
    kind: str,
    payload: dict[str, Any],
    task_id: str | None = None,
    ts: float | None = None,
) -> int:
    """Append an event. Returns the sequence number."""
    cur = store.conn.execute(
        "INSERT INTO events (ts, task_id, kind, payload_json) VALUES (?, ?, ?, ?)",
        (ts if ts is not None else time.time(), task_id, kind, canonical_json(payload)),
    )
    out = cur.lastrowid
    assert isinstance(out, int)
    return out


def for_task(store: Store, task_id: str) -> list[dict[str, Any]]:
    out = []
    for row in store.query(
        "SELECT seq, ts, kind, payload_json FROM events "
        "WHERE task_id = ? ORDER BY seq",
        (task_id,),
    ):
        d = dict(row)
        d["payload"] = json.loads(d.pop("payload_json"))
        out.append(d)
    return out


def record_transition(
    store: Store,
    task_id: str,
    from_state: str,
    to_state: str,
    detail: dict[str, Any] | None = None,
) -> None:
    """Validate the transition, update the task row, append the event."""
    if to_state not in ALLOWED_TRANSITIONS.get(from_state, set()):
        raise ValueError(
            f"invalid task transition {from_state!r} -> {to_state!r} for task {task_id}"
        )
    store.conn.execute(
        "UPDATE tasks SET state = ?, updated_at = ? WHERE id = ? AND state = ?",
        (to_state, time.time(), task_id, from_state),
    )
    cur = store.conn.execute(
        "SELECT changes()",
    )
    changed = int(cur.fetchone()[0])
    if not changed:
        raise ValueError(
            f"task {task_id} is not in expected state {from_state!r} "
            "(concurrent transition or missing task)"
        )
    append(
        store,
        "task.transition",
        {"from": from_state, "to": to_state, "detail": detail or {}},
        task_id=task_id,
    )
