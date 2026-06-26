from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_MEMORY_DIR = Path.home() / ".jarvis" / "provider_memory"
_MEMORY_FILE = _MEMORY_DIR / "memory.json"


@dataclass
class ProviderPerformanceRecord:
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


class ProviderMemory:
    def __init__(self):
        self._records: dict[str, ProviderPerformanceRecord] = {}
        self._load()

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
        record = self._records.setdefault(provider_id, ProviderPerformanceRecord(provider_id=provider_id))
        record.total_executions += 1
        record.total_duration_ms += duration_ms
        record.total_retries += retries
        record.total_repair_count += repair_count
        record.total_tokens_used += tokens_used
        record.total_cost += cost
        record.last_execution = time.time()

        if success:
            record.successful_executions += 1
            record.consecutive_failures = 0
        else:
            record.failed_executions += 1
            record.consecutive_failures += 1

        if capability:
            record.capabilities_used[capability] = record.capabilities_used.get(capability, 0) + 1
        if language:
            record.languages[language] = record.languages.get(language, 0) + 1
        if framework:
            record.frameworks[framework] = record.frameworks.get(framework, 0) + 1

        self._save()

    def get_record(self, provider_id: str) -> ProviderPerformanceRecord | None:
        return self._records.get(provider_id)

    def get_success_rate(self, provider_id: str) -> float:
        record = self._records.get(provider_id)
        return record.success_rate if record else 0.0

    def get_avg_duration(self, provider_id: str) -> float:
        record = self._records.get(provider_id)
        return record.avg_duration_ms if record else 0.0

    def get_avg_cost(self, provider_id: str) -> float:
        record = self._records.get(provider_id)
        return record.avg_cost if record else 0.0

    def get_score(self, provider_id: str) -> float:
        record = self._records.get(provider_id)
        if not record or record.total_executions < 3:
            return 0.5
        return record.success_rate

    def get_all_scores(self) -> dict[str, float]:
        return {pid: self.get_score(pid) for pid in self._records}

    def should_skip(self, provider_id: str) -> bool:
        record = self._records.get(provider_id)
        if not record:
            return False
        if record.consecutive_failures >= 3:
            return True
        if record.total_executions >= 5 and record.success_rate < 0.3:
            return True
        return False

    def _load(self) -> None:
        try:
            if _MEMORY_FILE.exists():
                data = json.loads(_MEMORY_FILE.read_text(encoding="utf-8"))
                for pid, record_data in data.items():
                    self._records[pid] = ProviderPerformanceRecord(**record_data)
        except Exception as e:
            logger.warning("[ProviderMemory] Failed to load: %s", e)

    def _save(self) -> None:
        try:
            _MEMORY_DIR.mkdir(parents=True, exist_ok=True)
            data = {pid: vars(record) for pid, record in self._records.items()}
            _MEMORY_FILE.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        except Exception as e:
            logger.warning("[ProviderMemory] Failed to save: %s", e)


provider_memory = ProviderMemory()
