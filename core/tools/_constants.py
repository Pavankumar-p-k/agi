"""Shared tool parsing constants."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


TOOL_TAGS = frozenset({
    "build_project", "repair_project", "run_tests", "runtime_validate", "cancel_build",
    "manage_memory", "create_session", "chat_with_model",
})


@dataclass
class ToolBlock:
    tool_type: str
    arguments: Any = None

    @property
    def tool(self) -> str:
        return self.tool_type

    @property
    def content(self) -> Any:
        return self.arguments

    def to_dict(self) -> dict[str, Any]:
        return {"tool": self.tool_type, "arguments": self.arguments}
