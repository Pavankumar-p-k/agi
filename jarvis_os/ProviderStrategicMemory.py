from __future__ import annotations

import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ProviderMemoryRecord:
    timestamp: str
    task_type: str
    provider: str
    success: bool
    regret_score: float
    trust_drift: float
    latency_ms: int
    hallucination_incidents: int
    user_satisfaction: float
    correction_cost: float
    strategic_value: float
    governance_override: bool
    privacy_sensitive: bool


class ProviderStrategicMemory:
    def __init__(self, config: Any) -> None:
        self.data_file = Path(config.data_dir) / "provider_strategic_memory.json"
        self.records: list[ProviderMemoryRecord] = []
        self._load()

    def _load(self) -> None:
        if self.data_file.exists():
            try:
                payload = json.loads(self.data_file.read_text(encoding="utf-8"))
                self.records = [ProviderMemoryRecord(**record) for record in payload if isinstance(record, dict)]
            except Exception as exc:
                logger.warning("Failed to load provider strategic memory: %s", exc)
                self.records = []

    def _save(self) -> None:
        try:
            self.data_file.parent.mkdir(parents=True, exist_ok=True)
            self.data_file.write_text(json.dumps([asdict(record) for record in self.records], indent=2), encoding="utf-8")
        except Exception as exc:
            logger.warning("Failed to persist provider strategic memory: %s", exc)

    def record(self, *, task_type: str, provider: str, success: bool, regret_score: float, trust_drift: float, latency_ms: int, hallucination_incidents: int, user_satisfaction: float, correction_cost: float, strategic_value: float, governance_override: bool, privacy_sensitive: bool) -> None:
        record = ProviderMemoryRecord(
            timestamp=datetime.utcnow().isoformat(),
            task_type=task_type,
            provider=provider,
            success=success,
            regret_score=regret_score,
            trust_drift=trust_drift,
            latency_ms=latency_ms,
            hallucination_incidents=hallucination_incidents,
            user_satisfaction=user_satisfaction,
            correction_cost=correction_cost,
            strategic_value=strategic_value,
            governance_override=governance_override,
            privacy_sensitive=privacy_sensitive,
        )
        self.records.append(record)
        self._save()
        logger.debug("Recorded strategic memory event for %s: %s", provider, record)

    def provider_history(self, provider: str) -> list[ProviderMemoryRecord]:
        return [record for record in self.records if record.provider == provider]

    def task_history(self, task_type: str) -> list[ProviderMemoryRecord]:
        return [record for record in self.records if record.task_type == task_type]

    def aggregate_scores(self, provider: str) -> dict[str, float]:
        history = self.provider_history(provider)
        if not history:
            return {
                "success_rate": 0.0,
                "average_regret": 0.0,
                "average_trust_drift": 0.0,
                "average_latency_ms": 0.0,
                "average_strategic_value": 0.0,
            }
        return {
            "success_rate": sum(1 for record in history if record.success) / len(history),
            "average_regret": sum(record.regret_score for record in history) / len(history),
            "average_trust_drift": sum(record.trust_drift for record in history) / len(history),
            "average_latency_ms": sum(record.latency_ms for record in history) / len(history),
            "average_strategic_value": sum(record.strategic_value for record in history) / len(history),
        }

    def most_consistent_provider_for(self, task_type: str) -> str | None:
        history = self.task_history(task_type)
        if not history:
            return None
        summary: dict[str, dict[str, Any]] = {}
        for record in history:
            entry = summary.setdefault(record.provider, {"score": 0.0, "count": 0})
            entry["score"] += (1.0 if record.success else -1.0) - record.regret_score + record.strategic_value * 0.3
            entry["count"] += 1
        best = max(summary.items(), key=lambda item: item[1]["score"])
        return best[0]
