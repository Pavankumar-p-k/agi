"""ActivityManager — high-level API for the activity graph.

Wraps ActivityStore with domain operations:
  create_activity, create_subgoal, create_agent_task, record_artifact,
  add_dependency, mark_completed, resume_candidates, etc.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

from core.activity.models import ActivityEdge, ActivityNode, ActivityStatus
from core.activity.storage import ActivityStore

logger = logging.getLogger(__name__)


class ActivityManager:
    """Domain operations for the activity graph.

    Usage:
        mgr = ActivityManager()
        act = mgr.create_activity("Build coffee shop app")
        sub = mgr.create_subgoal(act, "Research competitors")
        task = mgr.create_agent_task(act, "research", "Research competitor apps", "research")
        mgr.add_dependency(task.node_id, sub.node_id, "depends_on")
        mgr.mark_completed(task.node_id, output={"result": "..."}, artifacts={"report": "art_001"})
    """

    def __init__(self, store: ActivityStore | None = None):
        self._store = store or ActivityStore()

    @property
    def store(self) -> ActivityStore:
        return self._store

    # ── Activity lifecycle ──────────────────────────────────────────────────

    def create_activity(self, goal: str, metadata: dict | None = None) -> ActivityNode:
        """Create a root activity node from a user goal. Returns the node."""
        node_id = f"act_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()
        node = ActivityNode(
            node_id=node_id,
            activity_id=node_id,
            node_type="goal",
            label=goal[:200],
            status=ActivityStatus.RUNNING,
            depth=0,
            input={"goal": goal},
            metadata=metadata or {},
            created_at=now,
            started_at=now,
        )
        self._store.create_node(node)
        logger.info("ActivityManager: created activity=%s goal=%r", node_id, goal[:60])
        return node

    def suspend_activity(self, activity_id: str) -> None:
        """Mark a root activity as SUSPENDED (paused, can resume later)."""
        root = self._store.get_node(activity_id)
        if root and root.depth == 0:
            root.status = ActivityStatus.SUSPENDED
            self._store.update_node(root)
            # Also mark any running children as SUSPENDED
            for node in self._store.get_activity_tree(activity_id):
                if node.status == ActivityStatus.RUNNING:
                    node.status = ActivityStatus.SUSPENDED
                    self._store.update_node(node)

    def complete_activity(self, activity_id: str, output: dict | None = None) -> None:
        """Mark a root activity and all incomplete children as COMPLETED."""
        root = self._store.get_node(activity_id)
        if not root or root.depth != 0:
            return
        now = datetime.utcnow()
        root.status = ActivityStatus.COMPLETED
        root.completed_at = now
        if output:
            root.output = output
        self._store.update_node(root)

    def fail_activity(self, activity_id: str, error: str) -> None:
        root = self._store.get_node(activity_id)
        if not root or root.depth != 0:
            return
        now = datetime.utcnow()
        root.status = ActivityStatus.FAILED
        root.completed_at = now
        root.output = {"error": error}
        self._store.update_node(root)

    # ── Sub-goal / task creation ────────────────────────────────────────────

    def create_subgoal(self, parent: ActivityNode, description: str,
                        step_name: str | None = None,
                        metadata: dict | None = None) -> ActivityNode:
        """Create a child subgoal node under a parent activity or subgoal."""
        node_id = f"sg_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()
        node = ActivityNode(
            node_id=node_id,
            parent_id=parent.node_id,
            activity_id=parent.activity_id,
            node_type="subgoal",
            label=description[:200],
            status=ActivityStatus.PENDING,
            depth=parent.depth + 1,
            input={"step_name": step_name, "description": description},
            metadata=metadata or {},
            created_at=now,
        )
        self._store.create_node(node)
        return node

    def create_agent_task(self, activity: ActivityNode, agent_id: str,
                           goal: str, step_name: str | None = None,
                           parent: ActivityNode | None = None,
                           origin_node_id: str | None = None,
                           input_data: dict | None = None) -> ActivityNode:
        """Create a node for an agent execution within an activity.

        origin_node_id can point to the causal predecessor
        (e.g., the artifact node that this agent consumes).
        """
        node_id = f"ag_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()
        parent_node = parent or activity
        node = ActivityNode(
            node_id=node_id,
            parent_id=parent_node.node_id,
            activity_id=activity.activity_id,
            node_type="agent_call",
            label=f"{agent_id}: {goal[:100]}",
            status=ActivityStatus.PENDING,
            depth=parent_node.depth + 1,
            agent_id=agent_id,
            origin_node_id=origin_node_id,
            input=input_data or {"goal": goal, "step_name": step_name},
            metadata={"goal": goal, "step_name": step_name},
            created_at=now,
            started_at=now,
        )
        self._store.create_node(node)
        return node

    def create_tool_call(self, parent: ActivityNode, tool_type: str,
                          input_data: dict | None = None,
                          origin_node_id: str | None = None) -> ActivityNode:
        """Create a node representing a single tool execution."""
        node_id = f"tl_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()
        node = ActivityNode(
            node_id=node_id,
            parent_id=parent.node_id,
            activity_id=parent.activity_id,
            node_type="tool_call",
            label=tool_type[:100],
            status=ActivityStatus.PENDING,
            depth=parent.depth + 1,
            agent_id=parent.agent_id,
            origin_node_id=origin_node_id,
            input=input_data or {},
            created_at=now,
        )
        self._store.create_node(node)
        return node

    def create_artifact_node(self, parent: ActivityNode, name: str,
                              artifact_id: str,
                              origin_node_id: str | None = None) -> ActivityNode:
        """Create a node representing a produced artifact."""
        node_id = f"art_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()
        node = ActivityNode(
            node_id=node_id,
            parent_id=parent.node_id,
            activity_id=parent.activity_id,
            node_type="artifact",
            label=name[:200],
            status=ActivityStatus.COMPLETED,
            depth=parent.depth + 1,
            agent_id=parent.agent_id,
            origin_node_id=origin_node_id,
            artifacts={name: artifact_id},
            created_at=now,
            completed_at=now,
        )
        self._store.create_node(node)
        return node

    # ── Status transitions ──────────────────────────────────────────────────

    def mark_running(self, node_id: str) -> None:
        node = self._store.get_node(node_id)
        if node:
            node.status = ActivityStatus.RUNNING
            node.started_at = node.started_at or datetime.utcnow()
            self._store.update_node(node)

    def mark_completed(self, node_id: str, output: dict | None = None,
                        artifacts: dict[str, str] | None = None) -> None:
        node = self._store.get_node(node_id)
        if not node:
            return
        node.status = ActivityStatus.COMPLETED
        node.completed_at = datetime.utcnow()
        if output:
            node.output = output
        if artifacts:
            node.artifacts.update(artifacts)
        self._store.update_node(node)

    def mark_failed(self, node_id: str, error: str) -> None:
        node = self._store.get_node(node_id)
        if not node:
            return
        node.status = ActivityStatus.FAILED
        node.completed_at = datetime.utcnow()
        node.output = {"error": error}
        self._store.update_node(node)

    # ── Dependencies ────────────────────────────────────────────────────────

    def add_dependency(self, from_node_id: str, to_node_id: str,
                        edge_type: str = "depends_on") -> ActivityEdge:
        """Add a directed edge: from_node -> to_node."""
        edge_id = f"ed_{uuid.uuid4().hex[:12]}"
        edge = ActivityEdge(
            edge_id=edge_id,
            from_node_id=from_node_id,
            to_node_id=to_node_id,
            edge_type=edge_type,
        )
        self._store.create_edge(edge)
        return edge

    def add_produces(self, agent_node_id: str, artifact_node_id: str) -> ActivityEdge:
        """Convenience: agent 'produces' artifact."""
        return self.add_dependency(agent_node_id, artifact_node_id, "produces")

    def link_workflow(self, node_id: str, workflow_id: str) -> None:
        """Link an activity node to a WorkflowInstance."""
        node = self._store.get_node(node_id)
        if node:
            node.workflow_id = workflow_id
            self._store.update_node(node)

    # ── Queries ─────────────────────────────────────────────────────────────

    def get_activity(self, activity_id: str) -> ActivityNode | None:
        return self._store.get_node(activity_id)

    def get_tree(self, activity_id: str) -> list[ActivityNode]:
        return self._store.get_activity_tree(activity_id)

    def get_timeline(self, activity_id: str) -> list[ActivityNode]:
        return self._store.get_activity_timeline(activity_id)

    def get_active_activities(self) -> list[ActivityNode]:
        """Return root activity nodes that are still in progress."""
        return self._store.get_active_activities()

    def resume_candidates(self, activity_id: str) -> list[ActivityNode]:
        """Return incomplete leaf nodes, shallowest first.

        These are the points from which execution can resume.
        Depth-first: shallower leaves represent higher-level work
        that hasn't started yet vs. deep leaves that are in-progress detail.
        """
        return self._store.get_incomplete_leaves(activity_id)

    def summarize(self, activity_id: str) -> dict[str, Any]:
        """Return a human-readable summary of an activity."""
        nodes = self._store.get_activity_tree(activity_id)
        if not nodes:
            return {"activity_id": activity_id, "error": "not found"}

        root = nodes[0]
        counts = self._store.count_by_status(activity_id)
        return {
            "activity_id": activity_id,
            "goal": root.label,
            "status": root.status.value,
            "total_nodes": len(nodes),
            "by_status": counts,
            "by_type": self._count_by_type(nodes),
            "depth": max(n.depth for n in nodes),
            "agents_used": sorted({n.agent_id for n in nodes if n.agent_id}),
            "created_at": root.created_at.isoformat() if root.created_at else None,
        }

    def _count_by_type(self, nodes: list[ActivityNode]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for n in nodes:
            counts[n.node_type] = counts.get(n.node_type, 0) + 1
        return counts
