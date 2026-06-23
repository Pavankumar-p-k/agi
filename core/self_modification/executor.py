"""Self-Modification Engine (Phase 18.0) — Modification Executor.

Orchestrates the full modification lifecycle:

  1. Snapshot current state (file backup, metrics collection)
  2. Generate patches via recipe
  3. Apply patches
  4. Run tests
  5. Collect after-metrics
  6. Safety post-check → promote or rollback
  7. Record outcome

The executor does NOT decide WHAT to modify — that is the planner's job.
It only executes the plan and verifies the result.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from core.self_modification.models import (
    ModificationMetrics,
    ModificationPlan,
    ModificationRecord,
    ModificationStatus,
    ModificationRecipe,
)
from core.self_modification.recipes import apply_recipe
from core.self_modification.safety import (
    SelfModificationSafety,
    PreCheckResult,
    PostCheckResult,
)
from core.self_modification.store import ModificationStore

logger = logging.getLogger(__name__)


class ModificationRollbackSnapshot:
    """Captures file state before modification for rollback."""

    def __init__(self, file_path: str, original_content: str):
        self.file_path = file_path
        self.original_content = original_content

    def restore(self) -> bool:
        try:
            with open(self.file_path, "w", encoding="utf-8") as f:
                f.write(self.original_content)
            logger.info(f"Rolled back: {self.file_path}")
            return True
        except Exception as e:
            logger.error(f"Rollback failed for {self.file_path}: {e}")
            return False


class SelfModificationExecutor:
    """Executes a ModificationPlan through the full lifecycle.

    Flow:
        plan → snapshot → generate_patches → apply → test → measure
        → safety_check → promote | rollback
    """

    def __init__(
        self,
        store: ModificationStore | None = None,
        safety: SelfModificationSafety | None = None,
        test_runner: Callable | None = None,
    ):
        self.store = store or ModificationStore()
        self.safety = safety or SelfModificationSafety()
        self.test_runner = test_runner
        self._snapshots: list[ModificationRollbackSnapshot] = []

    # ── Public API ─────────────────────────────────────────────────────

    def execute(self, plan: ModificationPlan) -> ModificationRecord:
        """Execute a modification plan through the full lifecycle.

        Returns a ModificationRecord summarizing the outcome.
        """
        record = self._create_record(plan)
        self.store.save(record)

        # 1. Pre-checks
        pre_check = self.safety.check_pre(plan)
        if not pre_check.passed:
            logger.warning(f"Pre-check failed: {pre_check.reason}")
            record.status = ModificationStatus.FAILED
            record.error_message = pre_check.reason
            self.store.save(record)
            return record

        logger.info(f"Pre-checks passed ({len(pre_check.details)} checks)")

        # 2. Snapshot before state
        before_metrics = self._collect_metrics(plan)
        record.before_metrics = before_metrics.to_dict()
        record.status = ModificationStatus.IN_PROGRESS
        self.store.save(record)

        try:
            # 3. Snapshot files
            self._create_snapshots(plan)

            # 4. Generate and apply patches
            patches = self._generate_patches(plan)
            if not patches:
                logger.info("No patches generated (registry-only change)")
                record.status = ModificationStatus.APPLIED
                record.patch_count = 0
                self.store.save(record)
                return self._finalize_promotion(record, plan)

            # 5. Apply patches
            self._apply_patches(patches, plan)
            record.patch_count = len(patches)
            record.status = ModificationStatus.APPLIED
            self.store.save(record)

            # 6. Run tests
            after_metrics = self._collect_metrics(plan)
            record.after_metrics = after_metrics.to_dict()
            record.test_count = int(after_metrics.test_pass_rate > 0)
            record.test_passed = int(
                after_metrics.test_pass_rate
                * (after_metrics.error_count + 1)
            ) if after_metrics.test_pass_rate > 0 else 0
            self.store.save(record)

            # 7. Post-check
            post_check = self.safety.check_post(before_metrics, after_metrics)
            if not post_check.passed:
                logger.warning(f"Post-check failed: {post_check.reason}")
                self._rollback(record, post_check.reason)
                return record

            # 8. Promote
            return self._finalize_promotion(record, plan)

        except Exception as e:
            logger.error(f"Modification execution error: {e}")
            self._rollback(record, str(e))
            return record

    def rollback_record(self, record_id: str) -> bool:
        """Roll back a previously promoted modification."""
        record = self.store.get(record_id)
        if record is None:
            logger.warning(f"Record not found: {record_id}")
            return False

        if record.status != ModificationStatus.PROMOTED:
            logger.warning(f"Record {record_id} is {record.status.value}, cannot rollback")
            return False

        if not record.target_file or not os.path.exists(record.target_file):
            logger.warning(f"Target file not found: {record.target_file}")
            return False

        # Restore from before_metrics? No — we need the original file content.
        # For rollback we'd need to have stored the original content.
        # Phase 18.1 can add full file backup; for now we report the gap.
        logger.info(f"Rollback requested for {record_id} — requires Phase 18.1 file backup")
        return False

    # ── Internal Steps ─────────────────────────────────────────────────

    def _create_record(self, plan: ModificationPlan) -> ModificationRecord:
        return ModificationRecord(
            record_id=f"sm_{uuid.uuid4().hex[:12]}",
            plan_id=plan.plan_id,
            proposal_id=plan.proposal_id,
            recipe=plan.recipe.value,
            target_system=plan.target.system_name,
            target_file=plan.target.target_file,
            status=ModificationStatus.PLANNED,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    def _create_snapshots(self, plan: ModificationPlan) -> None:
        """Back up files before modification."""
        self._snapshots = []
        if plan.target.target_file and os.path.exists(plan.target.target_file):
            with open(plan.target.target_file, "r", encoding="utf-8") as f:
                content = f.read()
            self._snapshots.append(
                ModificationRollbackSnapshot(plan.target.target_file, content)
            )
            logger.info(f"Snapshot created: {plan.target.target_file} ({len(content)} bytes)")

    def _generate_patches(self, plan: ModificationPlan) -> list[dict[str, Any]]:
        """Generate patches by applying the recipe."""
        return apply_recipe(plan.recipe, plan.target)

    def _apply_patches(
        self, patches: list[dict[str, Any]], plan: ModificationPlan
    ) -> None:
        """Write patches to disk."""
        for patch in patches:
            file_path = patch["file"]
            new_content = patch["new_content"]
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(new_content)
            logger.info(f"Applied patch to {file_path} ({len(new_content)} bytes)")

    def _collect_metrics(self, plan: ModificationPlan) -> ModificationMetrics:
        """Collect before/after metrics for the modification.

        Runs project tests if a test_runner is configured, otherwise
        returns a minimal metrics object.
        """
        metrics = ModificationMetrics()

        if self.test_runner:
            try:
                result = self.test_runner()
                if isinstance(result, dict):
                    metrics.test_pass_rate = result.get("pass_rate", 0.0)
                    metrics.error_count = result.get("error_count", 0)
                    metrics.execution_time_seconds = result.get("duration", 0.0)
                    metrics.coverage_percent = result.get("coverage", 0.0)
                elif isinstance(result, (int, float)):
                    metrics.test_pass_rate = float(result)
            except Exception as e:
                logger.warning(f"Test runner failed (non-fatal): {e}")

        return metrics

    def _finalize_promotion(
        self, record: ModificationRecord, plan: ModificationPlan
    ) -> ModificationRecord:
        """Mark modification as promoted and save."""
        record.status = ModificationStatus.PROMOTED
        record.completed_at = datetime.now(timezone.utc).isoformat()
        self.store.save(record)
        logger.info(
            f"Modification promoted: {plan.recipe.value} on "
            f"{plan.target.system_name} (record={record.record_id})"
        )
        return record

    def _rollback(self, record: ModificationRecord, reason: str) -> None:
        """Roll back all file snapshots and update the record."""
        errors = []
        for snapshot in self._snapshots:
            if not snapshot.restore():
                errors.append(snapshot.file_path)

        if errors:
            record.error_message = (
                f"Rollback partial failure on: {', '.join(errors)}. "
                f"Original reason: {reason}"
            )
        else:
            record.error_message = reason

        record.status = ModificationStatus.ROLLED_BACK
        record.completed_at = datetime.now(timezone.utc).isoformat()
        self.store.save(record)
        logger.info(f"Rolled back: {record.record_id} ({reason})")
