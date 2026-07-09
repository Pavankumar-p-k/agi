"""WorkflowExecutionRecorder — observes workflow lifecycle, records outcomes.

Hooks into WorkflowEngine at terminal states (COMPLETED, FAILED, CANCELLED,
COMPENSATED, COMPENSATION_FAILED) and persists WorkflowOutcome records for
the workflow learning system.

This is a pure observer: it never modifies execution, never blocks completion,
and never ranks or scores templates.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any

import importlib as _il
ActivityManager = _il.import_module("core.activity.manager").ActivityManager
from core.activity.storage import ActivityStore
from core.workflow.calibration import WorkflowCalibrationEngine
from core.workflow.learning_models import (
    ProviderEntry,
    RecoveryMode,
    WorkflowFingerprint,
    WorkflowOutcome,
)
from core.workflow.learning_store import WorkflowHistoryStore
from core.workflow.models import StepStatus, WorkflowInstance, WorkflowStatus

logger = logging.getLogger(__name__)


class WorkflowExecutionRecorder:
    """Observes workflow lifecycle and records outcomes for learning.

    Operates in two modes:
      1. Engine-integrated — called by WorkflowEngine at terminal states
      2. Standalone audit  — record_workflow_by_id() reads from store

    Never modifies workflow execution. Never blocks.
    """

    def __init__(
        self,
        history_store: WorkflowHistoryStore | None = None,
        calibration_engine: WorkflowCalibrationEngine | None = None,
        activity_manager: ActivityManager | None = None,
    ):
        self._history = history_store or WorkflowHistoryStore()
        self._calibration = calibration_engine or WorkflowCalibrationEngine(
            history_store=self._history,
        )
        self._activity = activity_manager

    # ── Public API ───────────────────────────────────────────────────

    def record_workflow(
        self,
        wf: WorkflowInstance,
        start_time: float | None = None,
    ) -> WorkflowOutcome | None:
        """Record the outcome of a completed/failed/cancelled workflow.

        Args:
            wf: WorkflowInstance in a terminal state.
            start_time: Optional monotonic clock value from engine start.
                        Used for wall-clock duration.

        Returns:
            WorkflowOutcome if recorded, None if skipped (non-terminal,
            already recorded, or invalid).
        """
        if wf.status not in _TERMINAL_STATUSES:
            logger.debug(
                "Skipping record for %s — non-terminal status %s",
                wf.workflow_id, wf.status,
            )
            return None

        # Append-only guard: never overwrite
        try:
            existing = self._history.get_outcome(wf.workflow_id)
            if existing is not None:
                logger.debug(
                    "Skipping record for %s — already recorded",
                    wf.workflow_id,
                )
                return None
        except Exception:
            pass

        fingerprint = self._build_fingerprint(wf)
        recovery_mode = self._determine_recovery_mode(wf)
        duration_ms = self._compute_duration_ms(wf, start_time)
        error_categories = self._extract_error_categories(wf)
        artifacts = self._extract_artifact_ids(wf)
        activity_graph_id = self._find_activity_graph_id(wf)
        template_id = wf.workflow_type
        template_version = (
            wf.execution_context.get("template_version", 1)
            if wf.execution_context
            else 1
        )

        provider_summary = self._build_provider_summary(wf)

        outcome = WorkflowOutcome(
            workflow_id=wf.workflow_id,
            template_id=template_id,
            template_version=template_version,
            fingerprint=fingerprint,
            success=wf.status == WorkflowStatus.COMPLETED,
            duration_ms=duration_ms,
            cost=wf.execution_context.get("cost", 0.0) if wf.execution_context else 0.0,
            quality=self._compute_quality(wf),
            recovery_mode=recovery_mode,
            artifacts=artifacts,
            error_categories=error_categories,
            provider_summary=provider_summary,
            activity_graph_id=activity_graph_id,
        )

        self._history.save_outcome(outcome)
        logger.info(
            "Recorded outcome for %s: success=%s duration_ms=%.0f mode=%s",
            wf.workflow_id, outcome.success, outcome.duration_ms,
            outcome.recovery_mode.value,
        )

        # Trigger recalibration for this template
        try:
            self._calibration.recalibrate(
                template_id=template_id,
                template_version=template_version,
            )
        except Exception as e:
            logger.warning("Recalibration failed after recording %s: %s", wf.workflow_id, e)

        return outcome

    def record_workflow_by_id(
        self,
        workflow_id: str,
        store: Any = None,
        start_time: float | None = None,
    ) -> WorkflowOutcome | None:
        """Load a workflow from store and record its outcome.

        Useful for audit, recovery, or standalone recording without
        engine integration.
        """
        if store is None:
            from core.workflow.storage import WorkflowStore
            store = WorkflowStore()
        wf = store.get_workflow(workflow_id)
        if wf is None:
            logger.warning("Cannot record %s — workflow not found", workflow_id)
            return None
        return self.record_workflow(wf, start_time=start_time)

    def record_multiple(
        self,
        store: Any = None,
        status_filter: WorkflowStatus | None = None,
    ) -> int:
        """Audit all unrecorded terminal workflows.

        Scans the WorkflowStore for terminal workflows that don't have
        a corresponding outcome in the history store, and records them.

        Returns the number of new outcomes recorded.
        """
        if store is None:
            from core.workflow.storage import WorkflowStore
            store = WorkflowStore()

        terminal_statuses = (
            [status_filter] if status_filter else list(_TERMINAL_STATUSES)
        )
        count = 0
        for status in terminal_statuses:
            workflows = store.list_workflows(status=status.value, limit=1000)
            for wf in workflows:
                try:
                    if self._history.get_outcome(wf.workflow_id) is None:
                        result = self.record_workflow(wf)
                        if result is not None:
                            count += 1
                except Exception as e:
                    logger.debug("Skipping %s during audit: %s", wf.workflow_id, e)
        return count

    # ── Fingerprint construction ─────────────────────────────────────

    def _build_fingerprint(
        self, wf: WorkflowInstance,
    ) -> WorkflowFingerprint | None:
        """Build a WorkflowFingerprint from execution_context fields."""
        ctx = wf.execution_context or {}
        fp = WorkflowFingerprint(
            task_type=ctx.get("task_type", ""),
            complexity=ctx.get("complexity", ""),
            project_size=ctx.get("project_size", ""),
            languages=ctx.get("languages", []),
            frameworks=ctx.get("frameworks", []),
            capabilities=ctx.get("capabilities", []),
            artifact_types=ctx.get("artifact_types", []),
            requirements=ctx.get("requirements", []),
            context_json="",
        )
        # Return None only if every field is empty (no context at all)
        if not fp.context_key():
            return None
        return fp

    # ── Recovery mode determination ──────────────────────────────────

    def _determine_recovery_mode(self, wf: WorkflowInstance) -> RecoveryMode:
        """Determine how the workflow reached its outcome."""
        if wf.status in (
            WorkflowStatus.FAILED,
            WorkflowStatus.CANCELLED,
            WorkflowStatus.COMPENSATION_FAILED,
        ):
            return RecoveryMode.FAILED

        if wf.status == WorkflowStatus.COMPENSATED:
            return RecoveryMode.AFTER_COMPENSATION

        had_retry = any(
            getattr(step, "retry_count", 0) > 0
            for step in (wf.steps or [])
        )

        if had_retry:
            return RecoveryMode.AFTER_RETRY

        return RecoveryMode.FIRST_TRY

    # ── Duration computation ─────────────────────────────────────────

    def _compute_duration_ms(
        self,
        wf: WorkflowInstance,
        start_time: float | None = None,
    ) -> float:
        if start_time is not None:
            elapsed = time.time() - start_time
            return max(0.0, elapsed * 1000.0)

        steps = wf.steps or []
        started = [s.started_at for s in steps if s.started_at]
        completed = [s.completed_at for s in steps if s.completed_at]
        created = wf.created_at

        if started and completed:
            s_min = min(s.timestamp() for s in started)
            c_max = max(c.timestamp() for c in completed)
            return max(0.0, (c_max - s_min) * 1000.0)

        if created and completed:
            c_max = max(c.timestamp() for c in completed)
            return max(0.0, (c_max - created.timestamp()) * 1000.0)

        return 0.0

    # ── Error categories ─────────────────────────────────────────────

    def _extract_error_categories(self, wf: WorkflowInstance) -> list[str]:
        categories: set[str] = set()
        for step in wf.steps or []:
            if step.status == StepStatus.FAILED and step.error:
                categories.add(step.tool_name or "unknown")
                err_lower = step.error.lower()
                if "timeout" in err_lower:
                    categories.add("timeout")
                if any(kw in err_lower for kw in ("import", "module", "cannot find symbol")):
                    categories.add("dependency")
                if any(kw in err_lower for kw in ("permission", "access denied", "forbidden")):
                    categories.add("permission")
                if any(kw in err_lower for kw in ("syntax", "compilation", "compile error")):
                    categories.add("syntax")
        return sorted(categories)

    # ── Artifacts ────────────────────────────────────────────────────

    def _extract_artifact_ids(self, wf: WorkflowInstance) -> list[str]:
        ids: list[str] = []
        for a in wf.artifacts or []:
            if isinstance(a, dict):
                aid = a.get("artifact_id") or a.get("id", "")
                if aid:
                    ids.append(aid)
            elif isinstance(a, str):
                ids.append(a)
        return ids

    # ── Quality score ────────────────────────────────────────────────

    def _compute_quality(self, wf: WorkflowInstance) -> float:
        """Compute a normalized quality score from the outcome.

        Range: 0.0 (worst) to 1.0 (best). Based on:
        - Success (0.6 weight)
        - First-try completion (0.2 weight)
        - No errors (0.2 weight)
        """
        if wf.status == WorkflowStatus.COMPLETED:
            base = 0.6
            had_retry = any(
                getattr(step, "retry_count", 0) > 0
                for step in (wf.steps or [])
            )
            first_try_bonus = 0.2 if not had_retry else 0.0
        else:
            base = 0.0
            first_try_bonus = 0.0

        failed_steps = sum(
            1 for s in (wf.steps or [])
            if s.status == StepStatus.FAILED
        )
        error_penalty = min(0.2, failed_steps * 0.1)
        error_score = 0.2 - error_penalty

        return min(1.0, max(0.0, base + first_try_bonus + error_score))

    # ── Activity graph lookup ────────────────────────────────────────

    def _find_activity_graph_id(self, wf: WorkflowInstance) -> str:
        """Find the root activity_id linked to this workflow."""
        if self._activity is None:
            return ""

        try:
            store: ActivityStore = self._activity.store
            nodes = store.search_nodes(wf.workflow_id, limit=5)
            for node in nodes:
                if node.workflow_id == wf.workflow_id and node.depth == 0:
                    return node.activity_id
            for node in nodes:
                if node.workflow_id == wf.workflow_id:
                    return node.activity_id
        except Exception as e:
            logger.debug("Activity graph lookup failed for %s: %s", wf.workflow_id, e)

        return ""


    # ── Provider summary ─────────────────────────────────────────────

    def _build_provider_summary(
        self, wf: WorkflowInstance,
    ) -> list[dict[str, Any]]:
        """Build structured provider entries from execution context.

        Priority order:
          1. provider_entries — structured list in execution_context
          2. provider_summary  — old dict format in execution_context
          3. step-level extraction — build from step tools + timing
        """
        ctx = wf.execution_context or {}

        entries = ctx.get("provider_entries")
        if isinstance(entries, list) and entries:
            return [dict(e) if not isinstance(e, dict) else e for e in entries]

        old_summary = ctx.get("provider_summary")
        if isinstance(old_summary, dict) and old_summary:
            return self._convert_old_provider_summary(old_summary, wf)

        return []

    def _convert_old_provider_summary(
        self, old: dict[str, Any], wf: WorkflowInstance,
    ) -> list[dict[str, Any]]:
        """Convert old provider_summary dict to structured entry list."""
        entries: list[dict[str, Any]] = []
        steps = wf.steps or []

        for provider, value in old.items():
            capability = ""
            duration_ms = 0.0
            success = bool(value) if isinstance(value, bool) else False
            retries = 0

            for step in steps:
                if step.tool_name and provider.lower() in step.tool_name.lower():
                    capability = step.tool_name
                    if step.started_at and step.completed_at:
                        d = (step.completed_at - step.started_at).total_seconds() * 1000
                        duration_ms = max(duration_ms, d)
                    retries = max(retries, getattr(step, "retry_count", 0))
                    if step.status.value == "COMPLETED":
                        success = True
                    break

            entries.append({
                "provider": provider,
                "capability": capability,
                "duration_ms": duration_ms,
                "success": success,
                "retries": retries,
                "cost": 0.0,
            })

        return entries


_TERMINAL_STATUSES: frozenset = frozenset({
    WorkflowStatus.COMPLETED,
    WorkflowStatus.FAILED,
    WorkflowStatus.CANCELLED,
    WorkflowStatus.COMPENSATED,
    WorkflowStatus.COMPENSATION_FAILED,
})
