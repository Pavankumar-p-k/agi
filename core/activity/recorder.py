"""Activity recording utility.

Node creation is delegated to :class:`ActivityManager` (the canonical creator,
Rule 25) so planners and specialists can record activity graphs without
importing the activity owner modules directly (Rule 5).
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

from core.activity.manager import ActivityManager, make_node
from core.activity.models import ActivityNode
from core.activity.storage import ActivityStore


def make_activity_node(node_type: str, label: str = "", output: Any = None, *,
                       activity_id: str = "", parent_id: Optional[str] = None,
                       resource_scope: Optional[dict] = None,
                       tenant_id: str = "", node_id: Optional[str] = None,
                       **metadata: Any) -> ActivityNode:
    """Build an activity node with tenant scope attached.

    Thin re-export of the manager's factory so callers outside the activity
    package have a sanctioned way to create nodes.
    """
    return make_node(
        node_type, label, output, activity_id=activity_id, parent_id=parent_id,
        resource_scope=resource_scope, tenant_id=tenant_id, node_id=node_id,
        **metadata,
    )


def record_activity_nodes(nodes: Iterable[ActivityNode],
                          store: Optional[ActivityStore] = None) -> list:
    """Persist *nodes*; duplicate ids are tolerated."""
    store = store or ActivityStore()
    saved = []
    for node in nodes or ():
        try:
            saved.append(store.create_node(node))
        except ValueError:
            continue
    return saved


def _task_value(task: Any, key: str, default: Any = None) -> Any:
    if isinstance(task, dict):
        return task.get(key, default)
    return getattr(task, key, default)


class ActivityRecorder:
    """Records the activity graph for one run.

    Delegates all node creation to the :class:`ActivityManager` it is given.
    """

    def __init__(self, manager: Optional[ActivityManager] = None) -> None:
        self.manager = manager or ActivityManager()
        self.activity_id: Optional[str] = None
        self.nodes: list[ActivityNode] = []

    # ── helpers ─────────────────────────────────────────────────────
    def _record(self, node: ActivityNode) -> ActivityNode:
        try:
            self.manager.create_node(node)
        except ValueError:
            pass
        self.nodes.append(node)
        return node

    @property
    def activity(self) -> Optional[ActivityNode]:
        if self.activity_id is None:
            return None
        return self.manager.get_node(self.activity_id)

    def _find_task_node(self, task: Any) -> Optional[ActivityNode]:
        if isinstance(task, ActivityNode):
            return task if task.node_type == "agent_call" else None
        agent_id = _task_value(task, "agent_id")
        goal = _task_value(task, "goal")
        agent_match: Optional[ActivityNode] = None
        for node in reversed(self.nodes):
            if node.node_type != "agent_call":
                continue
            if agent_id is not None and node.agent_id != agent_id:
                continue
            if goal is not None and node.label == goal:
                return node
            if agent_match is None:
                agent_match = node
        return agent_match

    # ── recording ───────────────────────────────────────────────────
    def record_goal(self, goal: str, template_id: str = "", *,
                    tenant_id: str = "default", **metadata: Any) -> ActivityNode:
        extra = dict(metadata)
        if template_id:
            extra["template_id"] = template_id
        node = self.manager.create_activity(str(goal or ""),
                                            tenant_id=tenant_id, **extra)
        self.activity_id = node.node_id
        return self._record(node)

    def record_subgoals(self, plan: Any) -> None:
        root = self.activity
        if root is None or plan is None:
            return

        def walk(parent_plan: Any, parent_node: ActivityNode) -> None:
            for child in (getattr(parent_plan, "children", None) or []):
                node = self.manager.create_subgoal(
                    parent_node, str(getattr(child, "description", "") or ""),
                    step_name=getattr(child, "step_name", None))
                self._record(node)
                walk(child, node)

        walk(plan, root)

    def record_agent_tasks(self, tasks: Iterable[Any]) -> None:
        if self.activity is None:
            return
        for task in tasks or ():
            node = self.manager.create_agent_task(
                self.activity,
                str(_task_value(task, "agent_id", "") or ""),
                str(_task_value(task, "goal", "") or ""),
                step_name=_task_value(task, "step"),
                parameters=_task_value(task, "parameters"),
            )
            self._record(node)

    def record_task_result(self, task: Any, success: bool,
                           output: Any = None,
                           error: Any = None) -> Optional[ActivityNode]:
        node = self._find_task_node(task)
        if node is None:
            return None
        if success:
            artifacts = output.get("artifacts") if isinstance(output, dict) else None
            self.manager.mark_completed(node.node_id, output=output,
                                        artifacts=artifacts)
        else:
            self.manager.mark_failed(node.node_id,
                                     error if error is not None else "task failed")
        return node

    def record_task_artifacts(self, task: Any,
                              artifacts: dict) -> Optional[ActivityNode]:
        node = self._find_task_node(task)
        if node is None:
            return None
        self.manager.mark_completed(node.node_id, artifacts=artifacts)
        return node

    def record_completion(self, output: Any = None,
                          **metadata: Any) -> Optional[ActivityNode]:
        if self.activity_id is None:
            return None
        node = self.manager.complete_activity(self.activity_id, output=output)
        if node is not None and metadata:
            node.metadata.update(metadata)
        return node

    def record_failure(self, error: Any, **metadata: Any) -> Optional[ActivityNode]:
        if self.activity_id is None:
            return None
        node = self.manager.fail_activity(self.activity_id, error)
        if node is not None and metadata:
            node.metadata.update(metadata)
        return node

    def record_artifact(self, task: Any, name: str, artifact_id: Any,
                        **metadata: Any) -> Optional[ActivityNode]:
        if self.activity is None:
            return None
        parent = self._find_task_node(task) or self.activity
        node = self.manager.create_artifact_node(parent, str(name), artifact_id)
        if metadata:
            node.metadata.update(metadata)
        return self._record(node)

    def link_workflow(self, workflow_id: str) -> None:
        for node in self.get_activity_tree():
            self.manager.link_workflow(node.node_id, workflow_id)

    # ── queries ─────────────────────────────────────────────────────
    def get_activity_tree(self) -> list[ActivityNode]:
        if self.activity_id is None:
            return []
        return [n for n in self.nodes if n.activity_id == self.activity_id
                or n.node_id == self.activity_id]

    def get_activity_timeline(self) -> list[ActivityNode]:
        return sorted(self.get_activity_tree(),
                      key=lambda n: n.created_at.isoformat() if n.created_at
                      else n.node_id)


__all__ = ["ActivityRecorder", "make_activity_node", "record_activity_nodes"]
