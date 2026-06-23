"""ResumeEngine — finds where to resume execution in an activity graph.

The Resume Engine is the reason the Activity Graph exists. Given a
suspended or incomplete activity, it finds the first incomplete leaf
and reconstructs the execution context (ancestors, artifacts, input)
needed to continue.

Algorithm:
  1. Find incomplete leaves via ActivityManager.resume_candidates()
     (PENDING/RUNNING/SUSPENDED nodes with no incomplete children)
  2. Pick the shallowest (highest-level) leaf — represents the
     highest-level work unit that hasn't been completed
  3. Walk up ancestors collecting artifacts, input, and metadata
  4. Return ResumeContext — ready for planner re-injection
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from core.activity.manager import ActivityManager
from core.activity.models import ActivityNode, ActivityStatus

logger = logging.getLogger(__name__)


@dataclass
class ResumeContext:
    """Result of finding a resume point in an activity graph."""

    activity_id: str
    target_node: ActivityNode
    ancestors: list[ActivityNode] = field(default_factory=list)
    accumulated_artifacts: dict[str, str] = field(default_factory=dict)
    accumulated_input: dict[str, Any] = field(default_factory=dict)

    @property
    def target_label(self) -> str:
        return self.target_node.label

    @property
    def is_for_agent(self) -> bool:
        return self.target_node.node_type == "agent_call"

    @property
    def agent_id(self) -> str | None:
        return self.target_node.agent_id

    @property
    def root_goal(self) -> str:
        """Return the root activity's goal label."""
        if self.ancestors:
            return self.ancestors[0].label
        return ""


class ResumeEngine:
    """Deterministic resume point finder for activity graphs.

    Usage:
        mgr = ActivityManager()
        engine = ResumeEngine(mgr)
        ctx = engine.find_resume_point("act_abc123")
        if ctx:
            planner.resume_from(ctx)
    """

    def __init__(self, manager: ActivityManager):
        self._mgr = manager

    def find_resume_point(self, activity_id: str) -> ResumeContext | None:
        """Find where to resume execution in an activity.

        Returns None if activity not found or no incomplete leaves remain.
        """
        activity = self._mgr.get_activity(activity_id)
        if not activity:
            logger.warning("ResumeEngine: activity %s not found", activity_id)
            return None

        if activity.status in (ActivityStatus.COMPLETED, ActivityStatus.CANCELLED):
            logger.info("ResumeEngine: activity %s already %s, nothing to resume",
                        activity_id, activity.status.value)
            return None

        leaves = self._mgr.resume_candidates(activity_id)
        if not leaves:
            logger.info("ResumeEngine: no incomplete leaves in activity %s",
                        activity_id)
            return None

        target = leaves[0]
        logger.info("ResumeEngine: resume point=%s label=%r depth=%d status=%s",
                    target.node_id, target.label, target.depth, target.status.value)

        ancestors = self._build_ancestors(target)
        accumulated = self._collect_artifacts(ancestors)

        return ResumeContext(
            activity_id=activity_id,
            target_node=target,
            ancestors=ancestors,
            accumulated_artifacts=accumulated["artifacts"],
            accumulated_input=accumulated["input"],
        )

    def resume_all_candidates(self, activity_id: str) -> list[ResumeContext]:
        """Return resume contexts for ALL incomplete leaves.

        Useful for decomposing remaining work into a list of sub-goals
        that still need to be done.
        """
        activity = self._mgr.get_activity(activity_id)
        if not activity:
            return []

        leaves = self._mgr.resume_candidates(activity_id)
        results: list[ResumeContext] = []
        for leaf in leaves:
            ancestors = self._build_ancestors(leaf)
            accumulated = self._collect_artifacts(ancestors)
            results.append(ResumeContext(
                activity_id=activity_id,
                target_node=leaf,
                ancestors=ancestors,
                accumulated_artifacts=accumulated["artifacts"],
                accumulated_input=accumulated["input"],
            ))
        return results

    def _build_ancestors(self, node: ActivityNode) -> list[ActivityNode]:
        """Walk up parents, returning root-first list."""
        ancestors: list[ActivityNode] = []
        current = node
        while current:
            ancestors.append(current)
            if current.parent_id:
                next_node = self._mgr.get_activity(current.parent_id)
                if next_node is None:
                    break
                current = next_node
            else:
                break
        ancestors.reverse()
        return ancestors

    def _collect_artifacts(
        self, ancestors: list[ActivityNode],
    ) -> dict[str, Any]:
        """Accumulate artifacts and input from ancestors and all
        COMPLETED nodes in the same activity.

        This captures artifacts from completed earlier steps even
        when they are in sibling subtrees not on the ancestor chain.
        """
        artifacts: dict[str, str] = {}
        input_data: dict[str, Any] = {}

        # 1. Collect from ancestors themselves
        for node in ancestors:
            artifacts.update(node.artifacts)
            input_data.update(node.input)

        # 2. Collect artifacts from all COMPLETED nodes in the activity
        if ancestors:
            activity_id = ancestors[0].activity_id
            for node in self._mgr.get_tree(activity_id):
                if node.status == ActivityStatus.COMPLETED:
                    artifacts.update(node.artifacts)

        return {"artifacts": artifacts, "input": input_data}

    def mark_resumed(self, ctx: ResumeContext) -> None:
        """Mark the target node and its chain as RUNNING after resume."""
        for node in ctx.ancestors:
            if node.status in (ActivityStatus.PENDING, ActivityStatus.SUSPENDED):
                self._mgr.mark_running(node.node_id)
        self._mgr.mark_running(ctx.target_node.node_id)

    def activity_summary(self, activity_id: str) -> str:
        """Return a human-readable summary of resume status."""
        activity = self._mgr.get_activity(activity_id)
        if not activity:
            return f"Activity {activity_id}: not found"

        tree = self._mgr.get_tree(activity_id)
        leaves = self._mgr.resume_candidates(activity_id)

        lines = [
            f"Activity: {activity.label} ({activity.status.value})",
            f"Total nodes: {len(tree)}",
            f"Incomplete leaves: {len(leaves)}",
        ]
        if leaves:
            lines.append("Resume points (shallowest first):")
            for leaf in leaves:
                lines.append(f"  [{leaf.node_type}] {leaf.label} (depth={leaf.depth}, {leaf.status.value})")
                if leaf.agent_id:
                    lines.append(f"    agent: {leaf.agent_id}")
        return "\n".join(lines)
