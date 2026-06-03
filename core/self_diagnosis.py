"""core/self_diagnosis.py
Meta-monitor that watches the JARVIS system itself.
Detects stuck loops, zero progress, dead agents, and resource leaks.
"""
import time
import logging
from dataclasses import dataclass, field
from typing import Optional
from collections import deque

logger = logging.getLogger(__name__)


@dataclass
class SystemHealthIssue:
    type: str
    severity: str
    message: str
    suggestion: str = ""


_STUCK_FAILURE_THRESHOLD = 3
_NO_PROGRESS_SECONDS = 60
_STATE_HISTORY_SIZE = 5


@dataclass
class _StateSnapshot:
    status: str
    retries: int
    failures: tuple
    task_id: str
    timestamp: float


class SelfDiagnosis:
    def __init__(self, history_size: int = _STATE_HISTORY_SIZE):
        self.history_size = history_size
        self._history: dict[str, deque] = {}

    def _get_history(self, project: str) -> deque:
        if project not in self._history:
            self._history[project] = deque(maxlen=self.history_size)
        return self._history[project]

    def check_health(self, state, previous_state=None) -> list[dict]:
        issues: list[dict] = []
        project = getattr(state, "project_name", "unknown")
        history = self._get_history(project)

        snapshot = _StateSnapshot(
            status=getattr(state, "status", ""),
            retries=getattr(state, "retries", 0),
            failures=tuple(getattr(state, "issues", []) or []),
            task_id=getattr(state, "current_task_id", ""),
            timestamp=time.time(),
        )

        history.append(snapshot)
        if len(history) < 2:
            return issues

        latest_failures = snapshot.failures

        repeated = 0
        for h in reversed(list(history)[:-1]):
            if h.failures == latest_failures and latest_failures:
                repeated += 1
            else:
                break
        if repeated >= _STUCK_FAILURE_THRESHOLD:
            issue = {
                "type": "stuck_loop",
                "severity": "critical",
                "message": f"Same failure repeated {repeated + 1} times in a row: {latest_failures}",
                "suggestion": "Check if the fix tasks are being generated correctly. Consider a different approach or escalate.",
            }
            issues.append(issue)
            logger.critical(f"[DIAGNOSIS] {project}: {issue['message']}")

        if previous_state:
            prev_retries = getattr(previous_state, "retries", 0)
            prev_failures = tuple(getattr(previous_state, "issues", []) or [])
            if snapshot.retries > prev_retries and snapshot.failures == prev_failures and snapshot.failures:
                issue = {
                    "type": "zero_progress",
                    "severity": "warning",
                    "message": f"Retry {snapshot.retries} but same failures persist: {snapshot.failures}",
                    "suggestion": "Validation failures are not being addressed. Review the fix generation logic.",
                }
                issues.append(issue)
                logger.warning(f"[DIAGNOSIS] {project}: {issue['message']}")

        last_ts = history[-2].timestamp if len(history) >= 2 else history[-1].timestamp
        time_since_change = time.time() - last_ts
        if time_since_change > _NO_PROGRESS_SECONDS and len(history) >= 3:
            all_same = all(h.status == history[-1].status for h in history)
            if all_same:
                issue = {
                    "type": "slow_progress",
                    "severity": "warning",
                    "message": f"No status change in {time_since_change:.0f}s (status: {snapshot.status})",
                    "suggestion": "The build may be stuck waiting for an agent response. Consider cancelling and retrying.",
                }
                issues.append(issue)
                logger.warning(f"[DIAGNOSIS] {project}: {issue['message']}")

        dead_agents = self._detect_dead_agents(snapshot)
        issues.extend(dead_agents)

        resource_leaks = self._detect_resource_leaks(snapshot)
        issues.extend(resource_leaks)

        return issues

    def _detect_dead_agents(self, snapshot: _StateSnapshot) -> list[dict]:
        issues = []
        task_id = snapshot.task_id
        if task_id and snapshot.status in ("building", "fixing"):
            if hasattr(self, "_last_task_seen"):
                if self._last_task_seen.get(snapshot.task_id, 0) == 0:
                    self._last_task_seen = {}
                last = self._last_task_seen.setdefault(task_id, time.time())
                elapsed = time.time() - last
                if elapsed > 120:
                    issues.append({
                        "type": "dead_agent",
                        "severity": "critical",
                        "message": f"Task {task_id} has been running for {elapsed:.0f}s with no visible output",
                        "suggestion": "Kill the agent process and retry with a different agent or shorter timeout.",
                    })
            else:
                self._last_task_seen = {task_id: time.time()}
        return issues

    def _detect_resource_leaks(self, snapshot: _StateSnapshot) -> list[dict]:
        issues = []
        if hasattr(self, "_last_check_time"):
            elapsed = time.time() - self._last_check_time
            if elapsed > 300:
                issues.append({
                    "type": "long_runtime",
                    "severity": "warning",
                    "message": f"Diagnosis check skipped for {elapsed:.0f}s",
                    "suggestion": "Ensure the health check is being called regularly.",
                })
        self._last_check_time = time.time()
        return issues

    def get_trend(self, project: str) -> list[dict]:
        history = self._get_history(project)
        return [
            {
                "status": h.status,
                "retries": h.retries,
                "failures": list(h.failures),
                "task_id": h.task_id,
                "timestamp": h.timestamp,
            }
            for h in history
        ]

    def clear_history(self, project: str):
        self._history.pop(project, None)


self_diagnosis = SelfDiagnosis()
