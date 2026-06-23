"""ActivityRecorder — planner-side recording of activities.

Plugs into PlannerStateMachine to record every phase of execution
as activity graph nodes. When no recorder is configured, the planner
runs exactly as before (zero-overhead opt-in).
"""

from __future__ import annotations

import logging
from typing import Any

from core.activity.manager import ActivityManager
from core.activity.models import ActivityNode
from core.planner.models import SubGoal

logger = logging.getLogger(__name__)


class ActivityRecorder:
    """Records planner phase transitions as activity graph nodes.

    Usage:
        recorder = ActivityRecorder(mgr)
        recorder.record_goal(goal)           # → root ActivityNode
        recorder.record_subgoals(plan)       # → subgoal nodes
        recorder.record_agent_tasks(tasks)   # → agent_call nodes
        recorder.record_completion(result)   # → marks COMPLETED
        recorder.record_failure(error)       # → marks FAILED
    """

    def __init__(self, manager: ActivityManager):
        self._mgr = manager
        self._activity: ActivityNode | None = None
        self._subgoal_map: dict[str, ActivityNode] = {}  # subgoal_id → ActivityNode
        self._agent_task_map: dict[str, ActivityNode] = {}  # task_key → ActivityNode

    @property
    def activity_id(self) -> str | None:
        return self._activity.activity_id if self._activity else None

    @property
    def activity(self) -> ActivityNode | None:
        return self._activity

    # ── Recording hooks ────────────────────────────────────────────────────

    def record_goal(self, goal: str, template_id: str | None = None) -> ActivityNode:
        """Create the root activity node for a user goal."""
        metadata = {"template_id": template_id} if template_id else {}
        self._activity = self._mgr.create_activity(goal, metadata=metadata)
        logger.info("ActivityRecorder: recorded goal activity=%s template=%s",
                    self._activity.node_id, template_id)
        return self._activity

    def record_subgoals(self, plan: SubGoal) -> None:
        """Walk the SubGoal tree and create subgoal nodes for each leaf."""
        if not self._activity:
            return
        for leaf in plan.flatten():
            parent = self._activity
            # Find the closest ancestor ActivityNode
            # (in a flat list of leaves, all have parent=root)
            node = self._mgr.create_subgoal(
                self._activity,
                leaf.description,
                step_name=leaf.step_name,
                metadata={
                    "subgoal_id": leaf.id,
                    "template_id": leaf.template_id,
                    "agent_id": leaf.agent_id,
                    "parameters": leaf.parameters,
                },
            )
            self._subgoal_map[leaf.id] = node

    def record_agent_tasks(self, tasks: list[dict[str, Any]]) -> None:
        """Create agent_call nodes for each agent task."""
        if not self._activity:
            return
        for task in tasks:
            agent_id = task.get("agent_id") or "unknown"
            goal = task.get("goal") or task.get("description", "")
            step = task.get("step") or agent_id
            # Try to link to the matching subgoal if subgoal_map was populated
            parent = self._activity
            node = self._mgr.create_agent_task(
                self._activity,
                agent_id,
                goal,
                step_name=step,
                parent=parent,
                input_data=task.get("parameters") or {},
            )
            task_key = _task_key(task)
            self._agent_task_map[task_key] = node

    def record_task_artifacts(self, task: dict[str, Any],
                               artifacts: dict[str, str]) -> None:
        """Record artifacts produced by an agent task."""
        task_key = _task_key(task)
        node = self._agent_task_map.get(task_key)
        if node:
            self._mgr.mark_completed(node.node_id, artifacts=artifacts)

    def record_task_result(self, task: dict[str, Any],
                            success: bool, output: dict[str, Any] | None = None,
                            error: str | None = None) -> None:
        """Record completion or failure of an agent task."""
        task_key = _task_key(task)
        node = self._agent_task_map.get(task_key)
        if not node:
            return
        if success:
            self._mgr.mark_completed(node.node_id, output=output,
                                      artifacts=output.get("artifacts") if output else None)
        else:
            self._mgr.mark_failed(node.node_id, error or "Unknown error")

    def record_completion(self, result: dict[str, Any]) -> None:
        """Mark the entire activity as COMPLETED."""
        if not self._activity:
            return
        output = {"result": result.get("state"), "summary": str(result.get("verification", ""))}
        self._mgr.complete_activity(self._activity.node_id, output=output)

    def record_failure(self, error: str) -> None:
        """Mark the entire activity as FAILED."""
        if not self._activity:
            return
        self._mgr.fail_activity(self._activity.node_id, error)

    def link_workflow(self, workflow_id: str) -> None:
        """Link all recorded nodes to a workflow."""
        if not self._activity:
            return
        self._mgr.link_workflow(self._activity.node_id, workflow_id)
        for node in self._subgoal_map.values():
            self._mgr.link_workflow(node.node_id, workflow_id)

    def record_artifact(self, task: dict[str, Any], name: str,
                         artifact_id: str) -> None:
        """Record a specific artifact produced by a task."""
        task_key = _task_key(task)
        parent = self._agent_task_map.get(task_key) or self._activity
        if parent:
            self._mgr.create_artifact_node(parent, name, artifact_id)

    # ── Queries ────────────────────────────────────────────────────────────

    def get_activity_tree(self) -> list[ActivityNode]:
        if not self._activity:
            return []
        return self._mgr.get_tree(self._activity.node_id)

    def get_activity_timeline(self) -> list[ActivityNode]:
        if not self._activity:
            return []
        return self._mgr.get_timeline(self._activity.node_id)


def _task_key(task: dict[str, Any]) -> str:
    """Unique key for an agent task dict."""
    return f"{task.get('agent_id', '?')}:{task.get('goal', '?')}::{task.get('step', '?')}"
