from __future__ import annotations

from typing import Any

from .runtime.exceptions import RuntimeBoundaryViolation


class ProviderExecutionEvaluator:
    """
    Evaluates provider readiness against task profile and returns actionable ranking.
    """

    def rank(self, candidate_statuses: dict[str, dict[str, Any]], task_profile: dict[str, Any]) -> list[dict[str, Any]]:
        if not candidate_statuses:
            raise RuntimeBoundaryViolation("Provider evaluation requires at least one candidate.")
        ranked: list[dict[str, Any]] = []
        for provider, status in candidate_statuses.items():
            readiness = 1.0 if status.get("ready", False) else 0.0
            privacy = 1.0 if task_profile.get("privacy_sensitive") and provider != "rest" else 0.8
            ranked.append({"provider": provider, "score": round(readiness * privacy, 4)})
        ranked.sort(key=lambda item: item["score"], reverse=True)
        return ranked
