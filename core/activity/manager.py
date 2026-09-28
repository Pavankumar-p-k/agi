"""ActivityManager — builds and maintains the activity graph.

This module is the canonical creator of :class:`ActivityNode`s (Rule 25), so
callers outside the activity package use :func:`make_node` instead of
constructing nodes themselves.
"""
from __future__ import annotations

import uuid
from typing import Any, Optional

from core.activity.models import ActivityEdge, ActivityNode, ActivityStatus


class ActivityManager:
    """In-memory activity graph with tenant-safe parent/child linking."""

    def __init__(self) -> None:
        self.nodes: dict[str, ActivityNode] = {}
        self.edges: list[ActivityEdge] = []

    # ── node management ──────────────────────────────────────────────
    def create_node(self, node: ActivityNode) -> ActivityNode:
        self.nodes[node.node_id] = node
        return node

    def get_node(self, node_id: str) -> Optional[ActivityNode]:
        return self.nodes.get(node_id)

    def link_parent_child(self, parent_id: str, child_id: str) -> None:
        """Link two nodes, rejecting cross-tenant parent/child relations."""
        parent = self.nodes.get(parent_id)
        child = self.nodes.get(child_id)
        if parent is None or child is None:
            raise ValueError("parent and child must exist before linking")
        p_tenant = (parent.resource_scope or {}).get("tenant_id", "default")
        c_tenant = (child.resource_scope or {}).get("tenant_id", "default")
        if p_tenant != c_tenant:
            raise ValueError(
                f"cross-tenant parent/child link rejected: "
                f"parent tenant {p_tenant!r} != child tenant {c_tenant!r}")
        child.parent_id = parent_id
        self.edges.append(ActivityEdge(src=parent_id, dst=child_id))

    def set_status(self, node_id: str, status: ActivityStatus) -> bool:
        node = self.nodes.get(node_id)
        if node is None:
            return False
        node.status = status
        return True

    def children(self, parent_id: str) -> list[ActivityNode]:
        return [n for n in self.nodes.values() if n.parent_id == parent_id]


def make_node(node_type: str, label: str = "", output: Any = None, *,
              activity_id: str = "", parent_id: Optional[str] = None,
              resource_scope: Optional[dict] = None, tenant_id: str = "",
              status: ActivityStatus = ActivityStatus.PENDING,
              node_id: Optional[str] = None, **extra_metadata: Any) -> ActivityNode:
    """Build an :class:`ActivityNode` with tenant scope attached (Rule 25).

    ``resource_scope`` is always populated so every node is tenant-attributable;
    ``output`` is carried in ``metadata`` (the node model has no output field).
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
