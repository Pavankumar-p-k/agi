"""ProviderMemory — execution evidence per provider (calibration input).

Evidence is keyed by the 5-tuple ``(provider, capability, task_type,
model, language)``. Lookups walk a fallback chain of field-dropping
patterns (lookup → stored) so evidence recorded with empty task_type /
language still matches specific lookups.
"""
from __future__ import annotations

import math
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

# Configured persistence location (see ProviderMemory.persist()).
_MEMORY_FILE = Path(os.getenv(
    "JARVIS_PROVIDER_MEMORY",
    str(Path(__file__).resolve().parents[2] / "data" / "provider_memory.json")))

# Field-drop patterns applied to the LOOKUP key: each tuple maps to the
# (capability, task_type, model, language) slots; 0 drops the field.
# (3, 0, 2, 0) is the critical B1 pattern: keep capability + model, drop
# task_type + language.
_FALLBACK_CHAIN: Tuple[Tuple[int, int, int, int], ...] = (
    (1, 1, 1, 1),   # exact
    (1, 1, 1, 0),   # drop language
    (1, 1, 0, 1),   # drop model
    (3, 0, 2, 0),   # keep capability + model (B1)
    (1, 0, 1, 1),   # drop task_type
    (1, 1, 0, 0),   # capability + task_type only
    (1, 0, 1, 0),   # capability + model only
    (1, 0, 0, 1),   # capability + language only
    (1, 0, 0, 0),   # capability only
    (0, 0, 0, 0),   # provider only
)


def evidence_key(provider_id: str, capability: str = "", task_type: str = "",
                 model: str = "", language: str = "") -> Tuple[str, str, str, str, str]:
    """Canonical 5-tuple evidence key."""
    return (str(provider_id or ""), str(capability or ""), str(task_type or ""),
            str(model or ""), str(language or ""))


def _match_keys(base: Tuple[str, str, str, str, str],
                pattern: Tuple[int, int, int, int]) -> Tuple[str, str, str, str, str]:
    """Return *base* with fields dropped where *pattern* is zero."""
    out = [base[0]]
    for value, flag in zip(base[1:], pattern):
        out.append(value if flag else "")
    return tuple(out)  # type: ignore[return-value]


@dataclass
class EvidenceRecord:
    """Accumulated evidence for one (provider, capability, context) bucket."""

    provider_id: str = ""
    capability: str = ""
    task_type: str = ""
    model: str = ""
    language: str = ""
    executions: int = 0
    successes: int = 0
    failures: int = 0
    total_duration_ms: float = 0.0
    last_duration_ms: float = 0.0
    last_error: str = ""
    last_execution_ts: float = 0.0
    history: list = field(default_factory=list)

    # Historical names kept for backward compatibility.
    @property
    def total_executions(self) -> int:
        return self.executions

    @property
    def successful_executions(self) -> int:
        return self.successes

    @property
    def failed_executions(self) -> int:
        return self.failures

    @property
    def success_rate(self) -> float:
        if self.executions == 0:
            return 0.0
        return self.successes / self.executions

    @property
    def key(self) -> Tuple[str, str, str, str, str]:
        return evidence_key(self.provider_id, self.capability, self.task_type,
                            self.model, self.language)

    def to_dict(self) -> dict:
        return {
            "provider_id": self.provider_id,
            "capability": self.capability,
            "task_type": self.task_type,
            "model": self.model,
            "language": self.language,
            "executions": self.executions,
            "successes": self.successes,
            "failures": self.failures,
            "success_rate": self.success_rate,
            "last_error": self.last_error,
            "last_duration_ms": self.last_duration_ms,
            "total_duration_ms": self.total_duration_ms,
        }


# ── Beta helpers (no scipy dependency) ───────────────────────────────────
def _betacf(a: float, b: float, x: float) -> float:
    max_iter, eps, fpmin = 200, 3e-12, 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    if abs(d) < fpmin:
        d = fpmin
    d = 1.0 / d
    h = d
    for m in range(1, max_iter + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < fpmin:
            d = fpmin
        c = 1.0 + aa / c
        if abs(c) < fpmin:
            c = fpmin
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < fpmin:
            d = fpmin
        c = 1.0 + aa / c
        if abs(c) < fpmin:
            c = fpmin
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < eps:
            break
    return h


def _betainc(a: float, b: float, x: float) -> float:
    """Regularized incomplete beta function I_x(a, b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    front = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
                     + a * math.log(x) + b * math.log1p(-x))
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b


def _beta_ppf(p: float, a: float, b: float) -> float:
    """Beta distribution percentile via bisection on the regularized CDF."""
    lo, hi = 0.0, 1.0
    for _ in range(80):
        mid = (lo + hi) / 2.0
        if _betainc(a, b, mid) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


class ProviderMemory:
    """Thread-safe store of per-provider execution evidence."""

    def __init__(self) -> None:
        self._records: Dict[Tuple[str, str, str, str, str], EvidenceRecord] = {}
        self._lock = threading.Lock()

    # ── recording ────────────────────────────────────────────────────
    def _apply(self, key: Tuple[str, str, str, str, str], success: bool,
               duration_ms: float, error: str = "") -> EvidenceRecord:
        with self._lock:
            record = self._records.get(key)
            if record is None:
                record = EvidenceRecord(
                    provider_id=key[0], capability=key[1], task_type=key[2],
                    model=key[3], language=key[4])
                self._records[key] = record
            record.executions += 1
            if success:
                record.successes += 1
            else:
                record.failures += 1
                record.last_error = error
            record.last_duration_ms = float(duration_ms or 0.0)
            record.total_duration_ms += float(duration_ms or 0.0)
            record.last_execution_ts = time.time()
            record.history.append({
                "ts": record.last_execution_ts,
                "success": bool(success),
                "duration_ms": float(duration_ms or 0.0),
                "error": error,
            })
            if len(record.history) > 200:
                del record.history[:-200]
            return record

    def record(self, result: Any) -> EvidenceRecord:
        """Record a ProviderResult (pipeline feedback)."""
        metrics = dict(getattr(result, "metrics", None) or {})
        key = evidence_key(
            getattr(result, "provider_id", ""),
            getattr(result, "capability", ""),
            metrics.get("task_type", ""),
            metrics.get("model", ""),
            metrics.get("language", ""),
        )
        error = str(getattr(result, "error", "") or "")
        return self._apply(key, bool(getattr(result, "success", False)),
                           float(getattr(result, "duration_ms", 0.0) or 0.0), error)

    def record_execution(self, provider_id: str, success: bool,
                         duration_ms: float = 0.0, capability: str = "",
                         task_type: str = "", model: str = "",
                         language: str = "", error: str = "",
                         retries: int = 0, **kwargs: Any) -> EvidenceRecord:
        """Legacy/simple recording path used by benchmark + orchestrator."""
        key = evidence_key(provider_id, capability, task_type, model, language)
        return self._apply(key, success, duration_ms, error)

    # ── lookup ───────────────────────────────────────────────────────
    def _lookup(self, key: Tuple[str, str, str, str, str]) -> Optional[EvidenceRecord]:
        with self._lock:
            for pattern in _FALLBACK_CHAIN:
                candidate = _match_keys(key, pattern)
                record = self._records.get(candidate)
                if record is not None:
                    return record
        return None

    def get_distribution(self, provider_id: str, capability: str = "",
                         task_type: str = "", model: str = "",
                         language: str = "") -> Optional[EvidenceRecord]:
        return self._lookup(evidence_key(provider_id, capability, task_type,
                                         model, language))

    def get_record(self, provider_id: str) -> Optional[EvidenceRecord]:
        """Aggregate evidence for a provider across all of its buckets."""
        with self._lock:
            matches = [r for key, r in self._records.items()
                       if key[0] == str(provider_id)]
        if not matches:
            return None
        aggregate = EvidenceRecord(provider_id=str(provider_id))
        for record in matches:
            aggregate.executions += record.executions
            aggregate.successes += record.successes
            aggregate.failures += record.failures
            aggregate.total_duration_ms += record.total_duration_ms
            aggregate.last_duration_ms = max(aggregate.last_duration_ms,
                                             record.last_duration_ms)
            aggregate.last_execution_ts = max(aggregate.last_execution_ts,
                                              record.last_execution_ts)
            if record.last_error:
                aggregate.last_error = record.last_error
        return aggregate

    def get_confidence(self, provider_id: str, capability: str = "",
                       task_type: str = "", model: str = "",
                       language: str = "") -> float:
        record = self._lookup(evidence_key(provider_id, capability, task_type,
                                           model, language))
        if record is None or record.executions == 0:
            return 0.0
        return min(1.0, record.executions / 5.0)

    def get_performance_score(self, provider_id: str,
                              context: Optional[dict]) -> float:
        """Conservative 10th-percentile lower bound; 0.5 without evidence."""
        context = context or {}
        record = self._lookup(evidence_key(
            provider_id,
            context.get("capability", ""),
            context.get("task_type", ""),
            context.get("model", ""),
            context.get("language", ""),
        ))
        if record is None or record.executions == 0:
            return 0.5
        a = record.successes + 1.0
        b = record.failures + 1.0
        return float(_beta_ppf(0.10, a, b))

    # ── housekeeping ─────────────────────────────────────────────────
    def all_records(self) -> list:
        with self._lock:
            return list(self._records.values())

    def clear(self) -> None:
        with self._lock:
            self._records.clear()

    def persist(self) -> None:
        """Best-effort snapshot of the evidence store (never raises)."""
        try:
            import json

            _MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
            with self._lock:
                payload = {",".join(key): record.to_dict()
                           for key, record in self._records.items()}
            _MEMORY_FILE.write_text(json.dumps(payload, indent=1),
                                    encoding="utf-8")
        except Exception:  # noqa: BLE001 — persistence is best-effort
            pass


provider_memory = ProviderMemory()


__all__ = ["EvidenceRecord", "ProviderMemory", "provider_memory",
           "evidence_key", "_FALLBACK_CHAIN", "_match_keys", "_MEMORY_FILE"]
