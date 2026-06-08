from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("jarvis.tools.policy")


class Requirement:
    """Single availability requirement for a tool."""

    def __init__(self, key: str, value: Any = None, exists: bool = True):
        self.key = key
        self.value = value
        self.exists = exists

    def check(self, context: Dict[str, Any]) -> bool:
        if self.key not in context:
            return False
        if self.exists and self.value is None:
            return context[self.key] is not None
        if self.value is not None:
            return context.get(self.key) == self.value
        return True


@dataclass
class ToolPolicy:
    id: str
    name: str
    description: str = ""
    requirements: List[Requirement] = field(default_factory=list)
    risk_level: str = "low"
    needs_confirmation: bool = False
    required_scope: Optional[str] = None
    rate_limit: Optional[int] = None
    privacy_tier: str = "LOCAL"


class PolicyEngine:
    """Evaluates tool availability against current context."""

    def __init__(self):
        self._policies: Dict[str, ToolPolicy] = {}
        self._global_reqs: List[Requirement] = []

    def register(self, policy: ToolPolicy):
        self._policies[policy.id] = policy
        logger.debug("Registered tool policy: %s", policy.id)

    def add_global_requirement(self, req: Requirement):
        self._global_reqs.append(req)

    def is_available(self, tool_id: str, context: Dict[str, Any]) -> bool:
        for req in self._global_reqs:
            if not req.check(context):
                return False
        policy = self._policies.get(tool_id)
        if not policy:
            return True
        for req in policy.requirements:
            if not req.check(context):
                return False
        return True

    def get_policy(self, tool_id: str) -> Optional[ToolPolicy]:
        return self._policies.get(tool_id)


policy_engine = PolicyEngine()

__all__ = ["policy_engine", "ToolPolicy", "Requirement"]
