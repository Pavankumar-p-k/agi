from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class ToolResult:
    output: str = ""
    error: str | None = None
    retryable: bool = False

    def is_ok(self) -> bool:
        return self.error is None


@dataclass
class ToolDefinition:
    name: str
    description: str
    category: str = "general"
    input_schema: dict[str, Any] = field(default_factory=dict)
    handler: Callable | None = None
    read_only: bool = False
    risk_tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    permission: str | None = None
    capabilities: list[str] = field(default_factory=list)
    examples: list[dict] | None = None
