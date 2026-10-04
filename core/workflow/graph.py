"""Execution graph: goal decomposition tree with persistence support."""

from __future__ import annotations

from dataclasses import dataclass, field

MAX_ESTIMATE_SECONDS = 86400.0


@dataclass
class ExecutionNode:
    """One node of an execution graph."""

    label: str = ""
    node_type: str = ""
    status: str = ""
    confidence: float = 0.0
    estimate_seconds: float = 0.0
    detail: str = ""
    trust_level: str = ""
    can_skip: bool = False
    can_reorder: bool = False
    files: list = field(default_factory=list)
    artifacts: list = field(default_factory=list)
    logs: list = field(default_factory=list)
    agent_reasoning: str = ""
    error: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    children: list = field(default_factory=list)

    def __post_init__(self) -> None:
        try:
            self.estimate_seconds = min(float(self.estimate_seconds or 0.0),
                                        MAX_ESTIMATE_SECONDS)
        except (TypeError, ValueError):
            self.estimate_seconds = 0.0

    def add_child(self, node: "ExecutionNode") -> "ExecutionNode":
        self.children.append(node)
        return node

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "node_type": self.node_type,
            "status": self.status,
            "confidence": self.confidence,
            "estimate_seconds": self.estimate_seconds,
            "detail": self.detail,
            "trust_level": self.trust_level,
            "can_skip": self.can_skip,
            "can_reorder": self.can_reorder,
            "files": list(self.files or []),
            "artifacts": list(self.artifacts or []),
            "logs": list(self.logs or []),
            "agent_reasoning": self.agent_reasoning,
            "error": self.error,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "children": [c.to_dict() for c in (self.children or [])],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ExecutionNode":
        data = data or {}
        node = cls(
            label=data.get("label", ""),
            node_type=data.get("node_type", ""),
            status=data.get("status", ""),
            confidence=float(data.get("confidence", 0.0) or 0.0),
            estimate_seconds=float(data.get("estimate_seconds", 0.0) or 0.0),
            detail=data.get("detail", ""),
            trust_level=data.get("trust_level", ""),
            can_skip=bool(data.get("can_skip", False)),
            can_reorder=bool(data.get("can_reorder", False)),
            files=list(data.get("files") or []),
            artifacts=list(data.get("artifacts") or []),
            logs=list(data.get("logs") or []),
            agent_reasoning=data.get("agent_reasoning", ""),
            error=data.get("error"),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
        )
        node.children = [cls.from_dict(c) for c in (data.get("children") or [])]
        return node


@dataclass
class ExecutionGraph:
    """Rooted execution graph for one goal."""

    goal: str = ""
    goal_id: str = ""
    root: ExecutionNode | None = None

    def set_root(self, node: ExecutionNode) -> None:
        self.root = node

    def to_dict(self) -> dict:
        return {
            "goal": self.goal,
            "goal_id": self.goal_id,
            "root": self.root.to_dict() if self.root is not None else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ExecutionGraph":
        data = data or {}
        graph = cls(
            goal=data.get("goal", ""),
            goal_id=data.get("goal_id", ""),
        )
        root = data.get("root")
        if root:
            graph.root = ExecutionNode.from_dict(root)
        return graph
