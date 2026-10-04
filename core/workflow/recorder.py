"""Records terminal workflow runs as learning outcomes."""

from __future__ import annotations

import time
from datetime import datetime

from core.workflow.calibration import WorkflowCalibrationEngine
from core.workflow.learning_models import (
    RecoveryMode,
    WorkflowFingerprint,
    WorkflowOutcome,
)
from core.workflow.learning_store import WorkflowHistoryStore
from core.workflow.models import (
    StepStatus,
    WorkflowInstance,
    WorkflowStatus,
    WorkflowStep,
)

# Error-text patterns classified into outcome error categories.
_ERROR_PATTERNS = (
    "syntax",
    "timeout",
    "refused",
    "denied",
    "not found",
    "no such",
    "permission",
    "connection",
    "network",
    "unreachable",
    "memory",
    "disk",
    "quota",
    "traceback",
    "exception",
    "unresolved",
)

_TERMINAL_STATUSES = {
    WorkflowStatus.COMPLETED,
    WorkflowStatus.FAILED,
    WorkflowStatus.CANCELLED,
    WorkflowStatus.COMPENSATED,
    WorkflowStatus.COMPENSATION_FAILED,
}

_FINGERPRINT_DIMS = (
    "task_type",
    "complexity",
    "project_size",
    "languages",
    "frameworks",
)


def _max_retries(steps: list[WorkflowStep]) -> int:
    if not steps:
        return 0
    return max(int(s.retry_count or 0) for s in steps)


def _recovery_mode(wf: WorkflowInstance) -> RecoveryMode:
    if wf.status == WorkflowStatus.COMPLETED:
        if _max_retries(wf.steps) > 0:
            return RecoveryMode.AFTER_RETRY
        return RecoveryMode.FIRST_TRY
    if wf.status == WorkflowStatus.COMPENSATED:
        return RecoveryMode.AFTER_COMPENSATION
    return RecoveryMode.FAILED


def _build_fingerprint(context: dict) -> WorkflowFingerprint | None:
    kwargs = {}
    for dim in _FINGERPRINT_DIMS:
        value = context.get(dim)
        if value is None:
            continue
        if isinstance(value, str):
            if value.strip():
                kwargs[dim] = value
        elif isinstance(value, (list, tuple)):
            items = [str(v) for v in value if str(v).strip()]
            if items:
                kwargs[dim] = items
    if not kwargs:
        return None
    fingerprint = WorkflowFingerprint(**kwargs)
    if not fingerprint.context_key():
        return None
    return fingerprint


def _duration_ms(wf: WorkflowInstance, start_time: float | None) -> float:
    if start_time is not None:
        return max(0.0, (time.time() - float(start_time)) * 1000.0)
    starts = [s.started_at for s in wf.steps if s.started_at is not None]
    completes = [s.completed_at for s in wf.steps if s.completed_at is not None]
    if not starts or not completes:
        return 0.0
    delta = max(completes) - min(starts)
    return max(0.0, delta.total_seconds() * 1000.0)


def _error_categories(wf: WorkflowInstance) -> list[str]:
    categories: list[str] = []
    for step in wf.steps:
        if step.status != StepStatus.FAILED:
            continue
        if step.tool_name and step.tool_name not in categories:
            categories.append(step.tool_name)
        if not step.error:
            continue
        lowered = step.error.lower()
        for pattern in _ERROR_PATTERNS:
            if pattern in lowered and pattern not in categories:
                categories.append(pattern)
    return categories


def _quality(success: bool, retries: int) -> float:
    score = 0.2
    if success:
        score += 0.6
        if retries == 0:
            score += 0.2
    return score


def _provider_summary(context: dict) -> list:
    entries = context.get("provider_entries")
    if isinstance(entries, list) and entries:
        return [dict(e) if isinstance(e, dict) else e for e in entries]
    legacy = context.get("provider_summary")
    if isinstance(legacy, dict) and legacy:
        return [
            {
                "provider": name,
                "capability": "",
                "duration_ms": 0.0,
                "success": bool(ok),
                "retries": 0,
                "cost": 0.0,
            }
            for name, ok in legacy.items()
        ]
    return []


def _artifact_ids(artifacts: list) -> list[str]:
    ids: list[str] = []
    for artifact in artifacts or []:
        if isinstance(artifact, dict):
            value = artifact.get("artifact_id") or artifact.get("id")
            if value is not None:
                ids.append(str(value))
        elif isinstance(artifact, str):
            ids.append(artifact)
    return ids


class WorkflowExecutionRecorder:
    """Turns terminal WorkflowInstances into persisted WorkflowOutcomes."""

    def __init__(
        self,
        history_store: WorkflowHistoryStore,
        calibration_engine: WorkflowCalibrationEngine | None = None,
    ) -> None:
        self._history = history_store
        self._calibration = calibration_engine

    def record_workflow(
        self,
        wf: WorkflowInstance,
        start_time: float | None = None,
    ) -> WorkflowOutcome | None:
        if wf.status not in _TERMINAL_STATUSES:
            return None
        if self._history.get_outcome(wf.workflow_id) is not None:
            return None

        context = wf.execution_context or {}
        template_version = context.get("template_version") or 1
        try:
            template_version = int(template_version)
        except (TypeError, ValueError):
            template_version = 1

        success = wf.status == WorkflowStatus.COMPLETED
        retries = _max_retries(wf.steps)
        outcome = WorkflowOutcome(
            workflow_id=wf.workflow_id,
            template_id=wf.workflow_type,
            template_version=template_version,
            fingerprint=_build_fingerprint(context),
            success=success,
            duration_ms=_duration_ms(wf, start_time),
            cost=float(context.get("cost", 0.0) or 0.0),
            quality=_quality(success, retries),
            recovery_mode=_recovery_mode(wf),
            artifacts=_artifact_ids(wf.artifacts),
            error_categories=_error_categories(wf),
            provider_summary=_provider_summary(context),
            activity_graph_id=context.get("activity_graph_id"),
        )

        self._history.save_outcome(outcome)

        if self._calibration is not None:
            self._calibration.recalibrate(
                outcome.template_id,
                template_version=outcome.template_version,
            )
        return outcome

    def record_workflow_by_id(
        self,
        workflow_id: str,
        store=None,
    ) -> WorkflowOutcome | None:
        if store is None:
            return None
        wf = store.get_workflow(workflow_id)
        if wf is None:
            return None
        return self.record_workflow(wf)

    def record_multiple(self, store=None) -> int:
        if store is None:
            return 0
        count = 0
        for wf in store.list_workflows():
            if self.record_workflow(wf) is not None:
                count += 1
        return count
