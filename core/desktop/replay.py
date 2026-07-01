from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReplayNode:
    node_id: str
    action: str
    details: dict[str, Any]
    timestamp: float
    parent_id: str | None = None

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "action": self.action,
            "details": dict(self.details),
            "timestamp": self.timestamp,
            "parent_id": self.parent_id,
        }


class ReplayGraph:
    def __init__(self) -> None:
        self._nodes: list[ReplayNode] = []
        self._last_id: str | None = None

    def record(self, action: str, details: dict[str, Any] | None = None) -> ReplayNode:
        node = ReplayNode(
            node_id=f"replay_{uuid.uuid4().hex[:12]}",
            action=action,
            details=details or {},
            timestamp=time.time(),
            parent_id=self._last_id,
        )
        self._nodes.append(node)
        self._last_id = node.node_id
        logger.debug("[Replay] %s — %s", action, details)
        return node

    @property
    def nodes(self) -> tuple[ReplayNode, ...]:
        return tuple(self._nodes)

    @property
    def last(self) -> ReplayNode | None:
        return self._nodes[-1] if self._nodes else None

    def to_dict(self) -> list[dict]:
        return [n.to_dict() for n in self._nodes]

    def clear(self) -> None:
        self._nodes.clear()
        self._last_id = None


desktop_replay = ReplayGraph()
