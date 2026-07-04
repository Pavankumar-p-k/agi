"""ExecutionTracker — ties graphs, events, focus, and agents together.

One tracker instance manages multiple goal sessions. Each session has an
ExecutionGraph. The tracker emits events on every state change via the
global EventBus, which WebSocket clients and in-process handlers receive.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from core.workflow.events import (
    CONFIDENCE_UPDATED,
    ESTIMATE_UPDATED,
    GOAL_COMPLETED,
    GOAL_CREATED,
    GOAL_FAILED,
    GOAL_UPDATED,
    MILESTONE,
    NODE_COMPLETED,
    NODE_CREATED,
    NODE_FAILED,
    NODE_SKIPPED,
    NODE_UPDATED,
    WARNING,
    emit as emit_event,
)
from core.workflow.graph import ExecutionGraph, ExecutionNode


class FocusMode:
    """Tracks what MJ is currently focused on.

    When a new request arrives while busy, FocusMode decides how to handle it.
    """

    def __init__(self) -> None:
        self._active_session_id: str | None = None
        self._queue: list[dict[str, Any]] = []
        self._paused: bool = False

    @property
    def active_session_id(self) -> str | None:
        return self._active_session_id

    @property
    def is_busy(self) -> bool:
        return self._active_session_id is not None and not self._paused

    @property
    def queue_depth(self) -> int:
        return len(self._queue)

    def set_active(self, session_id: str | None) -> None:
        self._active_session_id = session_id

    def pause(self) -> None:
        self._paused = True

    def resume(self) -> None:
        self._paused = False

    def enqueue(self, request: dict[str, Any]) -> None:
        self._queue.append(request)

    def dequeue(self) -> dict[str, Any] | None:
        return self._queue.pop(0) if self._queue else None

    def clear_queue(self) -> None:
        self._queue.clear()

    def to_dict(self) -> dict[str, Any]:
        return {
            "active_session_id": self._active_session_id,
            "is_busy": self.is_busy,
            "queue_depth": self.queue_depth,
            "paused": self._paused,
        }


class ExecutionTracker:
    """Central coordinator for goal execution sessions.

    Usage:
        tracker = ExecutionTracker()
        session_id = tracker.create_goal("Build a portfolio website")
        tracker.add_node(session_id, None, "Plan architecture")
        tracker.add_node(session_id, None, "Code components", node_type="code")
        tracker.update_node(session_id, node_id, status="running")
    """

    def __init__(self) -> None:
        self._graphs: dict[str, ExecutionGraph] = {}
        self._focus = FocusMode()

    @property
    def focus(self) -> FocusMode:
        return self._focus

    # ── Goal lifecycle ──────────────────────────────────────────────────

    def create_goal(self, goal: str, goal_id: str | None = None) -> str:
        graph = ExecutionGraph(goal=goal, goal_id=goal_id)
        self._graphs[graph.goal_id] = graph
        self._focus.set_active(graph.goal_id)
        emit_event(
            GOAL_CREATED,
            payload={"goal": goal, "goal_id": graph.goal_id},
            session_id=graph.goal_id,
            goal_id=graph.goal_id,
        )
        return graph.goal_id

    def get_graph(self, session_id: str) -> ExecutionGraph | None:
        return self._graphs.get(session_id)

    def list_goals(self, status: str | None = None) -> list[dict[str, Any]]:
        result = []
        for g in self._graphs.values():
            if status and g.status != status:
                continue
            result.append({
                "goal_id": g.goal_id,
                "goal": g.goal,
                "status": g.status,
                "created_at": g.created_at,
            })
        return sorted(result, key=lambda x: x["created_at"], reverse=True)

    def complete_goal(self, session_id: str) -> None:
        graph = self._graphs.get(session_id)
        if not graph:
            return
        graph.status = "completed"
        emit_event(
            GOAL_COMPLETED,
            payload={"goal": graph.goal, "goal_id": session_id},
            session_id=session_id,
            goal_id=session_id,
        )
        if self._focus.active_session_id == session_id:
            self._focus.set_active(None)

    def fail_goal(self, session_id: str, error: str) -> None:
        graph = self._graphs.get(session_id)
        if not graph:
            return
        graph.status = "failed"
        emit_event(
            GOAL_FAILED,
            payload={"goal": graph.goal, "goal_id": session_id, "error": error},
            session_id=session_id,
            goal_id=session_id,
        )

    # ── Node lifecycle ──────────────────────────────────────────────────

    def add_node(
        self,
        session_id: str,
        parent_id: str | None,
        label: str,
        node_type: str = "task",
        **kwargs: Any,
    ) -> ExecutionNode | None:
        graph = self._graphs.get(session_id)
        if not graph:
            return None
        node = graph.add_node(parent_id, label, node_type, **kwargs)
        emit_event(
            NODE_CREATED,
            payload={
                "node_id": node.node_id,
                "parent_id": parent_id,
                "label": label,
                "node_type": node_type,
                "status": node.status,
                "confidence": node.confidence,
            },
            session_id=session_id,
            goal_id=session_id,
        )
        return node

    def update_node(
        self,
        session_id: str,
        node_id: str,
        **updates: Any,
    ) -> ExecutionNode | None:
        graph = self._graphs.get(session_id)
        if not graph:
            return None
        node = graph.update_node(node_id, **updates)
        if not node:
            return None

        event_type = NODE_UPDATED
        if updates.get("status") == "completed":
            event_type = NODE_COMPLETED
        elif updates.get("status") == "failed":
            event_type = NODE_FAILED
        elif updates.get("status") == "skipped":
            event_type = NODE_SKIPPED

        emit_event(
            event_type,
            payload={
                "node_id": node_id,
                "label": node.label,
                "status": node.status,
                "confidence": node.confidence,
            },
            session_id=session_id,
            goal_id=session_id,
        )

        if "confidence" in updates and node.status != "completed":
            emit_event(
                CONFIDENCE_UPDATED,
                payload={"node_id": node_id, "label": node.label, "confidence": node.confidence},
                session_id=session_id,
                goal_id=session_id,
            )

        if "estimate_seconds" in updates:
            emit_event(
                ESTIMATE_UPDATED,
                payload={
                    "node_id": node_id,
                    "label": node.label,
                    "estimate_seconds": node.estimate_seconds,
                    "total_estimate_seconds": node.total_estimate_seconds(),
                },
                session_id=session_id,
                goal_id=session_id,
            )

        return node

    def remove_node(self, session_id: str, node_id: str) -> bool:
        graph = self._graphs.get(session_id)
        if not graph:
            return False
        return graph.remove_node(node_id)

    def reorder_node(self, session_id: str, parent_id: str, node_id: str, new_index: int) -> bool:
        graph = self._graphs.get(session_id)
        if not graph:
            return False
        return graph.reorder_child(parent_id, node_id, new_index)

    # ── Convenience ─────────────────────────────────────────────────────

    def milestone(self, session_id: str, message: str) -> None:
        graph = self._graphs.get(session_id)
        emit_event(
            MILESTONE,
            payload={
                "message": message,
                "goal": graph.goal if graph else "",
            },
            session_id=session_id,
            goal_id=session_id,
        )

    def warning(self, session_id: str, message: str) -> None:
        emit_event(
            WARNING,
            payload={"message": message},
            session_id=session_id,
            goal_id=session_id,
        )

    def set_node_detail(self, session_id: str, node_id: str, detail: str) -> ExecutionNode | None:
        return self.update_node(session_id, node_id, detail=detail)


# ── Global singleton ─────────────────────────────────────────────────────────

_tracker: ExecutionTracker | None = None


def get_tracker() -> ExecutionTracker:
    global _tracker
    if _tracker is None:
        _tracker = ExecutionTracker()
    return _tracker


def reset_tracker() -> None:
    global _tracker
    _tracker = None
