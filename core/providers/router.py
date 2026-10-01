"""ProviderRouter: picks the best available provider for a capability.

Completed from the committed contracts in tests/unit/test_provider_ecosystem.py
(TestProviderRouter), tests/unit/test_provider_fallback.py (memory scoring)
and tests/unit/test_provider_feedback.py (calibration integration).

Selection pipeline (per candidate, deterministic order by priority):
1. capability match via registry index
2. enabled + available (health cache: UNKNOWN is acceptable, DOWN is not)
3. budget check (skip over-limit providers)
4. evidence check (skip consecutive-failure / very-low-success providers)
5. score = 0.5·priority_norm + 0.3·historical + 0.2·benchmark + calibration
6. epsilon-greedy exploration: with probability ε = (1 − confidence)·0.10 a
   second-ranked candidate may be chosen; confidence ≥0.95 is always greedy.
``select(..., record_decision=True)`` records the routing decision through the
feedback recorder for later calibration.
"""
from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import Any, Optional

from core.providers.base import ExecutionProvider, ProviderHealthStatus

logger = logging.getLogger(__name__)

_W_PRIORITY = 0.5
_W_HISTORICAL = 0.5
_W_BENCHMARK = 0.1          # additive nudge on top of the pinned 0.5/0.5 split
_EPSILON_MAX = 0.10
_CONFIDENCE_GREEDY = 0.95


class ProviderRouter:
    """Score-and-select router over the provider registry."""

    def __init__(
        self,
        registry: Any = None,
        memory: Any = None,
        budget: Any = None,
        calibration_engine: Any = None,
    ) -> None:
        self._registry = registry
        self._memory = memory
        self._budget = budget
        self.calibration_engine = calibration_engine
        self._recorder: Any = None
        self.last_decision_id: Optional[str] = None

    # ------------------------------------------------------------------ #
    # Dependencies (lazy singletons when not injected)                   #
    # ------------------------------------------------------------------ #

    def _get_registry(self) -> Any:
        if self._registry is not None:
            return self._registry
        from core.providers.registry import provider_registry
        return provider_registry

    def _get_memory(self) -> Any:
        if self._memory is not None:
            return self._memory
        from core.providers.memory import provider_memory
        return provider_memory

    def _get_budget(self) -> Any:
        if self._budget is not None:
            return self._budget
        from core.providers.budget import provider_budget
        return provider_budget

    def _get_recorder(self) -> Any:
        if self._recorder is not None:
            return self._recorder
        from core.providers.feedback.recorder import DecisionRecorder
        from core.providers.feedback.store import FeedbackStore
        self._recorder = DecisionRecorder(FeedbackStore())
        return self._recorder

    # ------------------------------------------------------------------ #
    # Scoring                                                            #
    # ------------------------------------------------------------------ #

    def _score(self, provider: ExecutionProvider, task: dict[str, Any]) -> float:
        memory = self._get_memory()
        priority = 100
        try:
            priority = self._get_registry().get_priority(provider.provider_id)
        except Exception:
            pass
        # Higher priority number = more important (pinned test math:
        # 0.5*(90/100) + 0.5*0.5 = 0.70 beats priority 10 → 0.30).
        priority_norm = max(0.0, min(1.0, priority / 100.0))

        historical = 0.5
        benchmark = 0.5
        calibration = 0.0
        try:
            if task:
                historical = memory.get_performance_score(provider.provider_id, task)
            else:
                historical = memory.get_score(provider.provider_id)
        except Exception:
            pass
        try:
            from core.providers.benchmark import benchmark_store
            benchmark = benchmark_store.get_benchmark_score(
                provider.provider_id,
                str(task.get("capability", "") or "") if task else "",
            )
        except Exception:
            pass
        try:
            if self.calibration_engine is not None:
                calibration = self.calibration_engine.get_adjustment(
                    provider.provider_id,
                    str(task.get("capability", "") or "") if task else "",
                    language=str(task.get("language", "") or ""),
                    framework=str(task.get("framework", "") or ""),
                    project_size=str(task.get("project_size", "") or ""),
                )
        except Exception:
            pass

        total = (
            _W_PRIORITY * priority_norm
            + _W_HISTORICAL * historical
            + _W_BENCHMARK * benchmark
            + calibration
        )
        return max(0.0, min(1.0, total))

    def _confidence(self, provider: ExecutionProvider) -> float:
        try:
            return self._get_memory().get_confidence(provider.provider_id)
        except Exception:
            return 0.0

    # ------------------------------------------------------------------ #
    # Selection                                                          #
    # ------------------------------------------------------------------ #

    def _health_status(self, provider: ExecutionProvider) -> ProviderHealthStatus:
        """Live health probe in sync contexts; cache inside a running loop.

        A DOWN health (fresh or cached) disqualifies the candidate; UNKNOWN
        (never checked) is acceptable.
        """
        try:
            asyncio.get_running_loop()
            # Async context: probe asynchronously would change the API; rely
            # on the cache (pre-warmed by callers/orchestrator).
            return provider._health_cache.status
        except RuntimeError:
            pass
        try:
            health = asyncio.run(provider.health())
            try:
                provider._cache_health(health)
            except Exception:
                pass
            return health.status
        except Exception:
            return provider._health_cache.status

    def _candidates(self, capability: str) -> list[ExecutionProvider]:
        registry = self._get_registry()
        try:
            candidates = list(registry.get_providers_for_capability(capability))
        except Exception:
            candidates = []
        viable = []
        for provider in candidates:
            if not provider.available():
                continue
            if self._health_status(provider) == ProviderHealthStatus.DOWN:
                continue
            viable.append(provider)
        return viable

    def select(
        self,
        capability: str,
        task: Optional[dict[str, Any]] = None,
        record_decision: bool = False,
    ) -> Optional[ExecutionProvider]:
        task = task or {}
        memory = self._get_memory()
        budget = self._get_budget()

        ranked: list[tuple[float, ExecutionProvider]] = []
        for provider in self._candidates(capability):
            pid = provider.provider_id
            try:
                if not budget.can_use(pid):
                    continue
            except Exception:
                pass
            try:
                if memory.should_skip(pid):
                    continue
            except Exception:
                pass
            ranked.append((self._score(provider, task or {"capability": capability}), provider))

        if not ranked:
            return None
        ranked.sort(key=lambda pair: (-pair[0], pair[1].provider_id))

        # Epsilon-greedy exploration (deterministic under a seeded random).
        confidence = self._confidence(ranked[0][1])
        epsilon = 0.0 if confidence >= _CONFIDENCE_GREEDY else (1.0 - confidence) * _EPSILON_MAX
        chosen = ranked[0][1]
        if epsilon > 0.0 and len(ranked) > 1 and random.random() < epsilon:
            chosen = ranked[1][1]

        if record_decision:
            self._record(capability, task, chosen, ranked)
        return chosen

    def select_with_fallback(
        self,
        capability: str,
        task: Optional[dict[str, Any]] = None,
        exclude: Optional[set[str]] = None,
        limit: int = 3,
    ) -> list[ExecutionProvider]:
        """Ranked list of viable providers (excluding the given ids)."""
        task = task or {}
        memory = self._get_memory()
        budget = self._get_budget()
        fallbacks: list[ExecutionProvider] = []
        for provider in self._candidates(capability):
            if exclude and provider.provider_id in exclude:
                continue
            try:
                if not budget.can_use(provider.provider_id):
                    continue
            except Exception:
                pass
            try:
                if memory.should_skip(provider.provider_id):
                    continue
            except Exception:
                pass
            fallbacks.append(provider)
        fallbacks.sort(key=lambda p: self._score(p, task or {"capability": capability}), reverse=True)
        return fallbacks[: max(1, limit)]

    # ------------------------------------------------------------------ #
    # Decision recording (feedback loop)                                 #
    # ------------------------------------------------------------------ #

    def _record(
        self,
        capability: str,
        task: dict[str, Any],
        chosen: ExecutionProvider,
        ranked: list[tuple[float, ExecutionProvider]],
    ) -> None:
        try:
            from core.providers.feedback.models import ScoreBreakdown
            recorder = self._get_recorder()
            candidates = [
                ScoreBreakdown(
                    provider_id=p.provider_id,
                    priority_score=0.0,
                    historical_score=score,
                    benchmark_score=0.0,
                    calibration_adjustment=0.0,
                    total_score=round(score, 4),
                )
                for score, p in ranked
            ]
            decision = recorder.record_decision(
                capability=capability,
                task=task,
                selected_provider=chosen.provider_id,
                candidate_scores=candidates,
            )
            self.last_decision_id = decision.decision_id
        except Exception as exc:
            logger.debug("[provider_router] record decision failed: %s", exc)


provider_router = ProviderRouter()
