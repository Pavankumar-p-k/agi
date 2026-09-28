"""AgentEvent — events emitted during parallel graph execution."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentEvent:
    event_type: str = ""
    node_id: str = ""
    agent_id: str = ""
    workflow_id: str = ""
    timestamp: float = field(default_factory=time.time)
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "node_id": self.node_id,
            "agent_id": self.agent_id,
            "workflow_id": self.workflow_id,
            "timestamp": self.timestamp,
            "data": dict(self.data),
        }
