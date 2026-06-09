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
"""
governance/RuntimeGovernanceLayer.py
Lightweight runtime governance — enforces request budget, concurrency, 
and timeout constraints at the API boundary.
"""
from __future__ import annotations
import asyncio
import time
import logging
from pydantic.v1.dataclasses import dataclass
from dataclasses import field
from typing import Optional, Dict, Any, Callable, Awaitable

logger = logging.getLogger("jarvis.governance.runtime")


@dataclass
class RequestBudget:
    max_tokens: int = 8192
    max_duration_s: float = 120.0
    max_retries: int = 3


@dataclass
class RuntimeDecision:
    allowed: bool
    reason: str
    remaining_budget: Optional[Dict[str, Any]] = None


class RuntimeGovernanceLayer:
    """
    Enforces runtime policies:
    - Request budget (tokens, duration)
    - Concurrency limits per user/agent
    - Circuit breaker on repeated failures
    """

    def __init__(
        self,
        max_concurrent_per_user: int = 5,
        global_max_concurrent: int = 50,
        default_budget: Optional[RequestBudget] = None,
    ):
        self._max_per_user = max_concurrent_per_user
        self._global_max = global_max_concurrent
        self._default_budget = default_budget or RequestBudget()
        self._user_counts: Dict[str, int] = {}
        self._global_count: int = 0
        self._failure_counts: Dict[str, int] = {}
        self._lock = asyncio.Lock()

    async def check_and_acquire(
        self, user_id: str, budget: Optional[RequestBudget] = None
    ) -> RuntimeDecision:
        async with self._lock:
            if self._global_count >= self._global_max:
                return RuntimeDecision(
                    allowed=False,
                    reason=f"Global concurrency limit ({self._global_max}) reached"
                )
            user_count = self._user_counts.get(user_id, 0)
            if user_count >= self._max_per_user:
                return RuntimeDecision(
                    allowed=False,
                    reason=f"User concurrency limit ({self._max_per_user}) reached for {user_id}"
                )
            failures = self._failure_counts.get(user_id, 0)
            if failures >= 10:
                return RuntimeDecision(
                    allowed=False,
                    reason=f"Circuit breaker open for {user_id} ({failures} recent failures)"
                )
            self._user_counts[user_id] = user_count + 1
            self._global_count += 1
            budget = budget or self._default_budget
            return RuntimeDecision(
                allowed=True,
                reason="ok",
                remaining_budget={
                    "max_tokens": budget.max_tokens,
                    "max_duration_s": budget.max_duration_s,
                }
            )

    async def release(self, user_id: str, success: bool = True) -> None:
        async with self._lock:
            self._user_counts[user_id] = max(0, self._user_counts.get(user_id, 1) - 1)
            self._global_count = max(0, self._global_count - 1)
            if not success:
                self._failure_counts[user_id] = self._failure_counts.get(user_id, 0) + 1
            else:
                self._failure_counts[user_id] = max(0, self._failure_counts.get(user_id, 0) - 1)

    def get_stats(self) -> Dict[str, Any]:
        return {
            "global_count": self._global_count,
            "user_counts": dict(self._user_counts),
            "failure_counts": {k: v for k, v in self._failure_counts.items() if v > 0},
        }


# Singleton for app-wide use
runtime_governance = RuntimeGovernanceLayer()

__all__ = ["RuntimeGovernanceLayer", "RuntimeDecision", "RequestBudget", "runtime_governance"]
