from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional

from jarvis_os.contracts import ToolSpec

ToolHandler = Callable[..., Any]


@dataclass(slots=True)
class ToolDefinition:
    name: str
    description: str
    category: str = "general"
    permission: str = "standard"
    input_schema: Dict[str, Any] = field(default_factory=dict)
    capabilities: List[str] = field(default_factory=list)
    risk_tags: List[str] = field(default_factory=list)
    read_only: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)
    handler: Optional[ToolHandler] = None

    def to_router_spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            capabilities=list(self.capabilities),
            risk_tags=list(self.risk_tags),
            read_only=self.read_only,
            category=self.category,
            permission=self.permission,
            input_schema=dict(self.input_schema),
            metadata=dict(self.metadata),
        )
