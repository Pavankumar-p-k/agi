"""core/budget_controller.py
Enforces resource limits per project build.
Tracks time, retries, and token usage against configured caps.
"""
import logging
from time import time
from typing import Optional

logger = logging.getLogger(__name__)

_DEFAULT_BUDGET = {
    "max_retries_per_step": 3,
    "max_total_retries": 10,
    "max_runtime_seconds": 600,
    "max_tokens": 100000,
}


class BudgetExhaustedError(Exception):
    pass


class BudgetController:
    def __init__(self, limits: dict = None):
        self.limits = {**_DEFAULT_BUDGET, **(limits or {})}
        self._budgets: dict[str, dict] = {}

    def _init_project(self, project: str):
        if project not in self._budgets:
            self._budgets[project] = {
                "elapsed_seconds": 0.0,
                "retry_count": 0,
                "token_usage": 0,
                "started_at": time(),
                "last_check_at": time(),
            }

    def get_budget(self, project: str) -> dict:
        self._init_project(project)
        return dict(self._budgets[project])

    def record_retry(self, project: str):
        self._init_project(project)
        self._budgets[project]["retry_count"] += 1

    def record_tokens(self, project: str, count: int):
        self._init_project(project)
        self._budgets[project]["token_usage"] += count

    def record_time(self, project: str, seconds: float):
        self._init_project(project)
        self._budgets[project]["elapsed_seconds"] += seconds

    def check_budget(self, project: str) -> tuple[bool, str]:
        self._init_project(project)
        b = self._budgets[project]
        elapsed = time() - b["started_at"]

        if b["retry_count"] >= self.limits["max_total_retries"]:
            return False, f"max_total_retries_exceeded ({b['retry_count']}/{self.limits['max_total_retries']})"

        if elapsed >= self.limits["max_runtime_seconds"]:
            return False, f"max_runtime_exceeded ({elapsed:.1f}s/{self.limits['max_runtime_seconds']}s)"

        if b["token_usage"] >= self.limits["max_tokens"]:
            return False, f"max_tokens_exceeded ({b['token_usage']}/{self.limits['max_tokens']})"

        retry_warn = b["retry_count"] / self.limits["max_total_retries"]
        time_warn = elapsed / self.limits["max_runtime_seconds"]
        token_warn = b["token_usage"] / self.limits["max_tokens"]

        if retry_warn >= 0.8:
            logger.warning(f"[BUDGET] {project}: {b['retry_count']}/{self.limits['max_total_retries']} retries used")
        if time_warn >= 0.8:
            logger.warning(f"[BUDGET] {project}: {elapsed:.0f}/{self.limits['max_runtime_seconds']}s used")
        if token_warn >= 0.8:
            logger.warning(f"[BUDGET] {project}: {b['token_usage']}/{self.limits['max_tokens']} tokens used")

        return True, "ok"

    @staticmethod
    def estimate_token_usage(task_description: str) -> int:
        return max(1, int(len(task_description.split()) * 1.3))

    def reset(self, project: str):
        self._budgets.pop(project, None)


budget_controller = BudgetController()
