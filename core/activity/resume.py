from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.activity.models import ActivityNode, ActivityStatus


@dataclass
class ResumeContext:
    activity_id: str
    target_node: ActivityNode
    ancestors: list[ActivityNode] = field(default_factory=list)
    root_goal: str = ""
    accumulated_artifacts: dict[str, Any] = field(default_factory=dict)
    accumulated_input: dict[str, Any] = field(default_factory=dict)

    @property
    def target_label(self) -> str:
        return self.target_node.label

    @property
    def is_for_agent(self) -> bool:
        return bool(self.target_node.agent_id)

    @property
    def agent_id(self) -> str | None:
        return self.target_node.agent_id


class ResumeEngine:
    def __init__(self, manager: Any):
        self.manager = manager

    def _context(self, activity_id: str, target: ActivityNode) -> ResumeContext:
        nodes = self.manager.get_tree(activity_id)
        by_id = {node.node_id: node for node in nodes}
        chain: list[ActivityNode] = []
        current: ActivityNode | None = target
        while current is not None:
            chain.append(current)
            current = by_id.get(current.parent_id) if current.parent_id else None
        ancestors = list(reversed(chain))
        artifacts: dict[str, Any] = {}
        inputs: dict[str, Any] = {}
        for node in nodes:
            if node.status == ActivityStatus.COMPLETED:
                artifacts.update(node.artifacts)
        for node in ancestors:
            inputs.update(node.input)
        root = nodes[0] if nodes else target
        return ResumeContext(
            activity_id=activity_id,
            target_node=target,
            ancestors=ancestors,
            root_goal=root.label,
            accumulated_artifacts=artifacts,
            accumulated_input=inputs,
        )

    def find_resume_point(self, activity_id: str) -> ResumeContext | None:
        nodes = self.manager.get_tree(activity_id)
        if not nodes:
            return None
        root = nodes[0]
        if root.status in {ActivityStatus.COMPLETED, ActivityStatus.FAILED, ActivityStatus.CANCELLED}:
            return None
        candidates = self.manager.resume_candidates(activity_id)
        if not candidates:
            candidates = [root] if root.status in {ActivityStatus.PENDING, ActivityStatus.RUNNING, ActivityStatus.SUSPENDED} else []
        if not candidates:
            return None
        target = sorted(candidates, key=lambda node: (node.depth, node.created_at, node.node_id))[0]
        return self._context(activity_id, target)

    def resume_all_candidates(self, activity_id: str) -> list[ResumeContext]:
        nodes = self.manager.get_tree(activity_id)
        if not nodes or nodes[0].status in {ActivityStatus.COMPLETED, ActivityStatus.FAILED, ActivityStatus.CANCELLED}:
            return []
        candidates = self.manager.resume_candidates(activity_id)
        if not candidates:
            root = nodes[0]
            candidates = [root] if root.status in {ActivityStatus.PENDING, ActivityStatus.RUNNING, ActivityStatus.SUSPENDED} else []
        return [self._context(activity_id, node) for node in sorted(candidates, key=lambda n: (n.depth, n.created_at, n.node_id))]

    def mark_resumed(self, context: ResumeContext) -> None:
        for node in context.ancestors:
            if node.status in {ActivityStatus.PENDING, ActivityStatus.SUSPENDED}:
                self.manager.mark_running(node.node_id)

    def activity_summary(self, activity_id: str) -> str:
        nodes = self.manager.get_tree(activity_id)
        if not nodes:
            return f"Activity {activity_id} not found"
        root = nodes[0]
        leaves = self.manager.resume_candidates(activity_id)
        labels = ", ".join(node.label for node in leaves) or "none"
        return (
            f"{root.label} ({root.status.value})\n"
            f"Nodes: {len(nodes)}\n"
            f"Incomplete leaves: {len(leaves)}\n"
            f"Resume candidates: {labels}"
        )
