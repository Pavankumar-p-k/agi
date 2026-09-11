from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ToolPolicy:
    id: str
    name: str
    required_scope: str


class ToolPolicyEngine:
    def __init__(self) -> None:
        self.policies: dict[str, ToolPolicy] = {}

    def register(self, policy: ToolPolicy) -> None:
        self.policies[policy.id] = policy

    def get(self, tool_name: str) -> ToolPolicy | None:
        return self.policies.get(tool_name)


policy_engine = ToolPolicyEngine()
