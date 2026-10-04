"""ActivityManager — builds and maintains the activity graph.

This module is the canonical creator of :class:`ActivityNode`s (Rule 25), so
callers outside the activity package use :func:`make_node` instead of
constructing nodes themselves.

All state lives in an :class:`ActivityStore`.  When no store is injected the
manager creates a private in-memory namespace so independent managers stay
isolated from each other.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from core.activity.models import ActivityEdge, ActivityNode, ActivityStatus
from core.activity.storage import ActivityStore


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _store_output(node: ActivityNode, output: Any) -> None:
    if output is None:
        return
    if isinstance(output, dict):
        node.output.update(output)
    else:
        node.output["result"] = output


class ActivityManager:
    """High-level activity graph API with tenant-safe parent/child linking."""

    def __init__(self, store: Optional[ActivityStore] = None) -> None:
        if store is None:
            store = ActivityStore(db_path=f"activity_manager_{uuid.uuid4().hex}")
        self.store = store

    # ── low-level node management (legacy API) ──────────────────────────────
    def create_node(self, node: ActivityNode) -> ActivityNode:
        return self.store.create_node(node)

    def get_node(self, node_id: str) -> Optional[ActivityNode]:
        return self.store.get_node(node_id)

    def set_status(self, node_id: str, status: ActivityStatus) -> bool:
        node = self.store.get_node(node_id)
        if node is None:
            return False
        node.status = status
        node.updated_at = _now()
        return True

    def children(self, parent_id: str) -> list[ActivityNode]:
        return self.store.get_children(parent_id)

    def link_parent_child(self, parent_id: str, child_id: str) -> None:
        """Link two nodes, rejecting cross-tenant parent/child relations."""
        parent = self.store.get_node(parent_id)
        child = self.store.get_node(child_id)
        if parent is None or child is None:
            raise ValueError("parent and child must exist before linking")
        p_tenant = (parent.resource_scope or {}).get("tenant_id", "default")
        c_tenant = (child.resource_scope or {}).get("tenant_id", "default")
        if p_tenant != c_tenant:
            raise ValueError(
                f"cross-tenant parent/child link rejected: "
                f"parent tenant {p_tenant!r} != child tenant {c_tenant!r}")
        child.parent_id = parent_id
        self.store.create_edge(ActivityEdge(from_node_id=parent_id, to_node_id=child_id))

    # ── node factories ──────────────────────────────────────────────────────
    def _as_node(self, ref: Any) -> ActivityNode:
        if isinstance(ref, ActivityNode):
            return ref
        node = self.store.get_node(ref) if ref is not None else None
        if node is None:
            raise ValueError(f"parent node not found: {ref!r}")
        return node

    def _spawn(self, node_type: str, label: str, base: ActivityNode, *,
               status: ActivityStatus = ActivityStatus.PENDING,
               agent_id: Optional[str] = None,
               origin_node_id: Optional[str] = None,
               input_data: Optional[dict] = None,
               **metadata: Any) -> ActivityNode:
        node = make_node(node_type, label, activity_id=base.activity_id,
                         parent_id=base.node_id, status=status, **metadata)
        node.depth = base.depth + 1
        if agent_id is not None:
            node.agent_id = agent_id
        if origin_node_id is not None:
            node.origin_node_id = origin_node_id
        if input_data:
            node.input.update(input_data)
        self.store.create_node(node)
        return node

    def create_activity(self, label: str, **metadata: Any) -> ActivityNode:
        """Create a new root activity (depth 0, RUNNING)."""
        node_id = f"node_{uuid.uuid4().hex[:12]}"
        node = make_node("goal", label, activity_id=node_id, node_id=node_id,
                         status=ActivityStatus.RUNNING, **metadata)
        node.started_at = _now()
        self.store.create_node(node)
        return node

    def create_subgoal(self, parent: Any, label: str = "",
                       step_name: Optional[str] = None,
                       **metadata: Any) -> ActivityNode:
        base = self._as_node(parent)
        node = self._spawn("subgoal", label, base, **metadata)
        if step_name is not None:
            node.input["step_name"] = step_name
        return node

    def create_agent_task(self, activity: Any, agent_id: str, label: str, *,
                          step_name: Optional[str] = None,
                          parent: Any = None,
                          origin_node_id: Optional[str] = None,
                          parameters: Optional[dict] = None,
                          **metadata: Any) -> ActivityNode:
        base = self._as_node(parent) if parent is not None else self._as_node(activity)
        node = self._spawn("agent_call", str(label), base,
                           agent_id=str(agent_id) if agent_id is not None else None,
                           origin_node_id=origin_node_id, **metadata)
        if step_name is not None:
            node.input["step_name"] = step_name
        if parameters:
            node.input.update(parameters)
        return node

    def create_tool_call(self, parent_task: Any, tool_name: str,
                         input_data: Optional[dict] = None,
                         **metadata: Any) -> ActivityNode:
        base = self._as_node(parent_task)
        node = self._spawn("tool_call", str(tool_name), base,
                           agent_id=base.agent_id, input_data=input_data,
                           **metadata)
        node.metadata.setdefault("tool", str(tool_name))
        return node

    def create_artifact_node(self, parent: Any, label: str, artifact_id: str,
                             **metadata: Any) -> ActivityNode:
        base = self._as_node(parent)
        node = self._spawn("artifact", str(label), base,
                           status=ActivityStatus.COMPLETED, **metadata)
        node.artifacts[str(label)] = artifact_id
        node.origin_node_id = base.node_id
        node.completed_at = _now()
        return node

    # ── queries ─────────────────────────────────────────────────────────────
    def get_activity(self, ref: Any) -> Optional[ActivityNode]:
        node = self.store.get_node(ref) if ref is not None else None
        if node is not None:
            return node
        for candidate in self.store.get_all_nodes():
            if candidate.depth == 0 and candidate.activity_id == ref:
                return candidate
        return None

    def get_tree(self, ref: Any) -> list[ActivityNode]:
        if ref is None:
            return []
        tree = self.store.get_activity_tree(ref)
        if not tree:
            node = self.store.get_node(ref)
            if node is not None:
                tree = self.store.get_activity_tree(node.activity_id or node.node_id)
        return tree

    def get_timeline(self, ref: Any) -> list[ActivityNode]:
        if ref is None:
            return []
        timeline = self.store.get_activity_timeline(ref)
        if not timeline:
            node = self.store.get_node(ref)
            if node is not None:
                timeline = self.store.get_activity_timeline(node.activity_id or node.node_id)
        return timeline

    def get_active_activities(self) -> list[ActivityNode]:
        return self.store.get_active_activities()

    def _resolve_root(self, ref: Any) -> Optional[ActivityNode]:
        node = self.store.get_node(ref) if ref is not None else None
        if node is None:
            return None
        if node.depth == 0:
            return node
        tree = self.store.get_activity_tree(node.activity_id or node.node_id)
        if tree and tree[0].depth == 0:
            return tree[0]
        return node

    # ── activity lifecycle ──────────────────────────────────────────────────
    def suspend_activity(self, activity_id: str) -> bool:
        tree = self.get_tree(activity_id)
        if not tree:
            return False
        for node in tree:
            node.status = ActivityStatus.SUSPENDED
            node.updated_at = _now()
        return True

    def complete_activity(self, activity_id: str,
                          output: Any = None) -> Optional[ActivityNode]:
        root = self._resolve_root(activity_id)
        if root is None:
            return None
        root.status = ActivityStatus.COMPLETED
        _store_output(root, output)
        root.completed_at = _now()
        root.updated_at = _now()
        return root

    def fail_activity(self, activity_id: str,
                      error: Any = None) -> Optional[ActivityNode]:
        root = self._resolve_root(activity_id)
        if root is None:
            return None
        root.status = ActivityStatus.FAILED
        if error is not None:
            root.output["error"] = str(error)
        root.completed_at = _now()
        root.updated_at = _now()
        return root

    # ── node status transitions ─────────────────────────────────────────────
    def mark_running(self, node_id: str) -> bool:
        node = self.store.get_node(node_id)
        if node is None:
            return False
        node.status = ActivityStatus.RUNNING
        if node.started_at is None:
            node.started_at = _now()
        node.updated_at = _now()
        return True

    def mark_completed(self, node_id: str, output: Any = None,
                       artifacts: Optional[dict] = None) -> bool:
        node = self.store.get_node(node_id)
        if node is None:
            return False
        node.status = ActivityStatus.COMPLETED
        _store_output(node, output)
        if artifacts:
            node.artifacts.update(artifacts)
        node.completed_at = _now()
        node.updated_at = _now()
        return True

    def mark_failed(self, node_id: str, error: Any = None) -> bool:
        node = self.store.get_node(node_id)
        if node is None:
            return False
        node.status = ActivityStatus.FAILED
        if error is not None:
            node.output["error"] = str(error)
        node.completed_at = _now()
        node.updated_at = _now()
        return True

    # ── edges and workflow linkage ──────────────────────────────────────────
    def add_dependency(self, from_node_id: str, to_node_id: str) -> ActivityEdge:
        edge = ActivityEdge(from_node_id=from_node_id, to_node_id=to_node_id,
                            edge_type="depends_on")
        return self.store.create_edge(edge)

    def add_produces(self, from_node_id: str, to_node_id: str) -> ActivityEdge:
        edge = ActivityEdge(from_node_id=from_node_id, to_node_id=to_node_id,
                            edge_type="produces")
        return self.store.create_edge(edge)

    def link_workflow(self, node_id: str, workflow_id: str) -> bool:
        node = self.store.get_node(node_id)
        if node is None:
            return False
        node.workflow_id = workflow_id
        node.updated_at = _now()
        return True

    # ── resume / summarize ──────────────────────────────────────────────────
    def resume_candidates(self, activity_id: str) -> list[ActivityNode]:
        tree = self.get_tree(activity_id)
        if not tree:
            return []
        blocked = {ActivityStatus.PENDING, ActivityStatus.RUNNING,
                   ActivityStatus.SUSPENDED}
        live = {ActivityStatus.PENDING, ActivityStatus.RUNNING}
        candidates = []
        for node in tree:
            if node.status not in live:
                continue
            has_active_child = any(
                child.parent_id == node.node_id and child.status in blocked
                for child in tree)
            if not has_active_child:
                candidates.append(node)
        return candidates

    def summarize(self, activity_id: str) -> dict[str, Any]:
        tree = self.get_tree(activity_id)
        if not tree:
            return {"error": f"activity not found: {activity_id}"}
        root = next((n for n in tree if n.depth == 0), tree[0])
        by_status: dict[str, int] = {}
        for node in tree:
            key = getattr(node.status, "name", str(node.status)).upper()
            by_status[key] = by_status.get(key, 0) + 1
        return {
            "activity_id": str(activity_id),
            "goal": root.label,
            "status": getattr(root.status, "name", str(root.status)).upper(),
            "total_nodes": len(tree),
            "depth": max((n.depth for n in tree), default=0),
            "by_status": by_status,
            "agents_used": sorted({n.agent_id for n in tree if n.agent_id}),
            "created_at": root.created_at.isoformat() if root.created_at else None,
        }


def make_node(node_type: str, label: str = "", output: Any = None, *,
              activity_id: str = "", parent_id: Optional[str] = None,
              resource_scope: Optional[dict] = None, tenant_id: str = "",
              status: ActivityStatus = ActivityStatus.PENDING,
              node_id: Optional[str] = None, **extra_metadata: Any) -> ActivityNode:
    """Build an :class:`ActivityNode` with tenant scope attached (Rule 25).

    ``resource_scope`` is always populated so every node is tenant-attributable;
    ``output`` is carried in ``metadata`` for legacy callers.
    """
    scope = dict(resource_scope or {})
    if tenant_id and not scope.get("tenant_id"):
        scope["tenant_id"] = tenant_id
    metadata = dict(extra_metadata)
    if output is not None:
        metadata["output"] = output
    return ActivityNode(
        node_id=node_id or f"node_{uuid.uuid4().hex[:12]}",
        activity_id=activity_id,
        node_type=node_type,
        label=label,
        status=status,
        parent_id=parent_id,
        resource_scope=scope,
        metadata=metadata,
    )


__all__ = ["ActivityManager", "make_node"]
