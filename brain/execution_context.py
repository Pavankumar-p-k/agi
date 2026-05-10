from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class BrainExecutionContext:
    goal: str = ""
    prompt: Optional[str] = None
    user_id: str = "system"
    session_id: str = "root"
    platform: str = "chat"
    context: Dict[str, Any] = field(default_factory=dict)
    variables: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    permissions: List[str] = field(default_factory=lambda: ["read", "execute"])
    working_directory: Optional[str] = None
    timeout: int = 300
    max_retries: int = 3

    @property
    def effective_prompt(self) -> str:
        return self.prompt or self.goal or ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "goal": self.goal,
            "prompt": self.prompt,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "platform": self.platform,
            "context": self.context,
            "variables": self.variables,
            "metadata": self.metadata,
            "permissions": self.permissions,
            "working_directory": self.working_directory,
            "timeout": self.timeout,
            "max_retries": self.max_retries,
        }
