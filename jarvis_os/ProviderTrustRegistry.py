from __future__ import annotations

import datetime
import logging
from typing import Any

logger = logging.getLogger(__name__)


class ProviderTrustRegistry:
    def __init__(self, providers: dict[str, Any] | None = None) -> None:
        self.providers = providers or {}
        self.entries: dict[str, dict[str, Any]] = {
            name: {
                "trust_score": 1.0,
                "hallucination_count": 0,
                "privacy_violations": 0,
                "policy_violations": 0,
                "strategic_missteps": 0,
                "total_requests": 0,
                "successful_requests": 0,
                "last_adjusted": None,
                "long_term_consistency": 1.0,
                "recent_outcomes": [],
            }
            for name in self.providers
        }

    def register_provider(self, name: str) -> None:
        if name not in self.entries:
            self.entries[name] = {
                "trust_score": 1.0,
                "hallucination_count": 0,
                "privacy_violations": 0,
                "policy_violations": 0,
                "strategic_missteps": 0,
                "total_requests": 0,
                "successful_requests": 0,
                "last_adjusted": None,
                "long_term_consistency": 1.0,
                "recent_outcomes": [],
            }

    def get_trust(self, name: str) -> float:
        entry = self.entries.get(name)
        if entry is None:
            return 0.5
        return float(entry["trust_score"])

    def record_outcome(self, provider: str, success: bool, hallucination: bool, privacy_ok: bool, strategic_fit: float, policy_compliant: bool, regret_penalty: float) -> None:
        entry = self.entries.get(provider)
        if entry is None:
            self.register_provider(provider)
            entry = self.entries[provider]

        entry["total_requests"] += 1
        if success:
            entry["successful_requests"] += 1
        if hallucination:
            entry["hallucination_count"] += 1
        if not privacy_ok:
            entry["privacy_violations"] += 1
        if not policy_compliant:
            entry["policy_violations"] += 1
        if regret_penalty > 0:
            entry["strategic_missteps"] += 1

        quality_bonus = 0.05 if success else -0.2
        privacy_bonus = 0.05 if privacy_ok else -0.15
        compliance_bonus = 0.05 if policy_compliant else -0.15
        strategic_bonus = (strategic_fit - 0.5) * 0.2
        regret_penalty_score = -regret_penalty * 0.3

        trust_delta = quality_bonus + privacy_bonus + compliance_bonus + strategic_bonus + regret_penalty_score
        entry["trust_score"] = max(0.0, min(1.0, entry["trust_score"] + trust_delta))
        entry["long_term_consistency"] = max(0.0, min(1.0, entry["trust_score"] - entry["hallucination_count"] * 0.01))
        entry["last_adjusted"] = datetime.datetime.utcnow().isoformat()
        entry["recent_outcomes"].append({
            "timestamp": entry["last_adjusted"],
            "success": success,
            "hallucination": hallucination,
            "privacy_ok": privacy_ok,
            "strategic_fit": strategic_fit,
            "policy_compliant": policy_compliant,
            "regret_penalty": regret_penalty,
        })
        entry["recent_outcomes"] = entry["recent_outcomes"][-20:]

        logger.debug("Trust registry updated for %s: %s", provider, entry)

    def summary(self) -> dict[str, Any]:
        return {name: dict(record) for name, record in self.entries.items()}
