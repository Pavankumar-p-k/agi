from __future__ import annotations

import json
import logging
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_MEMORY_DIR = Path.home() / ".jarvis" / "provider_memory"
_MEMORY_FILE = _MEMORY_DIR / "memory.json"

# ── Beta-Binomial prior ───────────────────────────────────────────────────────
BETA_PRIOR_ALPHA: float = 1.0
BETA_PRIOR_BETA: float = 1.0
"""Uniform Beta(1, 1) prior.  Posterior = Beta(1+s, 1+f) after s successes,
f failures.  Posterior mean = (1+s)/(2+n).  Conservative lower-bound uses
the approximate 10th percentile of the posterior.
"""

# ── Failure reason constants ──────────────────────────────────────────────────
FAILURE_TIMEOUT = "timeout"
FAILURE_TOOL_ERROR = "tool_error"
FAILURE_VALIDATION = "validation_failed"
FAILURE_UNAVAILABLE = "provider_unavailable"
FAILURE_BUDGET = "budget_exceeded"
FAILURE_AUTH = "authentication"
FAILURE_RATE_LIMIT = "rate_limited"
FAILURE_UNKNOWN = "unknown"


# ==============================================================================
# Evidence models
# ==============================================================================


@dataclass
class EvidenceRecord:
    """Per-(provider, capability, task_type, model, language) statistics.

    This is the unit of evidence for the router.  Each record tracks
    outcome distributions (success, latency, cost), failure-mode
    histograms, and last-updated timestamps for time-decay weighting.
    """

    provider_id: str = ""
    capability: str = ""
    task_type: str = ""
    model: str = ""
    language: str = ""

    # ── Outcome counters ──────────────────────────────────────────────────────
    executions: int = 0
    successes: int = 0
    failures: int = 0
    cancellations: int = 0

    # ── Latency moments (for mean + variance) ─────────────────────────────────
    total_duration_ms: float = 0.0
    duration_squared_ms: float = 0.0

    # ── Cost ──────────────────────────────────────────────────────────────────
    total_cost: float = 0.0

    # ── Retries ───────────────────────────────────────────────────────────────
    retries: int = 0

    # ── Failure-reason histogram ──────────────────────────────────────────────
    failure_reasons: dict[str, int] = field(default_factory=dict)

    # ── Maintenance ───────────────────────────────────────────────────────────
    last_updated: float = 0.0

    # ── Bayesian-derived (cached after each mutation) ─────────────────────────
    _posterior_alpha: float = BETA_PRIOR_ALPHA
    _posterior_beta: float = BETA_PRIOR_BETA

    # ── Computed properties ───────────────────────────────────────────────────

    @property
    def posterior_mean(self) -> float:
        """Beta posterior expected success rate."""
        return self._posterior_alpha / (self._posterior_alpha + self._posterior_beta)

    @property
    def posterior_std(self) -> float:
        """Standard deviation of the Beta posterior."""
        a = self._posterior_alpha
        b = self._posterior_beta
        return math.sqrt(a * b / ((a + b) ** 2 * (a + b + 1)))

    @property
    def avg_duration_ms(self) -> float:
        if self.executions == 0:
            return 0.0
        return self.total_duration_ms / self.executions

    @property
    def duration_variance_ms(self) -> float:
        if self.executions < 2:
            return 0.0
        mean = self.avg_duration_ms
        return self.duration_squared_ms / self.executions - mean * mean

    @property
    def avg_cost(self) -> float:
        if self.executions == 0:
            return 0.0
        return self.total_cost / self.executions

    @property
    def retry_rate(self) -> float:
        if self.executions == 0:
            return 0.0
        return self.retries / self.executions

    @property
    def effective_sample_size(self) -> float:
        """Kish's effective sample size accounting for time decay.

        Falls back to raw count when no timestamps are available.
        """
        return float(self.executions)

    @property
    def confidence(self) -> float:
        """Maps evidence count to 0-1 confidence scale.

        A single observation → ~0.5,  100 observations → ~0.91.
        """
        n = self.effective_sample_size
        return math.sqrt(n) / (1.0 + math.sqrt(n)) if n > 0 else 0.0

    def performance_lower_bound(self, percentile: float = 0.10) -> float:
        """Conservative lower-bound estimate of true success rate.

        Uses normal approximation to the Beta posterior:
            lower ≈ mean - z * std
        where z = 1.28 for 10th percentile, 1.645 for 5th.
        """
        z = {0.05: 1.645, 0.10: 1.282}.get(percentile, 1.282)
        lower = self.posterior_mean - z * self.posterior_std
        return max(0.0, lower)

    # ── Mutators ──────────────────────────────────────────────────────────────

    def record_outcome(
        self,
        success: bool,
        duration_ms: float = 0.0,
        cost: float = 0.0,
        retries: int = 0,
        cancelled: bool = False,
        failure_reason: str = "",
    ) -> None:
        self.executions += 1
        self.total_duration_ms += duration_ms
        self.duration_squared_ms += duration_ms * duration_ms
        self.total_cost += cost
        self.retries += retries
        self.last_updated = time.time()

        if cancelled:
            self.cancellations += 1
        elif success:
            self.successes += 1
        else:
            self.failures += 1
            if failure_reason:
                self.failure_reasons[failure_reason] = self.failure_reasons.get(failure_reason, 0) + 1

        self._recompute_posterior()

    def _recompute_posterior(self) -> None:
        self._posterior_alpha = BETA_PRIOR_ALPHA + self.successes
        self._posterior_beta = BETA_PRIOR_BETA + self.failures


# ==============================================================================
# Evidence key generation & fallback chain
# ==============================================================================


def evidence_key(
    provider_id: str,
    capability: str = "",
    task_type: str = "",
    model: str = "",
    language: str = "",
) -> tuple[str, str, str, str, str]:
    """Canonical key for EvidenceRecord lookup."""
    return (provider_id, capability or "", task_type or "", model or "", language or "")


_FALLBACK_CHAIN: list[tuple[int, int, int, int]] = [
    (3, 2, 2, 1),  # exact match
    (3, 2, 0, 1),  # drop model
    (3, 0, 0, 1),  # drop model + task_type
    (3, 0, 0, 0),  # capability only
    (0, 0, 0, 0),  # provider-wide aggregate
]
"""Fallback chain for evidence lookup.

Each entry is (include_capability, include_task_type, include_model, include_language)
where >0 = include, 0 = wildcard to "".
"""


def _match_keys(
    base: tuple[str, str, str, str, str],
    template: tuple[int, int, int, int],
) -> tuple[str, str, str, str, str]:
    """Build a lookup key from *base* masked by *template*.

    Components where template[i] > 0 keep the base value; others are "".
    """
    return (
        base[0],
        base[1] if template[0] > 0 else "",
        base[2] if template[1] > 0 else "",
        base[3] if template[2] > 0 else "",
        base[4] if template[3] > 0 else "",
    )


# ==============================================================================
# ProviderMemory — evidence service
# ==============================================================================


class ProviderMemory:
    """Evidence store for provider execution history.

    Maintains two collections:
      * ``self._records`` — **keyed by (pid, cap, task_type, model, lang)**

      * ``self._legacy_records`` — flat ``{pid: ProviderPerformanceRecord}``

    The legacy flat records are kept for backward-compatible API calls
    (``record_execution``, ``get_score``, ``should_skip``).  New code
    should use ``record(ProviderResult)`` and ``get_performance_score(...)``.
    """

    def __init__(self):
        self._records: dict[tuple[str, str, str, str, str], EvidenceRecord] = {}
        self._legacy_records: dict[str, ProviderPerformanceRecord] = {}
        self._load()

    # ── Primary recording API ─────────────────────────────────────────────────

    def record(self, result: Any) -> None:
        """Record a ProviderResult (or compatible object).

        This is the single entry point for pipeline execution feedback.
        """
        from core.providers.feedback.models import ProviderResult

        if not hasattr(result, "provider_id"):
            result = ProviderResult.from_execution_result(result)
        if not result.provider_id:
            return

        task_type = result.metrics.get("task_type", "") if hasattr(result, "metrics") else ""
        model = result.metrics.get("model", "") if hasattr(result, "metrics") else ""
        language = result.metrics.get("language", "") if hasattr(result, "metrics") else ""

        failure_reason = ""
        if not result.success and hasattr(result, "error") and result.error:
            error_lower = result.error.lower()
            if any(kw in error_lower for kw in ("timeout", "timed out")):
                failure_reason = FAILURE_TIMEOUT
            elif any(kw in error_lower for kw in ("auth", "permission", "unauthorized")):
                failure_reason = FAILURE_AUTH
            elif any(kw in error_lower for kw in ("rate limit", "too many")):
                failure_reason = FAILURE_RATE_LIMIT
            elif any(kw in error_lower for kw in ("unavailable", "connection refused", "offline")):
                failure_reason = FAILURE_UNAVAILABLE
            elif any(kw in error_lower for kw in ("budget", "limit exceeded")):
                failure_reason = FAILURE_BUDGET
            elif any(kw in error_lower for kw in ("validation", "invalid")):
                failure_reason = FAILURE_VALIDATION
            elif any(kw in error_lower for kw in ("tool", "execution")):
                failure_reason = FAILURE_TOOL_ERROR
            else:
                failure_reason = FAILURE_UNKNOWN

        key = evidence_key(
            result.provider_id,
            getattr(result, "capability", ""),
            task_type,
            model,
            language,
        )

        record = self._records.setdefault(
            key,
            EvidenceRecord(
                provider_id=result.provider_id,
                capability=getattr(result, "capability", ""),
                task_type=task_type,
                model=model,
                language=language,
            ),
        )
        record.record_outcome(
            success=result.success,
            duration_ms=getattr(result, "duration_ms", 0.0),
            cost=getattr(result, "cost", 0.0),
            retries=0,
            cancelled=False,
            failure_reason=failure_reason,
        )

        self._save()

    def record_execution(
        self,
        provider_id: str,
        success: bool,
        duration_ms: float = 0.0,
        retries: int = 0,
        repair_count: int = 0,
        tokens_used: int = 0,
        cost: float = 0.0,
        capability: str = "",
        language: str = "",
        framework: str = "",
    ) -> None:
        """Backward-compatible legacy recording API.

        Records into both the evidence store and the flat legacy store.
        """
        # Evidence store entry (aggregated, no task_type/model)
        key = evidence_key(provider_id, capability)
        rec = self._records.setdefault(key, EvidenceRecord(provider_id=provider_id, capability=capability))
        rec.record_outcome(success=success, duration_ms=duration_ms, cost=cost, retries=retries)

        # Legacy flat record
        legacy = self._legacy_records.setdefault(provider_id, ProviderPerformanceRecord(provider_id=provider_id))
        legacy.total_executions += 1
        legacy.total_duration_ms += duration_ms
        legacy.total_retries += retries
        legacy.total_repair_count += repair_count
        legacy.total_tokens_used += tokens_used
        legacy.total_cost += cost
        legacy.last_execution = time.time()
        if success:
            legacy.successful_executions += 1
            legacy.consecutive_failures = 0
        else:
            legacy.failed_executions += 1
            legacy.consecutive_failures += 1
        if capability:
            legacy.capabilities_used[capability] = legacy.capabilities_used.get(capability, 0) + 1
        if language:
            legacy.languages[language] = legacy.languages.get(language, 0) + 1
        if framework:
            legacy.frameworks[framework] = legacy.frameworks.get(framework, 0) + 1

        self._save()

    # ── Evidence query API ────────────────────────────────────────────────────

    def get_record(self, provider_id: str) -> Any | None:
        """Backward-compatible: return the legacy ProviderPerformanceRecord."""
        return self._legacy_records.get(provider_id)

    def get_success_rate(self, provider_id: str) -> float:
        """Backward-compatible: raw success rate from legacy store."""
        legacy = self._legacy_records.get(provider_id)
        return legacy.success_rate if legacy else 0.0

    def get_avg_duration(self, provider_id: str) -> float:
        """Backward-compatible: average duration from legacy store."""
        legacy = self._legacy_records.get(provider_id)
        return legacy.avg_duration_ms if legacy else 0.0

    def get_avg_cost(self, provider_id: str) -> float:
        """Backward-compatible: average cost from legacy store."""
        legacy = self._legacy_records.get(provider_id)
        return legacy.avg_cost if legacy else 0.0

    def get_score(self, provider_id: str) -> float:
        """Backward-compatible score (raw success rate, legacy store)."""
        legacy = self._legacy_records.get(provider_id)
        if not legacy or legacy.total_executions < 3:
            return 0.5
        return legacy.success_rate

    def get_all_scores(self) -> dict[str, float]:
        """Backward-compatible: all provider-level Bayesian scores."""
        scores: dict[str, float] = {}
        for (pid, cap, tt, m, lang), rec in self._records.items():
            if cap == "" and tt == "" and m == "" and lang == "":
                if rec.executions >= 3:
                    scores[pid] = rec.posterior_mean
        for pid in self._legacy_records:
            if pid not in scores:
                scores[pid] = self.get_score(pid)
        return scores

    def should_skip(self, provider_id: str) -> bool:
        """Backward-compatible: skip on consecutive failures or low rate."""
        legacy = self._legacy_records.get(provider_id)
        if not legacy:
            return False
        if legacy.consecutive_failures >= 3:
            return True
        if legacy.total_executions >= 5 and legacy.success_rate < 0.3:
            return True
        return False

    # ── New query API ─────────────────────────────────────────────────────────

    def get_distribution(
        self,
        provider_id: str,
        capability: str = "",
        task_type: str = "",
        model: str = "",
        language: str = "",
    ) -> EvidenceRecord | None:
        """Return the raw EvidenceRecord for the best matching key.

        Uses a fallback chain from most-specific to least-specific key.
        Returns None only when no record exists for any fallback level.
        """
        base = evidence_key(provider_id, capability, task_type, model, language)
        for mask in _FALLBACK_CHAIN:
            key = _match_keys(base, mask)
            rec = self._records.get(key)
            if rec is not None and rec.executions > 0:
                return rec
        return None

    def get_expected_score(
        self,
        provider_id: str,
        capability: str = "",
        task_type: str = "",
        model: str = "",
        language: str = "",
    ) -> float:
        """Beta posterior mean success rate for the best matching evidence.

        Returns 0.5 (the uniform prior mean) when no evidence exists.
        """
        rec = self.get_distribution(provider_id, capability, task_type, model, language)
        if rec is None:
            return 0.5
        return rec.posterior_mean

    def get_confidence(
        self,
        provider_id: str,
        capability: str = "",
        task_type: str = "",
        model: str = "",
        language: str = "",
    ) -> float:
        """Confidence in the expected score, 0-1 scale."""
        rec = self.get_distribution(provider_id, capability, task_type, model, language)
        if rec is None:
            return 0.0
        return rec.confidence

    def get_performance_score(
        self,
        provider_id: str,
        task: dict[str, Any] | None = None,
    ) -> float:
        """Conservative evidence score for the ProviderRouter.

        Returns the 10th percentile lower bound of the Beta posterior
        for the best matching evidence context derived from *task*.
        This avoids favouring low-sample providers.
        """
        cap = (task or {}).get("capability", "")
        tt = (task or {}).get("task_type", "")
        model = (task or {}).get("model", "")
        lang = (task or {}).get("language", "")
        rec = self.get_distribution(provider_id, cap, tt, model, lang)
        if rec is None or rec.executions == 0:
            return 0.5
        return rec.performance_lower_bound(percentile=0.10)

    def get_top_providers(
        self,
        capability: str,
        task_type: str = "",
        model: str = "",
        language: str = "",
        limit: int = 5,
    ) -> list[tuple[str, EvidenceRecord]]:
        """Rank providers for a (capability, task_type) by lower-bound score."""
        scored: list[tuple[float, str, EvidenceRecord]] = []
        for (pid, cap, tt, m, lang), rec in self._records.items():
            if cap != capability:
                continue
            if not rec.executions:
                continue
            score = rec.performance_lower_bound()
            scored.append((-score, pid, rec))
        scored.sort()
        return [(pid, rec) for _, pid, rec in scored[:limit]]

    def get_failure_profile(
        self,
        provider_id: str,
        capability: str = "",
        task_type: str = "",
    ) -> dict[str, int]:
        """Return the failure-reason histogram for a provider+context."""
        rec = self.get_distribution(provider_id, capability, task_type)
        if rec is None:
            return {}
        return dict(rec.failure_reasons)

    # ── Persistence ──────────────────────────────────────────────────────────

    def _load(self) -> None:
        try:
            if _MEMORY_FILE.exists():
                data = json.loads(_MEMORY_FILE.read_text(encoding="utf-8"))
                for pid, rd in data.get("legacy", {}).items():
                    self._legacy_records[pid] = ProviderPerformanceRecord(**rd)
                for key_str, ev_data in data.get("evidence", {}).items():
                    import ast
                    try:
                        key = ast.literal_eval(key_str) if isinstance(key_str, str) else key_str
                    except Exception:
                        continue
                    rec = EvidenceRecord(**ev_data)
                    rec._recompute_posterior()
                    self._records[key] = rec
        except Exception as e:
            logger.warning("[ProviderMemory] Failed to load: %s", e)

    def _save(self) -> None:
        try:
            _MEMORY_DIR.mkdir(parents=True, exist_ok=True)
            data = {
                "legacy": {pid: vars(record) for pid, record in self._legacy_records.items()},
                "evidence": {str(k): {f: v for f, v in vars(rec).items() if not f.startswith("_")}
                             for k, rec in self._records.items()},
            }
            _MEMORY_FILE.write_text(
                json.dumps(data, indent=2, default=str, sort_keys=True),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning("[ProviderMemory] Failed to save: %s", e)


# ==============================================================================
# Legacy record (kept for backward-compatible public API)
# ==============================================================================


@dataclass
class ProviderPerformanceRecord:
    """Legacy flat success-rate record.

    Deprecated.  New code should use ``EvidenceRecord`` and the
    ``.record(ProviderResult)`` / ``.get_performance_score(...)`` API.
    """

    provider_id: str = ""
    total_executions: int = 0
    successful_executions: int = 0
    failed_executions: int = 0
    total_duration_ms: float = 0.0
    total_retries: int = 0
    total_repair_count: int = 0
    total_tokens_used: int = 0
    total_cost: float = 0.0
    capabilities_used: dict[str, int] = field(default_factory=dict)
    languages: dict[str, int] = field(default_factory=dict)
    frameworks: dict[str, int] = field(default_factory=dict)
    last_execution: float = 0.0
    consecutive_failures: int = 0

    @property
    def success_rate(self) -> float:
        if self.total_executions == 0:
            return 0.0
        return self.successful_executions / self.total_executions

    @property
    def avg_duration_ms(self) -> float:
        if self.total_executions == 0:
            return 0.0
        return self.total_duration_ms / self.total_executions

    @property
    def avg_cost(self) -> float:
        if self.total_executions == 0:
            return 0.0
        return self.total_cost / self.total_executions


provider_memory = ProviderMemory()
