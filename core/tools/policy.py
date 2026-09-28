"""Tool policy registry.

Each tool may declare the scope required to execute it. Dispatch code asks
``policy_engine.get_policy(tool_id)`` and then has the policy engine
evaluate the caller's scope.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ToolPolicy:
    """Declared execution policy for a single tool."""

    id: str
    name: str = ""
    required_scope: str = ""
    description: str = ""
    category: str = ""
    enabled: bool = True
    requires_confirmation: bool = False
    metadata: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.id = str(self.id or "").strip()
        if not self.name:
            self.name = self.id
        if self.required_scope is None:
            self.required_scope = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "required_scope": self.required_scope,
            "description": self.description,
            "category": self.category,
            "enabled": self.enabled,
            "requires_confirmation": self.requires_confirmation,
        }


class ToolPolicyEngine:
    """In-memory registry of :class:`ToolPolicy` records."""

    def __init__(self) -> None:
        self._policies: dict[str, ToolPolicy] = {}

    def register(self, policy: ToolPolicy) -> ToolPolicy:
        if not isinstance(policy, ToolPolicy):
            raise TypeError("register() expects a ToolPolicy")
        if not policy.id:
            raise ValueError("ToolPolicy.id is required")
        self._policies[policy.id] = policy
        return policy

    def unregister(self, tool_id: str) -> bool:
        return self._policies.pop(str(tool_id), None) is not None

    def get_policy(self, tool_id: Any) -> Optional[ToolPolicy]:
        if not tool_id:
            return None
        return self._policies.get(str(tool_id))

    def all_policies(self) -> list:
        return list(self._policies.values())

    def ids(self) -> list:
        return sorted(self._policies)

    def clear(self) -> None:
        self._policies.clear()

    def __contains__(self, tool_id: object) -> bool:
        return str(tool_id) in self._policies

    def __len__(self) -> int:
        return len(self._policies)


# Module-level singleton — patched by dispatch tests.
policy_engine = ToolPolicyEngine()


__all__ = ["ToolPolicy", "ToolPolicyEngine", "policy_engine"]
