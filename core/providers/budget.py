from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_BUDGET_DIR = Path.home() / ".jarvis" / "provider_budgets"
_BUDGET_FILE = _BUDGET_DIR / "budgets.json"

_DEFAULT_DAILY_LIMIT = 10.0
_DEFAULT_MONTHLY_LIMIT = 100.0
_DEFAULT_PER_WORKFLOW_LIMIT = 5.0


@dataclass
class ProviderBudgetRecord:
    provider_id: str = ""
    daily_cost: float = 0.0
    daily_reset: float = 0.0
    monthly_cost: float = 0.0
    monthly_reset: float = 0.0
    per_workflow_cost: dict[str, float] = field(default_factory=dict)
    total_spent: float = 0.0
    total_tokens: int = 0

    def check_daily(self, limit: float) -> bool:
        self._maybe_reset_daily()
        return self.daily_cost < limit

    def check_monthly(self, limit: float) -> bool:
        self._maybe_reset_monthly()
        return self.monthly_cost < limit

    def check_workflow(self, workflow_id: str, limit: float) -> bool:
        return self.per_workflow_cost.get(workflow_id, 0.0) < limit

    def record_spend(self, cost: float, tokens: int, workflow_id: str = "") -> None:
        self._maybe_reset_daily()
        self._maybe_reset_monthly()
        self.daily_cost += cost
        self.monthly_cost += cost
        self.total_spent += cost
        self.total_tokens += tokens
        if workflow_id:
            self.per_workflow_cost[workflow_id] = (
                self.per_workflow_cost.get(workflow_id, 0.0) + cost
            )

    def _maybe_reset_daily(self) -> None:
        now = time.time()
        if now - self.daily_reset > 86400:
            self.daily_cost = 0.0
            self.daily_reset = now

    def _maybe_reset_monthly(self) -> None:
        now = time.time()
        if now - self.monthly_reset > 2592000:
            self.monthly_cost = 0.0
            self.monthly_reset = now


class ProviderBudgetManager:
    def __init__(self):
        self._records: dict[str, ProviderBudgetRecord] = {}
        self._limits: dict[str, dict] = {}
        self._load()

    def set_limit(self, provider_id: str, daily: float | None = None,
                   monthly: float | None = None,
                   per_workflow: float | None = None) -> None:
        limits = self._limits.setdefault(provider_id, {})
        if daily is not None:
            limits["daily"] = daily
        if monthly is not None:
            limits["monthly"] = monthly
        if per_workflow is not None:
            limits["per_workflow"] = per_workflow
        self._save()

    def get_limits(self, provider_id: str) -> dict:
        return self._limits.get(provider_id, {})

    def record_spend(self, provider_id: str, cost: float,
                      tokens: int = 0, workflow_id: str = "") -> None:
        record = self._records.setdefault(
            provider_id, ProviderBudgetRecord(provider_id=provider_id)
        )
        record.record_spend(cost, tokens, workflow_id)
        if cost > 0:
            limit = self._get_limit(provider_id, "daily", _DEFAULT_DAILY_LIMIT)
            if not record.check_daily(limit):
                logger.warning("[ProviderBudget] %s daily limit $%.2f exceeded", provider_id, limit)
            limit = self._get_limit(provider_id, "monthly", _DEFAULT_MONTHLY_LIMIT)
            if not record.check_monthly(limit):
                logger.warning("[ProviderBudget] %s monthly limit $%.2f exceeded", provider_id, limit)
        self._save()

    def can_use(self, provider_id: str, workflow_id: str = "") -> bool:
        record = self._records.get(provider_id)
        if not record:
            return True
        if not record.check_daily(self._get_limit(provider_id, "daily", _DEFAULT_DAILY_LIMIT)):
            return False
        if not record.check_monthly(self._get_limit(provider_id, "monthly", _DEFAULT_MONTHLY_LIMIT)):
            return False
        if workflow_id and not record.check_workflow(
            workflow_id, self._get_limit(provider_id, "per_workflow", _DEFAULT_PER_WORKFLOW_LIMIT)
        ):
            return False
        return True

    def get_record(self, provider_id: str) -> ProviderBudgetRecord | None:
        return self._records.get(provider_id)

    def _get_limit(self, provider_id: str, key: str, default: float) -> float:
        return self._limits.get(provider_id, {}).get(key, default)

    def _load(self) -> None:
        try:
            if _BUDGET_FILE.exists():
                data = json.loads(_BUDGET_FILE.read_text(encoding="utf-8"))
                for pid, record_data in data.get("records", {}).items():
                    self._records[pid] = ProviderBudgetRecord(**record_data)
                self._limits = data.get("limits", {})
        except Exception as e:
            logger.warning("[ProviderBudget] Failed to load: %s", e)

    def _save(self) -> None:
        try:
            _BUDGET_DIR.mkdir(parents=True, exist_ok=True)
            data = {
                "records": {pid: vars(rec) for pid, rec in self._records.items()},
                "limits": self._limits,
            }
            _BUDGET_FILE.write_text(
                json.dumps(data, indent=2, default=str), encoding="utf-8"
            )
        except Exception as e:
            logger.warning("[ProviderBudget] Failed to save: %s", e)


provider_budget = ProviderBudgetManager()
