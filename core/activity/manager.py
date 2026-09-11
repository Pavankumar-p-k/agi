from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from core.activity.models import ActivityEdge, ActivityNode, ActivityStatus
from core.activity.storage import ActivityStore


class ActivityManager:
    def __init__(self, store: ActivityStore | None = None, **_kwargs: Any):
        self.store = store or ActivityStore()

    def create_activity(self, label: str) -> ActivityNode:
        node = ActivityNode(activity_id="", node_type="goal", label=label, depth=0, status=ActivityStatus.RUNNING)
        node.activity_id = node.node_id
        return self.store.create_node(node)

    def _child(self, parent: ActivityNode, node_type: str, label: str, **kwargs: Any) -> ActivityNode:
        node = ActivityNode(activity_id=parent.activity_id, node_type=node_type, label=label,
                           depth=parent.depth + 1, parent_id=parent.node_id, **kwargs)
        return self.store.create_node(node)

    def create_subgoal(self, parent: ActivityNode, label: str, step_name: str | None = None) -> ActivityNode:
        return self._child(parent, "subgoal", label, input={"step_name": step_name} if step_name else {})

    def create_agent_task(self, activity: ActivityNode, agent_id: str, label: str, step_name: str | None = None, origin_node_id: str | None = None, parent: ActivityNode | None = None) -> ActivityNode:
        actual_parent = parent or activity
        return self._child(actual_parent, "agent_call", label, agent_id=agent_id, origin_node_id=origin_node_id,
                           input={"step_name": step_name} if step_name else {})

    def create_tool_call(self, parent: ActivityNode, tool_name: str, input_data: dict[str, Any] | None = None) -> ActivityNode:
        return self._child(parent, "tool_call", tool_name, agent_id=parent.agent_id, input=input_data or {})

    def create_artifact_node(self, parent: ActivityNode, label: str, artifact_id: str) -> ActivityNode:
        node = self._child(parent, "artifact", label, artifacts={label: artifact_id}, status=ActivityStatus.COMPLETED)
        node.completed_at = datetime.now(timezone.utc)
        return node

    def get_activity(self, node_id: str) -> ActivityNode | None:
        return self.store.get_node(node_id)

    def mark_running(self, node_id: str) -> None:
        node = self.get_activity(node_id)
        if node:
            node.status = ActivityStatus.RUNNING
            node.started_at = datetime.now(timezone.utc)
            self.store.update_node(node)

    def mark_completed(self, node_id: str, output: Any = None, artifacts: dict[str, Any] | None = None) -> None:
        node = self.get_activity(node_id)
        if node:
            node.status = ActivityStatus.COMPLETED
            node.output = output
            node.artifacts.update(artifacts or {})
            node.completed_at = datetime.now(timezone.utc)
            self.store.update_node(node)

    def mark_failed(self, node_id: str, error: str) -> None:
        node = self.get_activity(node_id)
        if node:
            node.status = ActivityStatus.FAILED
            node.output = {"error": error}
            node.completed_at = datetime.now(timezone.utc)
            self.store.update_node(node)

    def suspend_activity(self, node_id: str) -> None:
        for node in self.store.get_activity_tree(node_id):
            node.status = ActivityStatus.SUSPENDED
            self.store.update_node(node)

    def complete_activity(self, node_id: str, output: Any = None) -> None:
        self.mark_completed(node_id, output)

    def fail_activity(self, node_id: str, error: str) -> None:
        self.mark_failed(node_id, error)

    def add_dependency(self, from_id: str, to_id: str) -> ActivityEdge:
        return self.store.create_edge(ActivityEdge(from_node_id=from_id, to_node_id=to_id, edge_type="depends_on"))

    def add_produces(self, from_id: str, to_id: str) -> ActivityEdge:
        return self.store.create_edge(ActivityEdge(from_node_id=from_id, to_node_id=to_id, edge_type="produces"))

    def link_workflow(self, node_id: str, workflow_id: str) -> None:
        node = self.get_activity(node_id)
        if node:
            node.workflow_id = workflow_id
            self.store.update_node(node)

    def get_tree(self, activity_id: str) -> list[ActivityNode]:
        return self.store.get_activity_tree(activity_id)

    def get_timeline(self, activity_id: str) -> list[ActivityNode]:
        return self.store.get_activity_timeline(activity_id)

    def get_active_activities(self) -> list[ActivityNode]:
        return self.store.get_active_activities()

    def resume_candidates(self, activity_id: str) -> list[ActivityNode]:
        return self.store.get_incomplete_leaves(activity_id)

    def summarize(self, activity_id: str) -> dict[str, Any]:
        nodes = self.get_tree(activity_id)
        if not nodes:
            return {"error": "Activity not found"}
        root = nodes[0]
        return {
            "activity_id": activity_id, "goal": root.label, "status": root.status.value,
            "total_nodes": len(nodes), "depth": max(n.depth for n in nodes),
            "agents_used": sorted({n.agent_id for n in nodes if n.agent_id}),
            "created_at": root.created_at, "by_status": self.store.count_by_status(activity_id),
        }
