from __future__ import annotations

import asyncio
import logging
from typing import Any

from core.providers.base import ExecutionProvider, ProviderHealthStatus
from core.providers.memory import ProviderMemory, provider_memory
from core.providers.budget import ProviderBudgetManager, provider_budget
from core.providers.registry import ProviderRegistry, provider_registry

logger = logging.getLogger(__name__)


class ProviderRouter:
    def __init__(
        self,
        registry: ProviderRegistry | None = None,
        memory: ProviderMemory | None = None,
        budget: ProviderBudgetManager | None = None,
    ):
        self._registry = registry or provider_registry
        self._memory = memory or provider_memory
        self._budget = budget or provider_budget
        self._benchmark_store = None

    def _get_benchmark_store(self):
        if self._benchmark_store is None:
            try:
                from core.providers.benchmark_store import BenchmarkStore
                self._benchmark_store = BenchmarkStore()
            except Exception as e:
                logger.debug("[ProviderRouter] Benchmark store unavailable: %s", e)
                self._benchmark_store = False
        return self._benchmark_store if self._benchmark_store else None

    def select(
        self,
        capability: str,
        task: dict[str, Any] | None = None,
        workflow_id: str = "",
        prefer_offline: bool = False,
    ) -> ExecutionProvider | None:
        candidates = self._registry.get_providers_for_capability(capability)
        if not candidates:
            logger.warning("[ProviderRouter] No providers for capability: %s", capability)
            return None

        scored = []
        for provider in candidates:
            if not provider.enabled:
                logger.debug("[ProviderRouter] Skipping disabled provider: %s", provider.provider_id)
                continue

            if not self._budget.can_use(provider.provider_id, workflow_id):
                logger.debug("[ProviderRouter] Skipping over-budget provider: %s", provider.provider_id)
                continue

            if self._memory.should_skip(provider.provider_id):
                logger.debug("[ProviderRouter] Skipping poor-performance provider: %s", provider.provider_id)
                continue

            health = provider.cached_health
            if hasattr(health, '__call__'):
                try:
                    health_result = asyncio.run(provider.cached_health())
                except RuntimeError:
                    health_result = provider._health_cache
            else:
                health_result = provider._health_cache

            if health_result.status == ProviderHealthStatus.DOWN:
                logger.debug("[ProviderRouter] Skipping unhealthy provider: %s (%s)",
                             provider.provider_id, health_result.error)
                continue

            score = self._score(provider, task)
            scored.append((score, provider))

        if not scored:
            return None

        scored.sort(key=lambda x: x[0], reverse=True)
        best = scored[0][1]
        logger.info("[ProviderRouter] Selected %s (score=%.2f) for capability '%s'",
                     best.provider_id, scored[0][0], capability)
        return best

    def select_with_fallback(
        self,
        capability: str,
        task: dict[str, Any] | None = None,
        workflow_id: str = "",
        exclude: set[str] | None = None,
    ) -> list[ExecutionProvider]:
        candidates = self._registry.get_providers_for_capability(capability)
        exclude = exclude or set()

        available = []
        for provider in candidates:
            if provider.provider_id in exclude:
                continue
            if not provider.enabled:
                continue
            if not self._budget.can_use(provider.provider_id, workflow_id):
                continue
            if self._memory.should_skip(provider.provider_id):
                continue

            health_result = provider.cached_health
            if hasattr(health_result, '__call__'):
                try:
                    health_result = asyncio.run(provider.cached_health())
                except RuntimeError:
                    health_result = provider._health_cache
            else:
                health_result = provider._health_cache

            if health_result.status == ProviderHealthStatus.DOWN:
                continue
            available.append(provider)

        scored = sorted(
            available,
            key=lambda p: self._score(p, task),
            reverse=True,
        )
        return scored

    def _score(self, provider: ExecutionProvider, task: dict[str, Any] | None = None) -> float:
        pid = provider.provider_id
        priority = self._registry.get_priority(pid)
        performance = self._memory.get_score(pid)

        base = 0.40 * (priority / 100.0) + 0.30 * performance

        benchmark_bonus = self._benchmark_score(pid, task)
        base += 0.30 * benchmark_bonus

        return base

    def _benchmark_score(self, provider_id: str, task: dict[str, Any] | None = None) -> float:
        store = self._get_benchmark_store()
        if not store or not task:
            return 0.5

        category = task.get("capability", task.get("goal", ""))
        language = task.get("language", "")
        goal = task.get("goal", "").lower()

        best = 0.0
        count = 0

        for cat_key in ["python", "javascript", "typescript", "java", "kotlin",
                         "react", "android", "fastapi", "refactoring", "debugging",
                         "testing", "security", "scaffold"]:
            if cat_key in category or cat_key in goal:
                row = store.get_best_provider(cat_key, language)
                if row and row["provider_id"] == provider_id:
                    quality = row.get("avg_quality", 0)
                    success_rate = row.get("success_rate", 0)
                    score = 0.6 * quality + 0.4 * success_rate
                    best = max(best, score)
                    count += 1

        if count > 0:
            return best
        if language:
            summaries = store.get_summary(provider_id=provider_id)
            lang_scores = [s.avg_quality for s in summaries if s.language == language and s.total_runs >= 2]
            if lang_scores:
                return sum(lang_scores) / len(lang_scores)

        return 0.5


provider_router = ProviderRouter()
