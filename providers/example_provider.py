from __future__ import annotations

import logging
import time
from typing import Any

from core.providers.base import (
    ExecutionProvider,
    ExecutionResult,
    ProviderCapabilities,
    ProviderHealth,
    ProviderHealthStatus,
)

logger = logging.getLogger(__name__)


class Provider(ExecutionProvider):
    provider_id = "example_search"
    name = "Example Search Provider"
    version = "1.0.0"
    priority = 80
    installed = True

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            capability_names=["search", "web_search", "knowledge_retrieval"],
            features=["web_search", "cached_search"],
        )

    async def health(self) -> ProviderHealth:
        return ProviderHealth(
            status=ProviderHealthStatus.HEALTHY,
            latency_ms=0.0,
            last_checked=time.time(),
        )

    async def execute(self, task: dict[str, Any], context: dict[str, Any] | None = None) -> ExecutionResult:
        start = time.monotonic()
        query = task.get("query", task.get("goal", ""))
        elapsed = (time.monotonic() - start) * 1000
        return ExecutionResult(
            success=True,
            output=f"Example search result for: {query}",
            exit_code=0,
            duration_ms=elapsed,
            metadata={"provider": "example_search", "query": query},
        )

    async def estimate_cost(self, task: dict[str, Any]) -> float:
        return 0.0

    async def estimate_latency(self, task: dict[str, Any]) -> float:
        return 50.0
