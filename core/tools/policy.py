# Copyright (c) 2024-2026 JARVIS Project
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("jarvis.tools.policy")


class Requirement:
    """Single availability requirement for a tool."""

    def __init__(self, key: str, value: Any = None, exists: bool = True):
        self.key = key
        self.value = value
        self.exists = exists

    def check(self, context: dict[str, Any]) -> bool:
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
    requirements: list[Requirement] = field(default_factory=list)
    risk_level: str = "low"
    needs_confirmation: bool = False
    required_scope: str | None = None
    rate_limit: int | None = None
    privacy_tier: str = "LOCAL"


class PolicyEngine:
    """Evaluates tool availability against current context."""

    def __init__(self):
        self._policies: dict[str, ToolPolicy] = {}
        self._global_reqs: list[Requirement] = []

    def register(self, policy: ToolPolicy):
        self._policies[policy.id] = policy
        logger.debug("Registered tool policy: %s", policy.id)

    def add_global_requirement(self, req: Requirement):
        self._global_reqs.append(req)

    def is_available(self, tool_id: str, context: dict[str, Any]) -> bool:
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

    def get_policy(self, tool_id: str) -> ToolPolicy | None:
        return self._policies.get(tool_id)


policy_engine = PolicyEngine()

__all__ = ["policy_engine", "ToolPolicy", "Requirement"]
