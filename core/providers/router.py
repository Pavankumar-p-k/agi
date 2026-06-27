from __future__ import annotations

import asyncio
import inspect
import logging
from typing import Any

from core.providers.base import ExecutionProvider, ProviderHealthStatus
from core.providers.feedback.models import _extract_context
from core.providers.memory import ProviderMemory, provider_memory
from core.providers.budget import ProviderBudgetManager, provider_budget
from core.providers.registry import ProviderRegistry, provider_registry

logger = logging.getLogger(__name__)


def _run_async_or_default(fn, default: float = 0.0) -> float:
    """Call fn() and return result, handling both sync and async functions.

    If already in a running event loop, returns *default* immediately
    rather than creating an unawaited coroutine.
    """
    try:
        asyncio.get_running_loop()
        return default
    except RuntimeError:
        pass
    try:
        result = fn()
        if asyncio.iscoroutine(result):
            try:
                return asyncio.run(result)
            except RuntimeError:
                return default
        return float(result) if result is not None else default
    except Exception:
        return default

_DEFAULT_WEIGHTS: dict[str, float] = {
    "historical_success": 0.20,
    "benchmark_quality": 0.15,
    "health": 0.15,
    "latency": 0.15,
    "cost": 0.10,
    "budget": 0.10,
    "offline_availability": 0.05,
    "priority": 0.10,
}
"""Evidence-based scoring weights configurable via self-improvement system.

The priority weight provides a small tiebreaker for admin-configured provider
preferences when evidence is scarce.  All weights should sum to 1.0.
"""


class ProviderRouter:
    def __init__(
        self,
        registry: ProviderRegistry | None = None,
        memory: ProviderMemory | None = None,
        budget: ProviderBudgetManager | None = None,
        calibration_engine: Any = None,
        weights: dict[str, float] | None = None,
    ):
        self._registry = registry or provider_registry
        self._memory = memory or provider_memory
        self._budget = budget or provider_budget
        self._benchmark_store = None
        self._calibration_engine = calibration_engine
        self._decision_recorder = None
        self.last_decision_id: str | None = None
        self.weights: dict[str, float] = dict(weights or _DEFAULT_WEIGHTS)

    # -- Lazy helpers -----------------------------------------------------------

    def _get_benchmark_store(self):
        if self._benchmark_store is None:
            try:
                from core.providers.benchmark_store import BenchmarkStore
                self._benchmark_store = BenchmarkStore()
            except Exception as e:
                logger.debug("[ProviderRouter] Benchmark store unavailable: %s", e)
                self._benchmark_store = False
        return self._benchmark_store if self._benchmark_store else None

    def _get_calibration_engine(self):
        if self._calibration_engine is None:
            try:
                from core.providers.feedback.calibrator import CalibrationEngine
                self._calibration_engine = CalibrationEngine()
            except Exception as e:
                logger.debug("[ProviderRouter] Calibration engine unavailable: %s", e)
                self._calibration_engine = False
        return self._calibration_engine if self._calibration_engine else None

    def _get_decision_recorder(self):
        if self._decision_recorder is None:
            try:
                from core.providers.feedback.recorder import DecisionRecorder
                self._decision_recorder = DecisionRecorder()
            except Exception as e:
                logger.debug("[ProviderRouter] Decision recorder unavailable: %s", e)
                self._decision_recorder = False
        return self._decision_recorder if self._decision_recorder else None

    # -- Selection ---------------------------------------------------------------

    def select(
        self,
        capability: str,
        task: dict[str, Any] | None = None,
        workflow_id: str = "",
        prefer_offline: bool = False,
        record_decision: bool = False,
    ) -> ExecutionProvider | None:
        candidates = self._registry.get_providers_for_capability(capability)
        if not candidates:
            logger.warning("[ProviderRouter] No providers for capability: %s", capability)
            return None

        scored: list[tuple[float, ExecutionProvider]] = []
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

            try:
                asyncio.get_running_loop()
                health_result = provider._health_cache
            except RuntimeError:
                try:
                    health_result = asyncio.run(provider.cached_health())
                except RuntimeError:
                    health_result = provider._health_cache

            if health_result.status == ProviderHealthStatus.DOWN:
                logger.debug("[ProviderRouter] Skipping unhealthy provider: %s (%s)",
                             provider.provider_id, health_result.error)
                continue

            score = self._score(provider, task, prefer_offline=prefer_offline)
            scored.append((score, provider))

        if not scored:
            return None

        scored.sort(key=lambda x: x[0], reverse=True)
        best = scored[0][1]
        logger.info("[ProviderRouter] Selected %s (score=%.4f) for capability '%s'",
                     best.provider_id, scored[0][0], capability)

        # Record decision if requested
        if record_decision:
            recorder = self._get_decision_recorder()
            if recorder:
                breakdowns = []
                for s, p in scored:
                    breakdowns.append(self._score_with_breakdown(p, task, score=s))
                decision = recorder.record_decision(
                    capability=capability,
                    task=task or {},
                    selected_provider=best.provider_id,
                    candidate_scores=breakdowns,
                    provider_version=best.version,
                )
                self.last_decision_id = decision.decision_id

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

            try:
                asyncio.get_running_loop()
                health_result = provider._health_cache
            except RuntimeError:
                try:
                    health_result = asyncio.run(provider.cached_health())
                except RuntimeError:
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

    # -- Weighted scoring --------------------------------------------------------

    def _score(
        self,
        provider: ExecutionProvider,
        task: dict[str, Any] | None = None,
        prefer_offline: bool = False,
    ) -> float:
        pid = provider.provider_id
        w = self.weights

        dims = self._score_dimensions(provider, task, prefer_offline)
        dims["priority"] = self._registry.get_priority(pid) / 100.0

        raw = sum(w.get(k, 0.0) * v for k, v in dims.items())

        # Context-aware calibration adjustment (additive bonus)
        calibration = self._get_calibration_engine()
        adj = 0.0
        if calibration:
            cap = (task or {}).get("capability", "coding")
            ctx = _extract_context(task)
            adj = calibration.get_adjustment(
                pid, cap,
                language=ctx["language"],
                framework=ctx["framework"],
                project_size=ctx["project_size"],
            )
        return raw + adj

    def _score_dimensions(
        self,
        provider: ExecutionProvider,
        task: dict[str, Any] | None = None,
        prefer_offline: bool = False,
    ) -> dict[str, float]:
        """Return the 7 evidence dimensions as 0-1 values."""
        pid = provider.provider_id

        # 1. Historical success rate (Bayesian conservative lower-bound)
        historical = self._memory.get_performance_score(pid, task)

        # 2. Benchmark quality
        benchmark = self._benchmark_score(pid, task)

        # 3. Health
        health_result = provider._health_cache
        if health_result.status == ProviderHealthStatus.HEALTHY:
            health = 1.0
        elif health_result.status == ProviderHealthStatus.DEGRADED:
            health = 0.5
        else:
            health = 0.5  # UNKNOWN

        # 4. Latency score (lower = better, normalized to 0-1)
        latency_ms = _run_async_or_default(lambda: provider.estimate_latency(task or {}))
        latency = max(0.0, 1.0 - latency_ms / 10000.0)

        # 5. Cost score (lower = better, normalized to 0-1)
        cost_val = _run_async_or_default(lambda: provider.estimate_cost(task or {}))
        cost = max(0.0, 1.0 - cost_val / 10.0)
        cost = max(0.0, 1.0 - cost_val / 10.0)

        # 6. Budget remaining
        record = self._budget.get_record(pid)
        if record:
            daily_limit = getattr(self._budget, "_get_limit", lambda p, k, d: d)(pid, "daily", 10.0)
            if daily_limit > 0:
                budget = max(0.0, 1.0 - record.daily_cost / daily_limit)
            else:
                budget = 1.0
        else:
            budget = 1.0

        # 7. Offline availability
        if prefer_offline:
            offline = 1.0 if provider.available() else 0.0
        else:
            offline = 0.5

        return {
            "historical_success": historical,
            "benchmark_quality": benchmark,
            "health": health,
            "latency": latency,
            "cost": cost,
            "budget": budget,
            "offline_availability": offline,
        }

    def _score_with_breakdown(
        self,
        provider: ExecutionProvider,
        task: dict[str, Any] | None = None,
        score: float | None = None,
    ):
        """Return a ScoreBreakdown for a provider for recording purposes."""
        from core.providers.feedback.models import ScoreBreakdown

        pid = provider.provider_id
        w = self.weights
        dims = self._score_dimensions(provider, task)
        dims["priority"] = self._registry.get_priority(pid) / 100.0

        capability = (task or {}).get("capability", "coding")
        ctx = _extract_context(task)
        calibration = self._get_calibration_engine()
        calibration_adjustment = calibration.get_adjustment(
            pid, capability,
            language=ctx["language"],
            framework=ctx["framework"],
            project_size=ctx["project_size"],
        ) if calibration else 0.0

        total = score if score is not None else (sum(w.get(k, 0.0) * v for k, v in dims.items()) + calibration_adjustment)

        return ScoreBreakdown(
            provider_id=pid,
            priority_score=w.get("priority", 0.0) * dims["priority"],
            historical_score=w.get("historical_success", 0.0) * dims["historical_success"],
            benchmark_score=w.get("benchmark_quality", 0.0) * dims["benchmark_quality"],
            health_score=w.get("health", 0.0) * dims["health"],
            latency_score=w.get("latency", 0.0) * dims["latency"],
            cost_score=w.get("cost", 0.0) * dims["cost"],
            budget_score=w.get("budget", 0.0) * dims["budget"],
            offline_score=w.get("offline_availability", 0.0) * dims["offline_availability"],
            calibration_adjustment=calibration_adjustment,
            total_score=total,
        )

    # -- Benchmark helper -------------------------------------------------------

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
