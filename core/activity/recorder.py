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


class ActivityRecorder:
    """Records the activity graph for one run.

    Delegates all node creation to the :class:`ActivityManager` it is given.
    """

    def __init__(self, manager: Optional[ActivityManager] = None) -> None:
        self.manager = manager or ActivityManager()
        self.activity_id: Optional[str] = None
        self.nodes: list = []

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

    # ── recording ───────────────────────────────────────────────────
    def record_goal(self, goal: str, template_id: str = "", *,
                    tenant_id: str = "default", **metadata: Any) -> ActivityNode:
        extra = dict(metadata)
        if template_id:
            extra["template_id"] = template_id
        node = make_node("goal", label=str(goal or ""), tenant_id=tenant_id,
                         **extra)
        self.activity_id = node.node_id
        return self._record(node)

    def record_completion(self, output: Any = None, **metadata: Any) -> Optional[ActivityNode]:
        node = self.activity
        if node is None:
            return None
        from core.activity.models import ActivityStatus

        node.status = ActivityStatus.COMPLETED
        if output is not None:
            node.metadata["output"] = output
        node.metadata.update(metadata)
        return node

    def record_failure(self, error: str, **metadata: Any) -> Optional[ActivityNode]:
        node = self.activity
        if node is None:
            return None
        from core.activity.models import ActivityStatus

        node.status = ActivityStatus.FAILED
        node.metadata["error"] = str(error)
        node.metadata.update(metadata)
        return node

    def record_artifact(self, name: str, artifact_id: Any, **metadata: Any) -> Optional[ActivityNode]:
        if self.activity is None:
            return None
        node = make_node("artifact", label=str(name), output=artifact_id,
                         activity_id=self.activity_id or "",
                         parent_id=self.activity_id)
        return self._record(node)

    # ── queries ─────────────────────────────────────────────────────
    def get_activity_tree(self) -> list:
        if self.activity_id is None:
            return []
        return [n for n in self.nodes if n.activity_id == self.activity_id
                or n.node_id == self.activity_id]

    def get_activity_timeline(self) -> list:
        return list(self.get_activity_tree())


__all__ = ["ActivityRecorder", "make_activity_node", "record_activity_nodes"]
