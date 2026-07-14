"""Phase 13.0 — Automated Build Tool.

Wraps AutomationLoop._build_project() as a synchronous tool surface
for the graph runtime. Produces BuildExecutionRecord with typed artifacts,
ActivityGraph nodes, and CalibrationStore records.

Key design decision (from spec):
  Call AutomationLoop._build_project(goal) directly instead of routing
  through start() → _run_loop() → _tick().

Progress events carry execution_id for concurrent build isolation.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)

# ── Typed artifact type constants ─────────────────────────────────

ARTIFACT_TYPE_SOURCE = "source_code"
ARTIFACT_TYPE_BUILD_LOG = "build_log"
ARTIFACT_TYPE_TEST_REPORT = "test_report"
ARTIFACT_TYPE_APK = "apk"
ARTIFACT_TYPE_AAB = "aab"
ARTIFACT_TYPE_REPORT = "report"
ARTIFACT_TYPE_COVERAGE = "coverage"


# ── Data models ───────────────────────────────────────────────────

@dataclass
class BuildPhaseRecord:
    """Record of a single build phase execution."""
    phase: str
    status: str                       # pending | running | completed | failed | skipped
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_seconds: float = 0.0
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class BuildExecutionRecord:
    """Single internal result object for a completed automated build.

    Produced by the adapter, consumed by ActivityGraph, CalibrationStore,
    KnowledgeStore, and the caller.
    """
    execution_id: str
    goal: str
    started_at: datetime
    completed_at: datetime

    success: bool
    status: str                        # completed | failed | building | cancelled
    failure_reason: str | None = None

    phases: list[BuildPhaseRecord] = field(default_factory=list)
    artifacts: list[dict] = field(default_factory=list)  # [{type, path}]

    project_dir: str = ""
    completion_pct: float = 0.0
    repair_cycles: int = 0
    repaired_errors: int = 0

    predicted_duration_days: float | None = None
    actual_duration_seconds: float = 0.0

    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "goal": self.goal[:200],
            "success": self.success,
            "status": self.status,
            "failure_reason": self.failure_reason,
            "phases": [
                {
                    "phase": p.phase,
                    "status": p.status,
                    "duration_seconds": round(p.duration_seconds, 1),
                    "error": p.error,
                }
                for p in self.phases
            ],
            "artifacts": self.artifacts,
            "project_dir": self.project_dir,
            "completion_pct": round(self.completion_pct, 1),
            "repair_cycles": self.repair_cycles,
            "repaired_errors": self.repaired_errors,
            "actual_duration_seconds": round(self.actual_duration_seconds, 1),
            "duration_days": round(self.actual_duration_seconds / 86400.0, 2),
        }

    @property
    def actual_duration_days(self) -> float:
        return self.actual_duration_seconds / 86400.0 if self.actual_duration_seconds else 0.0


# ── Progress event helpers ────────────────────────────────────────

async def _emit_progress(progress_cb: Callable[[dict], Awaitable[None]] | None,
                         execution_id: str, phase: str, status: str,
                         message: str, progress: float = 0.0) -> None:
    """Emit a structured progress event with execution_id.

    Every event carries execution_id so concurrent builds do not
    interleave their progress streams.
    """
    if not progress_cb:
        return
    try:
        await progress_cb({
            "execution_id": execution_id,
            "phase": phase,
            "status": status,
            "progress": round(progress, 2),
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
    except Exception as exc:
        logger.debug("progress callback failed: %s", exc)


# ── Artifact detection ────────────────────────────────────────────

_BUILD_ARTIFACT_PATTERNS: list[tuple[str, str]] = [
    ("*.apk", ARTIFACT_TYPE_APK),
    ("*.aab", ARTIFACT_TYPE_AAB),
    ("build.log", ARTIFACT_TYPE_BUILD_LOG),
    ("*.log", ARTIFACT_TYPE_BUILD_LOG),
    ("*.html", ARTIFACT_TYPE_REPORT),
    ("coverage.xml", ARTIFACT_TYPE_COVERAGE),
    ("test-results.xml", ARTIFACT_TYPE_TEST_REPORT),
    ("TEST-*.xml", ARTIFACT_TYPE_TEST_REPORT),
]


def _find_build_artifacts(project_dir: str) -> list[dict]:
    """Scan project_dir for build artifacts with typed paths."""
    import fnmatch
    found: list[dict] = []
    if not os.path.isdir(project_dir):
        return found
    for root, _dirs, files in os.walk(project_dir):
        for fname in files:
            for pattern, art_type in _BUILD_ARTIFACT_PATTERNS:
                if fnmatch.fnmatch(fname, pattern):
                    rel = os.path.relpath(os.path.join(root, fname), project_dir)
                    found.append({
                        "type": art_type,
                        "path": rel.replace("\\", "/"),
                    })
                    break
    return found


# ── ActivityGraph integration ─────────────────────────────────────

async def _record_activity_nodes(record: BuildExecutionRecord) -> None:
    """Create ActivityGraph nodes for the automated build execution.

    Parent node: type="build", label="{goal}". Children: one per phase
    with node_type="build_phase" and execution_id in metadata.
    """
    try:
        import importlib as _il
        _as_mod = _il.import_module("core.activity.models")
        ActivityNode = _as_mod.ActivityNode
        ActivityStatus = _as_mod.ActivityStatus
        from core.activity.storage import ActivityStore
    except ImportError:
        logger.debug("ActivityStore not available, skipping activity recording")
        return

    store = ActivityStore()
    now = datetime.now(timezone.utc)

    # Parent build node
    parent = ActivityNode(
        node_id=f"ab_{record.execution_id}",
        activity_id=f"ab_{record.execution_id}",
        node_type="build",
        label=record.goal[:200],
        status=ActivityStatus.COMPLETED if record.success else ActivityStatus.FAILED,
        metadata={
            "execution_id": record.execution_id,
            "origin": "automated_build",
            "repair_cycles": record.repair_cycles,
            "repaired_errors": record.repaired_errors,
        },
        started_at=record.started_at,
        completed_at=record.completed_at,
    )
    try:
        store.create_node(parent)
    except Exception as exc:
        logger.debug("ActivityStore: failed to create parent node: %s", exc)
        return

    # Child phase nodes
    for phase in record.phases:
        phase_status = ActivityStatus.COMPLETED
        if phase.status == "failed":
            phase_status = ActivityStatus.FAILED
        elif phase.status == "skipped":
            phase_status = ActivityStatus.SKIPPED
        elif phase.status == "running":
            phase_status = ActivityStatus.RUNNING

        child = ActivityNode(
            node_id=f"ab_{record.execution_id}_{phase.phase}",
            activity_id=f"ab_{record.execution_id}",
            node_type="build_phase",
            label=f"{phase.phase}: {record.goal[:80]}",
            status=phase_status,
            depth=1,
            parent_id=parent.node_id,
            metadata={
                "execution_id": record.execution_id,
                "phase": phase.phase,
            },
            started_at=phase.started_at or now,
            completed_at=phase.completed_at or now,
        )
        try:
            store.create_node(child)
        except Exception as exc:
            logger.debug("ActivityStore: failed to create phase node %s: %s",
                         phase.phase, exc)

    # ── Artifact lineage (requirement B) ──
    # Artifact nodes as direct children of build_execution (depth 1, siblings of phases).
    # This enables queries like "which artifacts correlate with successful builds"
    # without traversing through phase nodes.
    for art in record.artifacts:
        art_node = ActivityNode(
            node_id=f"ab_{record.execution_id}_artifact_{art.get('type', 'unknown')}",
            activity_id=f"ab_{record.execution_id}",
            node_type="artifact",
            label=f"{art.get('type', 'file')}: {art.get('path', '')[:60]}",
            status=ActivityStatus.COMPLETED,
            depth=1,
            parent_id=parent.node_id,
            metadata={
                "artifact_type": art.get("type", "unknown"),
                "path": art.get("path", ""),
                "execution_id": record.execution_id,
            },
        )
        try:
            store.create_node(art_node)
        except Exception as exc:
            logger.debug("ActivityStore: failed to create artifact node: %s", exc)


# ── KnowledgeStore integration (requirement C) ───────────────────

async def _record_knowledge(record: BuildExecutionRecord) -> None:
    """Feed build outcomes into KnowledgeStore via ExperienceExtractor.

    This unifies FailureMemory and KnowledgeStore into one learning stream:
      AutomationLoop → ExperienceExtractor → KnowledgeStore
    """
    try:
        import importlib as _il
        ActivityManager = _il.import_module("core.activity.manager").ActivityManager
        from core.activity.storage import ActivityStore
        from core.long_term_memory.extractor import ExperienceExtractor
        from core.long_term_memory.store import KnowledgeStore
    except ImportError:
        logger.debug("KnowledgeStore not available, skipping")
        return

    try:
        store = ActivityStore()
        mgr = ActivityManager(store)
        ks = KnowledgeStore()
        extractor = ExperienceExtractor(mgr, ks)

        activity_id = f"ab_{record.execution_id}"
        summary = extractor.extract(activity_id)
        if summary:
            ks.insert_experience(summary)
            logger.info("[AutoBuild] KnowledgeStore updated from %s", activity_id)
        else:
            logger.debug("ExperienceExtractor returned None for %s", activity_id)
    except Exception as exc:
        logger.debug("KnowledgeStore recording failed: %s", exc)


# ── Calibration integration ──────────────────────────────────────

async def _record_calibration(record: BuildExecutionRecord) -> None:
    """Record build outcomes into CalibrationStore for strategy learning.

    Creates a minimal StrategyDecision and records predicted vs actual.
    When no prediction exists (first-time build), uses default heuristics
    as the 'prediction' so the calibration system has a baseline.
    """
    try:
        from core.strategy.calibration import PredictionCalibrator
        from core.strategy.models import Prediction, Strategy, StrategyDecision, StrategyTag
    except ImportError:
        logger.debug("Calibration not available, skipping calibration recording")
        return

    from core.belief.integration import BeliefIntegrator
    calibrator = PredictionCalibrator(belief_integrator=BeliefIntegrator())

    # Build a minimal strategy with a default heuristic prediction
    duration_days = record.actual_duration_seconds / 86400.0 if record.actual_duration_seconds else 1.0
    tag = StrategyTag.MVP
    strategy = Strategy(
        name="automated_build",
        description="AutomationLoop-backed build",
        goal=record.goal,
        tags=[tag],
        prediction=Prediction(
            success_probability=0.75,
            estimated_duration_days=duration_days,
            estimated_risk=0.3,
            estimated_effort=5.0,
            confidence=0.3,
        ),
    )

    decision = StrategyDecision(
        decision_id=f"ab_cal_{record.execution_id}",
        goal=record.goal,
        timestamp=datetime.now(timezone.utc),
        strategies_considered=[strategy],
        chosen_strategy=strategy,
        confidence=0.3,
    )

    try:
        calibrator.store.record(
            decision, "build",
            actual_success=record.success,
            actual_duration_days=max(duration_days, 0.01),
        )
        logger.info("[AutoBuild] calibration recorded for %s (success=%s, duration=%.1fd)",
                     record.execution_id, record.success, duration_days)
    except Exception as exc:
        logger.debug("CalibrationStore: record failed: %s", exc)


# ── Main adapter ──────────────────────────────────────────────────

async def do_automated_build(
    task: str,
    project_dir: str = "",
    progress_cb: Callable[[dict], Awaitable[None]] | None = None,
    **kwargs,
) -> BuildExecutionRecord:
    """Execute an automated build via AutomationLoop.

    Wraps the existing AutomationLoop._build_project() call, adding:
      - execution_id on every progress event
      - BuildExecutionRecord output
      - ActivityGraph node creation
      - CalibrationStore recording
      - Typed artifact scanning

    Args:
        task: The goal/objective for the build (e.g., "Build Android coffee shop app")
        project_dir: Working directory for the project
        progress_cb: Async callback for progress events

    Returns:
        BuildExecutionRecord with full execution details
    """
    execution_id = uuid.uuid4().hex[:12]
    start_time = time.time()
    start_dt = datetime.now(timezone.utc)

    await _emit_progress(progress_cb, execution_id, "initialize", "running",
                         f"Starting automated build: {task[:80]}", 0.0)

    phases: list[BuildPhaseRecord] = []

    try:
        # ── Phase: planning ──
        phase_plan = BuildPhaseRecord(phase="planning", status="running",
                                       started_at=datetime.now(timezone.utc))

        await _emit_progress(progress_cb, execution_id, "planning", "running",
                             "Creating build plan", 0.05)

        # Ensure the build loop singleton exists
        from core.tools.build_tools import _ensure_automation, _GOAL_MANAGER, _BUILD_LOOP
        await _ensure_automation(project_dir)

        # Create a Goal for this build
        goal = _GOAL_MANAGER.create(goal=task, priority=10, tags=["automated_build"])

        phase_plan.status = "completed"
        phase_plan.completed_at = datetime.now(timezone.utc)
        phase_plan.duration_seconds = time.time() - start_time
        phases.append(phase_plan)

        # ── Phase: building ──
        phase_build = BuildPhaseRecord(phase="building", status="running",
                                        started_at=datetime.now(timezone.utc))

        await _emit_progress(progress_cb, execution_id, "building", "running",
                             "Running AutomationLoop build", 0.15)

        # Execute the build loop directly (no tick routing)
        await _BUILD_LOOP._build_project(goal)

        # Re-fetch the goal to get the final status
        final_goal = _GOAL_MANAGER.get(goal.id)
        goal_status = final_goal.status.value if final_goal else "unknown"
        success = goal_status == "completed"

        phase_build.status = "completed" if success else "failed"
        phase_build.completed_at = datetime.now(timezone.utc)
        phase_build.duration_seconds = time.time() - (phase_build.started_at.timestamp()
                                                       if phase_build.started_at else start_time)
        phases.append(phase_build)

        # ── Phase: packaging ──
        phase_pkg = BuildPhaseRecord(phase="packaging", status="running",
                                      started_at=datetime.now(timezone.utc))

        await _emit_progress(progress_cb, execution_id, "packaging", "running",
                             "Collecting build artifacts", 0.85)

        # Scan for typed artifacts
        resolved_dir = str(Path(project_dir).resolve()) if project_dir else os.getcwd()
        artifacts = _find_build_artifacts(resolved_dir)

        phase_pkg.status = "completed"
        phase_pkg.completed_at = datetime.now(timezone.utc)
        phases.append(phase_pkg)

        # ── Build result ──
        elapsed = time.time() - start_time
        failure_reason = None
        if not success:
            # Extract failure reason from build history
            history = list(_BUILD_LOOP._build_history.values()) if _BUILD_LOOP else []
            if history and history[0]:
                failure_reason = history[0][-1][:200] if history[0] else "Build failed"

        record = BuildExecutionRecord(
            execution_id=execution_id,
            goal=task,
            started_at=start_dt,
            completed_at=datetime.now(timezone.utc),
            success=success,
            status=goal_status,
            failure_reason=failure_reason,
            phases=phases,
            artifacts=artifacts,
            project_dir=resolved_dir,
            completion_pct=_BUILD_LOOP._completion if _BUILD_LOOP else 0.0,
            repair_cycles=_BUILD_LOOP._last_build_metrics.get("repair_cycles", 0) if _BUILD_LOOP else 0,
            repaired_errors=_BUILD_LOOP._last_build_metrics.get("repaired_errors", 0) if _BUILD_LOOP else 0,
            actual_duration_seconds=elapsed,
        )

        await _emit_progress(progress_cb, execution_id, "complete", "completed",
                             f"Build {'succeeded' if success else 'failed'} in {elapsed:.1f}s",
                             1.0)

    except asyncio.CancelledError:
        elapsed = time.time() - start_time
        record = BuildExecutionRecord(
            execution_id=execution_id,
            goal=task,
            started_at=start_dt,
            completed_at=datetime.now(timezone.utc),
            success=False,
            status="cancelled",
            failure_reason="Build cancelled",
            phases=phases,
            project_dir=project_dir,
            actual_duration_seconds=elapsed,
        )
        await _emit_progress(progress_cb, execution_id, "complete", "cancelled",
                             "Build cancelled", 1.0)

    except Exception as exc:
        elapsed = time.time() - start_time
        logger.exception("[AutoBuild] unexpected error: %s", exc)
        record = BuildExecutionRecord(
            execution_id=execution_id,
            goal=task,
            started_at=start_dt,
            completed_at=datetime.now(timezone.utc),
            success=False,
            status="failed",
            failure_reason=str(exc)[:200],
            phases=phases,
            project_dir=project_dir,
            actual_duration_seconds=elapsed,
        )
        await _emit_progress(progress_cb, execution_id, "complete", "failed",
                             f"Build error: {str(exc)[:100]}", 1.0)

    # ── Post-execution integration ─────────────────────────────

    # Record in ActivityGraph
    try:
        await _record_activity_nodes(record)
    except Exception as exc:
        logger.warning("[AutoBuild] ActivityGraph recording failed: %s", exc)

    # Record in CalibrationStore
    try:
        await _record_calibration(record)
    except Exception as exc:
        logger.warning("[AutoBuild] Calibration recording failed: %s", exc)

    # Feed into KnowledgeStore (requirement C)
    try:
        await _record_knowledge(record)
    except Exception as exc:
        logger.warning("[AutoBuild] KnowledgeStore recording failed: %s", exc)

    return record
