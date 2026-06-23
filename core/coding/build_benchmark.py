"""Phase 13.1 — Build Benchmarking & Promotion Framework.

Compares build_project vs automated_build on identical goals using:
  - ActivityGraph for structured recording
  - StrategyDecision for real predictions
  - CalibrationStore for prediction-vs-actual learning
  - KnowledgeStore for persistent learning

Promotion decision is a first-class entity in the ActivityGraph
with full lineage: StrategyDecision → BenchmarkRuns → Comparison → Decision.
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
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ── Models ────────────────────────────────────────────────────────


class BuildMethod(str, Enum):
    BUILD_PROJECT = "build_project"
    AUTOMATED_BUILD = "automated_build"


class PromotionAction(str, Enum):
    KEEP_BOTH = "keep_both"
    PROMOTE_AUTOMATED = "promote_automated"
    PROMOTE_BUILD_PROJECT = "promote_build_project"
    INCONCLUSIVE = "inconclusive"


@dataclass
class MetricComparison:
    """Comparison of a single metric between two build methods."""

    metric: str
    build_project_value: float
    automated_build_value: float
    automated_is_better: bool
    margin: float = 0.0  # absolute difference
    margin_pct: float = 0.0  # percentage difference
    is_tie: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric": self.metric,
            "build_project": round(self.build_project_value, 3),
            "automated_build": round(self.automated_build_value, 3),
            "automated_is_better": self.automated_is_better,
            "margin": round(self.margin, 3),
            "margin_pct": round(self.margin_pct, 1),
            "is_tie": self.is_tie,
        }


@dataclass
class BenchmarkRun:
    """Record of a single build execution in a benchmark comparison."""

    run_id: str
    goal: str
    method: BuildMethod
    strategy_decision_id: str

    success: bool
    status: str
    duration_seconds: float

    repair_cycles: int = 0
    repaired_errors: int = 0
    artifact_count: int = 0
    phases: list[dict] = field(default_factory=list)
    artifacts: list[dict] = field(default_factory=list)

    predicted_duration_days: float | None = None
    predicted_success: float | None = None

    activity_node_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "goal": self.goal[:100],
            "method": self.method.value,
            "strategy_decision_id": self.strategy_decision_id,
            "success": self.success,
            "status": self.status,
            "duration_seconds": round(self.duration_seconds, 1),
            "duration_days": round(self.duration_seconds / 86400.0, 2),
            "repair_cycles": self.repair_cycles,
            "repaired_errors": self.repaired_errors,
            "artifact_count": self.artifact_count,
            "predicted_duration_days": self.predicted_duration_days,
            "predicted_success": self.predicted_success,
            "activity_node_id": self.activity_node_id,
        }


@dataclass
class ComparisonResult:
    """Statistical comparison between build_project and automated_build."""

    metrics: list[MetricComparison] = field(default_factory=list)
    automated_wins: int = 0
    build_project_wins: int = 0

    overall_score: float = 0.0  # positive = automated_build better

    def to_dict(self) -> dict[str, Any]:
        return {
            "metrics": [m.to_dict() for m in self.metrics],
            "automated_wins": self.automated_wins,
            "build_project_wins": self.build_project_wins,
            "overall_score": round(self.overall_score, 3),
        }


@dataclass
class PromotionDecision:
    """The benchmark's conclusion — should automated_build replace build_project?"""

    action: PromotionAction
    confidence: float  # 0.0–1.0
    reasoning: str
    comparison: ComparisonResult | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action.value,
            "confidence": round(self.confidence, 3),
            "reasoning": self.reasoning,
            "comparison": self.comparison.to_dict() if self.comparison else None,
        }


@dataclass
class BenchmarkSession:
    """A complete benchmark session comparing two build methods on one goal."""

    session_id: str
    goal: str
    strategy_decision_id: str
    build_project_run: BenchmarkRun
    automated_build_run: BenchmarkRun
    comparison: ComparisonResult | None = None
    promotion_decision: PromotionDecision | None = None
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "goal": self.goal[:100],
            "strategy_decision_id": self.strategy_decision_id,
            "build_project": self.build_project_run.to_dict(),
            "automated_build": self.automated_build_run.to_dict(),
            "comparison": self.comparison.to_dict() if self.comparison else None,
            "promotion_decision": self.promotion_decision.to_dict()
                if self.promotion_decision else None,
            "started_at": self.started_at.isoformat(),
        }


# ── Strategy Decision Pipeline ───────────────────────────────────

async def get_strategy_prediction(goal: str, goal_type: str = "build"
                                  ) -> tuple[str, float, float]:
    """Create a StrategyDecision for a goal and return prediction values.

    Returns (decision_id, predicted_duration_days, predicted_success).

    This wires the benchmark to the real Phase 12 strategy pipeline
    so calibration learns from actual strategic predictions.
    """
    try:
        from core.strategy.generator import StrategyGenerator
        from core.strategy.predictor import OutcomePredictor
        from core.strategy.evaluator import StrategyEvaluator
        from core.strategy.selector import StrategySelector
        from core.strategy.memory_adapter import MemoryAdapter

        gen = StrategyGenerator()
        pred = OutcomePredictor()
        ev = StrategyEvaluator()
        sel = StrategySelector(evaluator=ev)
        mem = MemoryAdapter()

        # Generate → Predict → Evaluate → Select
        strategies = gen.generate(goal)
        pred.predict_all(strategies, goal_type, memory_adapter=mem)
        chosen, decision = sel.select(strategies)

        if chosen and chosen.prediction and decision:
            p = chosen.prediction
            return (decision.decision_id, p.estimated_duration_days,
                    p.success_probability)

        logger.debug("Strategy pipeline returned no prediction for %s", goal)
        return ("", 14.0, 0.75)

    except Exception as exc:
        logger.warning("Strategy pipeline unavailable: %s", exc)
        return ("", 14.0, 0.75)


# ── Comparison Logic ─────────────────────────────────────────────

def _compare_metric(name: str, a_val: float, b_val: float,
                    higher_is_better: bool) -> MetricComparison:
    """Compare a single metric between two approaches."""
    margin = b_val - a_val
    margin_pct = (margin / a_val * 100.0) if a_val != 0 else 0.0
    is_tie = a_val == b_val
    if is_tie:
        automated_is_better = False
    elif higher_is_better:
        automated_is_better = b_val > a_val
    else:
        automated_is_better = b_val < a_val
    return MetricComparison(
        metric=name,
        build_project_value=a_val,
        automated_build_value=b_val,
        automated_is_better=automated_is_better,
        margin=abs(margin),
        margin_pct=abs(margin_pct),
        is_tie=is_tie,
    )


def compute_comparison(bp_run: BenchmarkRun, ab_run: BenchmarkRun
                       ) -> ComparisonResult:
    """Compare build_project vs automated_build metrics."""
    metrics = [
        _compare_metric("success", 1.0 if bp_run.success else 0.0,
                        1.0 if ab_run.success else 0.0,
                        higher_is_better=True),
        _compare_metric("duration_seconds", bp_run.duration_seconds,
                        ab_run.duration_seconds,
                        higher_is_better=False),
        _compare_metric("repair_cycles", bp_run.repair_cycles,
                        ab_run.repair_cycles,
                        higher_is_better=False),
        _compare_metric("artifact_count", bp_run.artifact_count,
                        ab_run.artifact_count,
                        higher_is_better=True),
    ]

    automated_wins = sum(1 for m in metrics if m.automated_is_better and not m.is_tie)
    bp_wins = sum(1 for m in metrics if not m.automated_is_better and not m.is_tie)

    # Overall score: weighted sum of margins (success +0.4, duration +0.3,
    # repair +0.2, artifacts +0.1). Positive = automated_build better.
    overall = 0.0
    for m in metrics:
        weight = {
            "success": 0.40,
            "duration_seconds": 0.30,
            "repair_cycles": 0.20,
            "artifact_count": 0.10,
        }.get(m.metric, 0.25)
        if m.is_tie:
            continue
        direction = 1.0 if m.automated_is_better else -1.0
        magnitude = min(abs(m.margin_pct) / 100.0, 1.0)
        overall += direction * magnitude * weight

    return ComparisonResult(
        metrics=metrics,
        automated_wins=automated_wins,
        build_project_wins=bp_wins,
        overall_score=round(overall, 3),
    )


# ── Promotion Decision Logic ────────────────────────────────────

def decide_promotion(comparison: ComparisonResult, bp_run: BenchmarkRun,
                     ab_run: BenchmarkRun) -> PromotionDecision:
    """Decide whether to promote automated_build over build_project.

    Decision rules:
      1. If overall_score > 0.2 + confidence bonus → PROMOTE_AUTOMATED
      2. If overall_score < -0.2 → PROMOTE_BUILD_PROJECT
      3. If comparison inconclusive → INCONCLUSIVE
      4. Otherwise → KEEP_BOTH
    """
    # Bonus for automated_build: it has repair capability + richer artifacts
    capability_bonus = 0.05

    adjusted_score = comparison.overall_score + capability_bonus

    if adjusted_score > 0.2:
        confidence = min(abs(adjusted_score), 0.95)
        reasoning = (
            f"automated_build outperforms build_project "
            f"(score={adjusted_score:.3f}): "
            f"wins {comparison.automated_wins}/{len(comparison.metrics)} metrics"
        )
        return PromotionDecision(
            action=PromotionAction.PROMOTE_AUTOMATED,
            confidence=round(confidence, 3),
            reasoning=reasoning,
            comparison=comparison,
        )

    if adjusted_score < -0.2:
        confidence = min(abs(adjusted_score), 0.95)
        reasoning = (
            f"build_project outperforms automated_build "
            f"(score={adjusted_score:.3f})"
        )
        return PromotionDecision(
            action=PromotionAction.PROMOTE_BUILD_PROJECT,
            confidence=round(confidence, 3),
            reasoning=reasoning,
            comparison=comparison,
        )

    if abs(adjusted_score) < 0.05:
        reasoning = (
            f"Comparison inconclusive: scores are nearly identical "
            f"(score={adjusted_score:.3f})"
        )
        return PromotionDecision(
            action=PromotionAction.INCONCLUSIVE,
            confidence=0.3,
            reasoning=reasoning,
            comparison=comparison,
        )

    reasoning = (
        f"Both methods comparable (score={adjusted_score:.3f}), "
        f"keeping both active"
    )
    return PromotionDecision(
        action=PromotionAction.KEEP_BOTH,
        confidence=0.5,
        reasoning=reasoning,
        comparison=comparison,
    )


# ── ActivityGraph Recording ──────────────────────────────────────

async def _record_benchmark_graph(session: BenchmarkSession) -> None:
    """Record the full benchmark session in ActivityGraph.

    Lineage:
      benchmark_session
        ├── strategy_decision
        ├── build_project_run (benchmark_run)
        │     └── phase nodes + artifact nodes
        ├── automated_build_run (benchmark_run)
        │     └── phase nodes + artifact nodes
        ├── comparison_result
        └── promotion_decision
    """
    try:
        from core.activity.models import ActivityNode, ActivityStatus
        from core.activity.storage import ActivityStore
    except ImportError:
        logger.debug("ActivityStore not available")
        return

    store = ActivityStore()
    now = datetime.now(timezone.utc)
    sid = session.session_id

    # ── Parent: benchmark_session ──
    parent = ActivityNode(
        node_id=f"bm_{sid}",
        activity_id=f"bm_{sid}",
        node_type="benchmark_session",
        label=f"Benchmark: {session.goal[:100]}",
        status=ActivityStatus.COMPLETED,
        metadata={"session_id": sid, "goal": session.goal[:200]},
        started_at=session.started_at,
        completed_at=now,
    )
    try:
        store.create_node(parent)
    except Exception as exc:
        logger.debug("ActivityStore: failed to create benchmark parent: %s", exc)
        return

    # ── Strategy Decision ──
    sd_node = ActivityNode(
        node_id=f"bm_{sid}_strategy",
        activity_id=f"bm_{sid}",
        node_type="strategy_decision",
        label=f"Strategy: {session.goal[:80]}",
        status=ActivityStatus.COMPLETED,
        depth=1,
        parent_id=parent.node_id,
        metadata={"strategy_decision_id": session.strategy_decision_id},
    )
    _safe_create(store, sd_node)

    # ── Build runs ──
    for run in (session.build_project_run, session.automated_build_run):
        run_status = ActivityStatus.COMPLETED if run.success else ActivityStatus.FAILED
        run_node = ActivityNode(
            node_id=f"bm_{sid}_{run.method.value}",
            activity_id=f"bm_{sid}",
            node_type="benchmark_run",
            label=f"{run.method.value}: {run.goal[:60]}",
            status=run_status,
            depth=1,
            parent_id=parent.node_id,
            metadata={
                "method": run.method.value,
                "run_id": run.run_id,
                "strategy_decision_id": run.strategy_decision_id,
            },
            started_at=session.started_at,
            completed_at=now,
        )
        _safe_create(store, run_node)

        # Artifact nodes under each run
        for art in run.artifacts:
            art_node = ActivityNode(
                node_id=f"bm_{sid}_{run.method.value}_artifact_{art.get('type', 'unknown')}",
                activity_id=f"bm_{sid}",
                node_type="artifact",
                label=f"{art.get('type', 'file')}: {art.get('path', '')[:60]}",
                status=ActivityStatus.COMPLETED,
                depth=2,
                parent_id=run_node.node_id,
                metadata={
                    "artifact_type": art.get("type", "unknown"),
                    "path": art.get("path", ""),
                    "run_id": run.run_id,
                },
            )
            _safe_create(store, art_node)

    # ── Comparison Result ──
    if session.comparison:
        comp_node = ActivityNode(
            node_id=f"bm_{sid}_comparison",
            activity_id=f"bm_{sid}",
            node_type="comparison_result",
            label=f"Comparison: {session.goal[:60]}",
            status=ActivityStatus.COMPLETED,
            depth=1,
            parent_id=parent.node_id,
            metadata={
                "overall_score": session.comparison.overall_score,
                "automated_wins": session.comparison.automated_wins,
                "build_project_wins": session.comparison.build_project_wins,
                "metrics": [m.to_dict() for m in session.comparison.metrics],
            },
        )
        _safe_create(store, comp_node)

    # ── Promotion Decision ──
    if session.promotion_decision:
        pd = session.promotion_decision
        promo_node = ActivityNode(
            node_id=f"bm_{sid}_promotion",
            activity_id=f"bm_{sid}",
            node_type="promotion_decision",
            label=f"Promotion: {pd.action.value} ({pd.confidence:.0%})",
            status=ActivityStatus.COMPLETED,
            depth=1,
            parent_id=parent.node_id,
            metadata={
                "action": pd.action.value,
                "confidence": pd.confidence,
                "reasoning": pd.reasoning,
            },
        )
        _safe_create(store, promo_node)


def _safe_create(store, node: Any) -> None:
    try:
        store.create_node(node)
    except Exception as exc:
        logger.debug("ActivityStore: create_node failed for %s: %s",
                     node.node_id, exc)


# ── Calibration Recording ────────────────────────────────────────

async def _record_benchmark_calibration(session: BenchmarkSession) -> None:
    """Record both runs as calibration data with the strategy prediction."""
    try:
        from core.strategy.calibration import PredictionCalibrator
        from core.strategy.models import Prediction, Strategy, StrategyDecision, StrategyTag
    except ImportError:
        logger.debug("Calibration not available")
        return

    calibrator = PredictionCalibrator()

    for run in (session.build_project_run, session.automated_build_run):
        duration_days = run.duration_seconds / 86400.0 if run.duration_seconds > 0 else 0.01

        strategy = Strategy(
            name=run.method.value,
            description=f"Benchmark run: {run.method.value}",
            goal=run.goal,
            tags=[StrategyTag.ITERATIVE],
            prediction=Prediction(
                success_probability=run.predicted_success or 0.75,
                estimated_duration_days=run.predicted_duration_days or duration_days,
                estimated_risk=0.3,
                estimated_effort=5.0,
                confidence=0.3,
            ),
        )

        decision = StrategyDecision(
            decision_id=f"bm_cal_{run.run_id}",
            goal=run.goal,
            timestamp=datetime.now(timezone.utc),
            strategies_considered=[strategy],
            chosen_strategy=strategy,
            confidence=0.3,
        )

        try:
            calibrator.store.record(
                decision, "build",
                actual_success=run.success,
                actual_duration_days=duration_days,
            )
            logger.debug("Calibration recorded for %s (success=%s, duration=%.1fd)",
                         run.run_id, run.success, duration_days)
        except Exception as exc:
            logger.debug("Calibration record failed for %s: %s", run.run_id, exc)


# ── KnowledgeStore Recording ────────────────────────────────────

async def _record_benchmark_knowledge(session: BenchmarkSession) -> None:
    """Feed build outcomes into KnowledgeStore via ExperienceExtractor."""
    try:
        from core.activity.manager import ActivityManager
        from core.activity.storage import ActivityStore
        from core.long_term_memory.extractor import ExperienceExtractor
        from core.long_term_memory.store import KnowledgeStore
    except ImportError:
        logger.debug("KnowledgeStore not available")
        return

    try:
        store = ActivityStore()
        mgr = ActivityManager(store)
        ks = KnowledgeStore()
        extractor = ExperienceExtractor(mgr, ks)

        sid = session.session_id
        extractor.extract(f"bm_{sid}")
        extractor.extract(f"bm_{sid}_strategy")

        logger.debug("KnowledgeStore updated from benchmark session %s", sid)
    except Exception as exc:
        logger.debug("KnowledgeStore recording failed: %s", exc)


# ── Main Benchmark Entry Point ──────────────────────────────────

async def run_benchmark(goal: str, project_dir: str,
                        goal_type: str = "build",
                        run_automated: bool = True,
                        run_traditional: bool = True
                        ) -> BenchmarkSession:
    """Run a complete benchmark comparison between build methods.

    Args:
        goal: The build goal (e.g., "Build Android coffee shop app")
        project_dir: Working directory for the project
        goal_type: Type for strategy prediction
        run_automated: If True, run automated_build comparison
        run_traditional: If True, run build_project comparison

    Returns:
        BenchmarkSession with runs, comparison, and promotion decision.
    """
    from uuid import uuid4
    session_id = uuid4().hex[:12]
    resolved_dir = str(Path(project_dir).resolve()) if project_dir else os.getcwd()

    logger.info("[Benchmark] session=%s goal=%s", session_id, goal[:80])

    # 1. Get strategy prediction
    decision_id, pred_dur, pred_sp = await get_strategy_prediction(goal, goal_type)

    runs: list[BenchmarkRun] = []

    # 2. Run build_project
    if run_traditional:
        bp_run = await _run_single_benchmark(
            goal, resolved_dir, BuildMethod.BUILD_PROJECT,
            decision_id, pred_dur, pred_sp, session_id,
        )
        runs.append(bp_run)
    else:
        bp_run = None

    # 3. Run automated_build
    if run_automated:
        ab_run = await _run_single_benchmark(
            goal, resolved_dir, BuildMethod.AUTOMATED_BUILD,
            decision_id, pred_dur, pred_sp, session_id,
        )
        runs.append(ab_run)
    else:
        ab_run = None

    # 4. Compare
    comparison = None
    promotion_decision = None
    if bp_run and ab_run:
        comparison = compute_comparison(bp_run, ab_run)
        promotion_decision = decide_promotion(comparison, bp_run, ab_run)

        logger.info(
            "[Benchmark] comparison: automated=%d/%d wins, "
            "score=%+.3f → %s",
            comparison.automated_wins, len(comparison.metrics),
            comparison.overall_score,
            promotion_decision.action.value,
        )

    session = BenchmarkSession(
        session_id=session_id,
        goal=goal,
        strategy_decision_id=decision_id,
        build_project_run=bp_run,
        automated_build_run=ab_run,
        comparison=comparison,
        promotion_decision=promotion_decision,
        completed_at=datetime.now(timezone.utc),
    )

    # 5. Record in ActivityGraph
    try:
        await _record_benchmark_graph(session)
    except Exception as exc:
        logger.warning("[Benchmark] ActivityGraph recording failed: %s", exc)

    # 6. Record in CalibrationStore
    try:
        await _record_benchmark_calibration(session)
    except Exception as exc:
        logger.warning("[Benchmark] Calibration recording failed: %s", exc)

    # 7. Feed into KnowledgeStore
    try:
        await _record_benchmark_knowledge(session)
    except Exception as exc:
        logger.warning("[Benchmark] KnowledgeStore feed failed: %s", exc)

    return session


async def _run_single_benchmark(
    goal: str, project_dir: str, method: BuildMethod,
    decision_id: str, pred_dur: float, pred_sp: float,
    session_id: str,
) -> BenchmarkRun:
    """Execute a single benchmark run and return structured results."""
    from uuid import uuid4
    run_id = uuid4().hex[:12]
    start = time.time()

    logger.info("[Benchmark] run=%s method=%s goal=%s",
                run_id, method.value, goal[:60])

    if method == BuildMethod.BUILD_PROJECT:
        from core.tools.build_tools import do_build_project
        result = await do_build_project(goal, project_dir)
        run = _to_benchmark_run(
            run_id, goal, method, result, decision_id, pred_dur, pred_sp,
        )
    else:
        from core.tools.automated_build import do_automated_build
        record = await do_automated_build(goal, project_dir)
        run = BenchmarkRun(
            run_id=run_id,
            goal=goal,
            method=method,
            strategy_decision_id=decision_id,
            success=record.success,
            status=record.status,
            duration_seconds=record.actual_duration_seconds,
            repair_cycles=record.repair_cycles,
            repaired_errors=record.repaired_errors,
            artifact_count=len(record.artifacts),
            phases=[p.__dict__ for p in record.phases],
            artifacts=record.artifacts,
            predicted_duration_days=pred_dur,
            predicted_success=pred_sp,
        )

    elapsed = round(time.time() - start, 1)
    logger.info("[Benchmark] run=%s completed: success=%s duration=%.1fs",
                run_id, run.success, elapsed)
    return run


def _to_benchmark_run(
    run_id: str, goal: str, method: BuildMethod,
    result: dict, decision_id: str,
    pred_dur: float, pred_sp: float,
) -> BenchmarkRun:
    """Convert a do_build_project result dict to BenchmarkRun."""
    artifacts_raw = result.get("_artifacts", {})
    artifact_list = [
        {"type": v.split(".")[-1] if "." in str(v) else "unknown", "path": str(v)}
        for v in artifacts_raw.values()
    ] if isinstance(artifacts_raw, dict) else []

    return BenchmarkRun(
        run_id=run_id,
        goal=goal,
        method=method,
        strategy_decision_id=decision_id,
        success=result.get("success", False),
        status=result.get("status", "unknown"),
        duration_seconds=result.get("elapsed_s", 0.0),
        repair_cycles=0,
        repaired_errors=0,
        artifact_count=len(artifact_list),
        artifacts=artifact_list,
        predicted_duration_days=pred_dur,
        predicted_success=pred_sp,
    )
