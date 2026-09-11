"""Events emitted while executing an agent graph."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentEvent:
    event_type: str
    workflow_id: str | None = None
    node_id: str | None = None
    data: dict[str, Any] = field(default_factory=dict)
