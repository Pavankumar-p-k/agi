from __future__ import annotations

import datetime
import logging
from typing import Any, Dict

from .models.base import ModelProvider

logger = logging.getLogger(__name__)


class ProviderHealthRegistry:
    def __init__(self, providers: dict[str, ModelProvider], max_error_count: int = 3) -> None:
        self.providers = providers
        self.max_error_count = max_error_count
        self.entries: dict[str, dict[str, Any]] = {
            name: {
                "ready": True,
                "last_checked": None,
                "error_count": 0,
                "last_error": "",
                "last_success": None,
                "trust_score": 1.0,
            }
            for name in providers
        }

    def update_status(self, name: str, status: dict[str, Any]) -> None:
        record = self.entries.get(name)
        if record is None:
            return
        record["last_checked"] = datetime.datetime.utcnow().isoformat()
        record["ready"] = bool(status.get("ready", False))
        record["last_error"] = status.get("error", "")
        if record["ready"]:
            record["error_count"] = 0
            record["last_success"] = record["last_checked"]
            record["trust_score"] = min(1.0, record["trust_score"] + 0.05)
        else:
            record["error_count"] += 1
            record["trust_score"] = max(0.0, record["trust_score"] - 0.15)
        record["trust_score"] = max(0.0, min(1.0, record["trust_score"]))
        logger.debug("Provider %s status updated: %s", name, record)

    def report_success(self, name: str, status: dict[str, Any]) -> None:
        self.update_status(name, {**status, "ready": True})

    def report_failure(self, name: str, error: str) -> None:
        record = self.entries.get(name)
        if record is None:
            return
        record["last_checked"] = datetime.datetime.utcnow().isoformat()
        record["ready"] = False
        record["last_error"] = error
        record["error_count"] += 1
        record["trust_score"] = max(0.0, record["trust_score"] - 0.2)
        logger.warning("Provider %s failure recorded: %s", name, error)

    def best_providers(self) -> list[str]:
        sorted_providers = sorted(
            self.entries.items(),
            key=lambda item: (
                not item[1]["ready"],
                item[1]["error_count"],
                -item[1]["trust_score"],
                item[1]["last_success"] is None,
                item[1]["last_success"] or "",
            ),
        )
        return [name for name, _ in sorted_providers]

    def best_provider(self) -> str:
        providers = self.best_providers()
        return providers[0] if providers else ""

    def summary(self) -> dict[str, Any]:
        return {
            name: dict(record)
            for name, record in self.entries.items()
        }

    def is_ready(self, name: str) -> bool:
        record = self.entries.get(name)
        return bool(record and record["ready"])

    def should_retry(self, name: str) -> bool:
        record = self.entries.get(name)
        if record is None:
            return False
        return record["error_count"] < self.max_error_count
