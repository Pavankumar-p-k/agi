"""Provider budget manager: spend tracking and limits per provider.

Completed from the committed contract in tests/unit/test_provider_ecosystem.py
(TestProviderBudget): record_spend / get_record / set_limit / get_limits /
can_use (daily + per_workflow) with JSON persistence and a process singleton.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

_BUDGET_DIR = Path(__file__).resolve().parent.parent.parent / "data"
_BUDGET_DIR.mkdir(parents=True, exist_ok=True)
_BUDGET_FILE = _BUDGET_DIR / "provider_budgets.json"


@dataclass
class BudgetRecord:
    provider_id: str = ""
    total_spent: float = 0.0
    total_tokens: int = 0
    workflow_spend: dict[str, float] = field(default_factory=dict)
    last_updated: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "total_spent": self.total_spent,
            "total_tokens": self.total_tokens,
            "workflow_spend": dict(self.workflow_spend),
            "last_updated": self.last_updated,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BudgetRecord":
        return cls(
            provider_id=data.get("provider_id", ""),
            total_spent=float(data.get("total_spent", 0.0)),
            total_tokens=int(data.get("total_tokens", 0)),
            workflow_spend=data.get("workflow_spend", {}) or {},
            last_updated=float(data.get("last_updated", 0.0)),
        )


class ProviderBudgetManager:
    """Tracks spend per provider and enforces configured limits.

    ``can_use`` is a guardrail consulted by the router — a provider over its
    daily budget is skipped, never silently allowed to run up costs.
    """

    def __init__(self) -> None:
        self._BUDGET_DIR = _BUDGET_DIR
        self._BUDGET_FILE = _BUDGET_FILE
        self._records: dict[str, BudgetRecord] = {}
        self._limits: dict[str, dict[str, float]] = {}
        self._load()

    # ------------------------------------------------------------------ #
    # Spend                                                              #
    # ------------------------------------------------------------------ #

    def record_spend(
        self,
        provider_id: str,
        cost: float,
        tokens: int = 0,
        workflow_id: str = "",
    ) -> None:
        rec = self._records.setdefault(provider_id, BudgetRecord(provider_id=provider_id))
        rec.total_spent += float(cost)
        rec.total_tokens += int(tokens)
        if workflow_id:
            rec.workflow_spend[workflow_id] = rec.workflow_spend.get(workflow_id, 0.0) + float(cost)
        rec.last_updated = time.time()

    def get_record(self, provider_id: str) -> BudgetRecord:
        return self._records.get(provider_id, BudgetRecord(provider_id=provider_id))

    # ------------------------------------------------------------------ #
    # Limits                                                             #
    # ------------------------------------------------------------------ #

    def set_limit(
        self,
        provider_id: str,
        daily: Optional[float] = None,
        monthly: Optional[float] = None,
        per_workflow: Optional[float] = None,
    ) -> None:
        limits = self._limits.setdefault(provider_id, {})
        if daily is not None:
            limits["daily"] = float(daily)
        if monthly is not None:
            limits["monthly"] = float(monthly)
        if per_workflow is not None:
            limits["per_workflow"] = float(per_workflow)

    def get_limits(self, provider_id: str) -> dict[str, float]:
        return dict(self._limits.get(provider_id, {}))

    def can_use(self, provider_id: str, workflow_id: str = "") -> bool:
        """False when a configured limit is exceeded. Unknown providers can run."""
        limits = self._limits.get(provider_id)
        if not limits:
            return True
        rec = self._records.get(provider_id)
        spent = rec.total_spent if rec else 0.0
        daily = limits.get("daily")
        if daily is not None and spent >= daily:
            return False
        monthly = limits.get("monthly")
        if monthly is not None and spent >= monthly:
            return False
        per_workflow = limits.get("per_workflow")
        if per_workflow is not None and workflow_id and rec is not None:
            wf_spent = rec.workflow_spend.get(workflow_id, 0.0)
            if wf_spent >= per_workflow:
                return False
        return True

    # ------------------------------------------------------------------ #
    # Persistence                                                        #
    # ------------------------------------------------------------------ #

    def _save(self) -> bool:
        try:
            payload = {
                "records": {pid: rec.to_dict() for pid, rec in self._records.items()},
                "limits": dict(self._limits),
                "saved_at": time.time(),
            }
            self._BUDGET_FILE.write_text(json.dumps(payload), encoding="utf-8")
            return True
        except Exception as exc:
            logger.debug("[provider_budget] save failed: %s", exc)
            return False

    def _load(self) -> bool:
        try:
            if not self._BUDGET_FILE.exists():
                return False
            payload = json.loads(self._BUDGET_FILE.read_text(encoding="utf-8"))
            for pid, rec_data in payload.get("records", {}).items():
                self._records[pid] = BudgetRecord.from_dict(rec_data)
            for pid, limits in payload.get("limits", {}).items():
                self._limits[pid] = dict(limits)
            return True
        except Exception as exc:
            logger.debug("[provider_budget] load failed: %s", exc)
            return False


provider_budget = ProviderBudgetManager()
