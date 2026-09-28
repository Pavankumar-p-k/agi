"""ProviderMemory — execution evidence per provider (calibration input)."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class EvidenceRecord:
    provider_id: str
    total_executions: int = 0
    successful_executions: int = 0
    failed_executions: int = 0
    last_error: str = ""
    last_duration_ms: float = 0.0
    last_execution_ts: float = 0.0
    total_duration_ms: float = 0.0
    history: list = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        if self.total_executions == 0:
            return 0.0
        return self.successful_executions / self.total_executions

    def to_dict(self) -> dict:
        return {
            "provider_id": self.provider_id,
            "total_executions": self.total_executions,
            "successful_executions": self.successful_executions,
            "failed_executions": self.failed_executions,
            "success_rate": self.success_rate,
            "last_error": self.last_error,
            "last_duration_ms": self.last_duration_ms,
        }


class ProviderMemory:
    """Thread-safe store of per-provider execution evidence."""

    def __init__(self) -> None:
        self._records: dict[str, EvidenceRecord] = {}
        self._lock = threading.Lock()

    def get_record(self, provider_id: str) -> Optional[EvidenceRecord]:
        with self._lock:
            return self._records.get(provider_id)

    def record(self, provider_id: str, success: bool,
               duration_ms: float = 0.0, error: str = "") -> EvidenceRecord:
        with self._lock:
            rec = self._records.get(provider_id)
            if rec is None:
                rec = EvidenceRecord(provider_id=provider_id)
                self._records[provider_id] = rec
            rec.total_executions += 1
            if success:
                rec.successful_executions += 1
            else:
                rec.failed_executions += 1
                rec.last_error = error
            rec.last_duration_ms = duration_ms
            rec.total_duration_ms += duration_ms
            rec.last_execution_ts = time.time()
            rec.history.append({
                "ts": rec.last_execution_ts, "success": success,
                "duration_ms": duration_ms, "error": error,
            })
            if len(rec.history) > 200:
                del rec.history[:-200]
            return rec

    def all_records(self) -> list:
        with self._lock:
            return list(self._records.values())

    def clear(self) -> None:
        with self._lock:
            self._records.clear()


provider_memory = ProviderMemory()


__all__ = ["EvidenceRecord", "ProviderMemory", "provider_memory"]
