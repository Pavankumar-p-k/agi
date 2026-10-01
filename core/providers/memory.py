"""Provider evidence memory: who executed what, how well, and when.

Completed from the committed contracts in tests/unit/test_provider_ecosystem.py
and tests/unit/test_provider_fallback.py.

Two layers, one file (no parallel stores):
- Evidence per (provider, capability, task_type, model, language):
  ``EvidenceRecord`` with a bounded, time-decayed execution log — feeds
  routing scores, confidence, and distribution lookups.
- Legacy aggregate per provider: total/success-rate counters, per-capability
  and per-language usage, retries/repair/tokens/cost totals.

Fallback matching (B1 fix): records stored with empty fields must be found
by lookups with populated fields.  ``_FALLBACK_CHAIN`` is an ordered list of
keep/drop patterns (nonzero = keep, 0 = wildcard) applied to the LOOKUP key;
the first pattern whose match key exists in the evidence store wins.
"""
from __future__ import annotations

import json
import logging
import math
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from core.providers.feedback.models import ProviderResult

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Storage paths (module-level; tests override instance attributes)            #
# --------------------------------------------------------------------------- #

_MEMORY_DIR = Path(__file__).resolve().parent.parent.parent / "data"
_MEMORY_DIR.mkdir(parents=True, exist_ok=True)
_MEMORY_FILE = _MEMORY_DIR / "provider_memory.json"

# Bounded execution log per evidence record (oldest entries pruned)
MAX_EXECUTION_LOG = 200

# Minimum samples before a provider score is trusted (below → 0.5 prior)
MIN_SAMPLES_FOR_SCORE = 3

# Time-decay half-life for evidence entries (seconds) — 30 days
_DECAY_HALF_LIFE = 30 * 86400.0

# 90% one-sided normal deviate for the conservative score bound
_Z90 = 1.2816

# Provider-only default score prior
_PRIOR = 0.5


def evidence_key(
    provider_id: str,
    capability: str = "",
    task_type: str = "",
    model: str = "",
    language: str = "",
) -> tuple[str, str, str, str, str]:
    """5-tuple evidence key: (provider, capability, task_type, model, language)."""
    return (provider_id, capability, task_type, model, language)


# Ordered keep/drop patterns over (capability, task_type, model, language).
# Nonzero = keep that field, 0 = drop to wildcard.  Provider is never dropped,
# so matching never crosses providers.  (3,0,2,0) is the critical B1 pattern:
# record stored with empty task_type/language, lookup with populated fields.
_FALLBACK_CHAIN: list[tuple[int, int, int, int]] = [
    (1, 1, 1, 1),   # exact
    (3, 0, 2, 0),   # keep capability+model, wildcard task_type+language (B1)
    (1, 1, 1, 0),   # drop language
    (1, 1, 0, 1),   # drop model
    (1, 0, 1, 1),   # drop task_type
    (0, 1, 1, 1),   # drop capability
    (1, 0, 1, 0),   # keep capability+model
    (0, 1, 1, 0),
    (1, 0, 0, 1),
    (0, 0, 1, 1),
    (0, 1, 0, 1),
    (1, 0, 0, 0),   # capability only
    (0, 1, 0, 0),   # task_type only
    (0, 0, 1, 0),   # model only
    (0, 0, 0, 1),   # language only
    (0, 0, 0, 0),   # provider+capability only
]


def _match_keys(
    base: tuple[str, str, str, str, str],
    pattern: tuple[int, int, int, int],
) -> tuple[str, str, str, str, str]:
    """Apply a keep/drop pattern to positions 1..4 of a 5-tuple key.

    Pattern element 0 applies to the capability, 1 → task_type, 2 → model,
    3 → language.  Zero drops the field to "" (wildcard); nonzero keeps it.
    The provider (position 0) is never dropped.
    """
    return (
        base[0],
        base[1] if pattern[0] else "",
        base[2] if pattern[1] else "",
        base[3] if pattern[2] else "",
        base[4] if pattern[3] else "",
    )


def _decay_weight(ts: float, now: float) -> float:
    age = max(0.0, now - ts)
    return 0.5 ** (age / _DECAY_HALF_LIFE)


@dataclass
class EvidenceRecord:
    """Fine-grained evidence for one evidence key."""

    provider_id: str = ""
    capability: str = ""
    successes: int = 0
    failures: int = 0
    executions: int = 0
    _execution_log: list[dict[str, Any]] = field(default_factory=list)

    def record_outcome(self, success: bool, duration_ms: float = 0.0, cost: float = 0.0) -> None:
        self.executions += 1
        if success:
            self.successes += 1
        else:
            self.failures += 1
        self._execution_log.append({
            "ts": time.time(),
            "ok": bool(success),
            "dur": float(duration_ms),
            "cost": float(cost),
        })
        if len(self._execution_log) > MAX_EXECUTION_LOG:
            del self._execution_log[: len(self._execution_log) - MAX_EXECUTION_LOG]

    def _weighted_counts(self) -> tuple[float, float]:
        """Time-decayed (effective successes, effective failures)."""
        now = time.time()
        eff_s = 0.0
        eff_f = 0.0
        for entry in self._execution_log:
            weight = _decay_weight(float(entry.get("ts", 0.0)), now)
            if entry.get("ok"):
                eff_s += weight
            else:
                eff_f += weight
        return eff_s, eff_f

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "capability": self.capability,
            "successes": self.successes,
            "failures": self.failures,
            "executions": self.executions,
            "log": list(self._execution_log),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EvidenceRecord":
        rec = cls(
            provider_id=data.get("provider_id", ""),
            capability=data.get("capability", ""),
            successes=int(data.get("successes", 0)),
            failures=int(data.get("failures", 0)),
            executions=int(data.get("executions", 0)),
        )
        rec._execution_log = list(data.get("log", []))
        return rec


@dataclass
class EvidenceDistribution:
    """Aggregate view of matching evidence for one lookup."""

    executions: int = 0
    successes: int = 0
    failures: int = 0
    matched_key: tuple[str, str, str, str, str] = ("", "", "", "", "")


@dataclass
class ProviderAggregate:
    """Legacy per-provider aggregate counters."""

    provider_id: str = ""
    total_executions: int = 0
    successful_executions: int = 0
    consecutive_failures: int = 0
    total_retries: int = 0
    total_repair_count: int = 0
    total_tokens_used: int = 0
    total_cost: float = 0.0
    total_duration_ms: float = 0.0
    capabilities_used: dict[str, int] = field(default_factory=dict)
    languages: dict[str, int] = field(default_factory=dict)

    @property
    def success_rate(self) -> float:
        if self.total_executions == 0:
            return 0.0
        return round(self.successful_executions / self.total_executions, 4)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "total_executions": self.total_executions,
            "successful_executions": self.successful_executions,
            "success_rate": self.success_rate,
            "consecutive_failures": self.consecutive_failures,
            "total_retries": self.total_retries,
            "total_repair_count": self.total_repair_count,
            "total_tokens_used": self.total_tokens_used,
            "total_cost": self.total_cost,
            "capabilities_used": dict(self.capabilities_used),
            "languages": dict(self.languages),
        }


class ProviderMemory:
    """Evidence + aggregate memory for providers.  Never raises on record."""

    def __init__(self) -> None:
        self._MEMORY_DIR = _MEMORY_DIR
        self._MEMORY_FILE = _MEMORY_FILE
        self._records: dict[tuple[str, str, str, str, str], EvidenceRecord] = {}
        self._legacy_records: dict[str, ProviderAggregate] = {}
        self._load()

    # ------------------------------------------------------------------ #
    # Recording                                                          #
    # ------------------------------------------------------------------ #

    def record_execution(
        self,
        provider_id: str,
        success: bool,
        duration_ms: float = 0.0,
        capability: str = "",
        language: str = "",
        task_type: str = "",
        model: str = "",
        retries: int = 0,
        repair_count: int = 0,
        tokens_used: int = 0,
        cost: float = 0.0,
        workflow_id: str = "",
    ) -> None:
        """Record one execution: evidence log + legacy aggregate."""
        try:
            self.record(ProviderResult(
                provider_id=provider_id,
                capability=capability,
                success=success,
                duration_ms=duration_ms,
                metrics={
                    "task_type": task_type,
                    "model": model,
                    "language": language,
                    "retries": retries,
                    "repair_count": repair_count,
                    "tokens_used": tokens_used,
                    "cost": cost,
                    "workflow_id": workflow_id,
                },
            ))
        except Exception as exc:
            logger.debug("[provider_memory] record_execution failed: %s", exc)

    def record(self, result: "ProviderResult") -> None:
        """Record a ProviderResult into evidence + aggregates."""
        provider_id = result.provider_id
        capability = result.capability or ""
        metrics = result.metrics or {}

        key = evidence_key(
            provider_id,
            capability,
            str(metrics.get("task_type", "") or ""),
            str(metrics.get("model", "") or ""),
            str(metrics.get("language", "") or ""),
        )
        rec = self._records.get(key)
        if rec is None:
            rec = EvidenceRecord(provider_id=provider_id, capability=capability)
            self._records[key] = rec
        rec.record_outcome(
            result.success,
            duration_ms=float(result.duration_ms or 0.0),
            cost=float(metrics.get("cost", 0.0) or 0.0),
        )

        agg = self._legacy_records.setdefault(provider_id, ProviderAggregate(provider_id=provider_id))
        agg.total_executions += 1
        if result.success:
            agg.successful_executions += 1
            agg.consecutive_failures = 0
        else:
            agg.consecutive_failures += 1
        agg.total_duration_ms += float(result.duration_ms or 0.0)
        agg.total_retries += int(metrics.get("retries", 0) or 0)
        agg.total_repair_count += int(metrics.get("repair_count", 0) or 0)
        agg.total_tokens_used += int(metrics.get("tokens_used", 0) or 0)
        agg.total_cost += float(metrics.get("cost", 0.0) or 0.0)
        if capability:
            agg.capabilities_used[capability] = agg.capabilities_used.get(capability, 0) + 1
        language = str(metrics.get("language", "") or "")
        if language:
            agg.languages[language] = agg.languages.get(language, 0) + 1

    # ------------------------------------------------------------------ #
    # Legacy aggregate accessors                                         #
    # ------------------------------------------------------------------ #

    def get_record(self, provider_id: str) -> ProviderAggregate:
        return self._legacy_records.get(provider_id, ProviderAggregate(provider_id=provider_id))

    def get_score(self, provider_id: str) -> float:
        """Trusted success score; 0.5 prior below MIN_SAMPLES_FOR_SCORE."""
        agg = self._legacy_records.get(provider_id)
        if agg is None or agg.total_executions < MIN_SAMPLES_FOR_SCORE:
            return _PRIOR
        return agg.success_rate

    def get_all_scores(self) -> dict[str, float]:
        return {pid: self.get_score(pid) for pid in self._legacy_records}

    def should_skip(self, provider_id: str) -> bool:
        agg = self._legacy_records.get(provider_id)
        if agg is None:
            return False
        if agg.consecutive_failures >= 3:
            return True
        if agg.total_executions >= 5 and agg.success_rate < 0.2:
            return True
        return False

    def get_success_rate(self, provider_id: str) -> float:
        agg = self._legacy_records.get(provider_id)
        return agg.success_rate if agg else 0.0

    def get_avg_duration(self, provider_id: str) -> float:
        agg = self._legacy_records.get(provider_id)
        if agg is None or agg.total_executions == 0:
            return 0.0
        return round(agg.total_duration_ms / agg.total_executions, 3)

    def get_avg_cost(self, provider_id: str) -> float:
        agg = self._legacy_records.get(provider_id)
        if agg is None or agg.total_executions == 0:
            return 0.0
        return round(agg.total_cost / agg.total_executions, 6)

    def get_confidence(
        self,
        provider_id: str,
        capability: str = "",
        task_type: str = "",
        model: str = "",
    ) -> float:
        """Evidence-scaled confidence: n/(n+1).

        Without a capability filter: confidence over ALL evidence of the
        provider.  With a capability (and optional task_type/model): confidence
        of the fallback-matched evidence record for that context.
        """
        if not capability:
            n = 0
            for key, rec in self._records.items():
                if key[0] == provider_id:
                    n += rec.executions
        else:
            dist = self.get_distribution(provider_id, capability, task_type, model)
            n = dist.executions if dist is not None else 0
        if n == 0:
            return 0.0
        return round(n / (n + 1), 4)

    # ------------------------------------------------------------------ #
    # Distribution + score lookups (fallback chain)                      #
    # ------------------------------------------------------------------ #

    def get_distribution(
        self,
        provider_id: str,
        capability: str,
        task_type: str = "",
        model: str = "",
        language: str = "",
    ) -> Optional[EvidenceDistribution]:
        """Find matching evidence, walking the fallback chain lookup→stored."""
        lookup = evidence_key(provider_id, capability, task_type, model, language)
        for pattern in _FALLBACK_CHAIN:
            match_key = _match_keys(lookup, pattern)
            rec = self._records.get(match_key)
            if rec is not None and rec.executions > 0:
                return EvidenceDistribution(
                    executions=rec.executions,
                    successes=rec.successes,
                    failures=rec.failures,
                    matched_key=match_key,
                )
        return None

    def get_performance_score(self, provider_id: str, task: dict[str, Any]) -> float:
        """Conservative 90% lower-bound success estimate for a prospective task.

        Returns the 0.5 prior when no evidence matches.
        """
        lookup = evidence_key(
            provider_id,
            str(task.get("capability", "") or ""),
            str(task.get("task_type", "") or ""),
            str(task.get("model", "") or ""),
            str(task.get("language", "") or ""),
        )
        for pattern in _FALLBACK_CHAIN:
            match_key = _match_keys(lookup, pattern)
            rec = self._records.get(match_key)
            if rec is None or rec.executions == 0:
                continue
            eff_s, eff_f = rec._weighted_counts()
            n = eff_s + eff_f
            if n <= 0:
                continue
            p_hat = eff_s / n
            # Wilson lower bound (90%): conservative estimate of true success
            denom = 1.0 + (_Z90 ** 2) / n
            centre = p_hat + (_Z90 ** 2) / (2.0 * n)
            margin = _Z90 * math.sqrt((p_hat * (1.0 - p_hat)) / n + (_Z90 ** 2) / (4.0 * n * n))
            return round(max(0.0, (centre - margin) / denom), 4)
        return _PRIOR

    # ------------------------------------------------------------------ #
    # Persistence                                                        #
    # ------------------------------------------------------------------ #

    def _save(self) -> bool:
        try:
            payload = {
                "records": {json.dumps(k): rec.to_dict() for k, rec in self._records.items()},
                "legacy": {pid: agg.to_dict() for pid, agg in self._legacy_records.items()},
                "saved_at": time.time(),
            }
            self._MEMORY_FILE.write_text(json.dumps(payload), encoding="utf-8")
            return True
        except Exception as exc:
            logger.debug("[provider_memory] save failed: %s", exc)
            return False

    def _load(self) -> bool:
        try:
            if not self._MEMORY_FILE.exists():
                return False
            payload = json.loads(self._MEMORY_FILE.read_text(encoding="utf-8"))
            for key_json, rec_data in payload.get("records", {}).items():
                key = tuple(json.loads(key_json))
                self._records[key] = EvidenceRecord.from_dict(rec_data)
            for pid, agg_data in payload.get("legacy", {}).items():
                agg = ProviderAggregate(
                    provider_id=agg_data.get("provider_id", pid),
                    total_executions=agg_data.get("total_executions", 0),
                    successful_executions=agg_data.get("successful_executions", 0),
                    consecutive_failures=agg_data.get("consecutive_failures", 0),
                    total_retries=agg_data.get("total_retries", 0),
                    total_repair_count=agg_data.get("total_repair_count", 0),
                    total_tokens_used=agg_data.get("total_tokens_used", 0),
                    total_cost=agg_data.get("total_cost", 0.0),
                    total_duration_ms=agg_data.get("total_duration_ms", 0.0),
                    capabilities_used=agg_data.get("capabilities_used", {}),
                    languages=agg_data.get("languages", {}),
                )
                self._legacy_records[pid] = agg
            return True
        except Exception as exc:
            logger.debug("[provider_memory] load failed: %s", exc)
            return False


provider_memory = ProviderMemory()
