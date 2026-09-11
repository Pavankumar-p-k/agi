"""Build benchmark and promotion framework for coding workflows."""
from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class BuildMethod(str, Enum):
    BUILD_PROJECT = "build_project"
    AUTOMATED_BUILD = "automated_build"


class PromotionAction(str, Enum):
    PROMOTE_AUTOMATED = "promote_automated"
    PROMOTE_BUILD_PROJECT = "promote_build_project"
    KEEP_BOTH = "keep_both"
    INCONCLUSIVE = "inconclusive"


@dataclass
class BenchmarkRun:
    run_id: str
    goal: str
    method: BuildMethod | str
    strategy_decision_id: str
    success: bool
    status: str
    duration_seconds: float
    repair_cycles: int = 0
    repaired_errors: int = 0
    artifact_count: int = 0
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    predicted_duration_days: float | None = None
    predicted_success: float | None = None
    failure_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.method, BuildMethod):
            self.method = BuildMethod(str(self.method))
        if self.artifacts and not self.artifact_count:
            self.artifact_count = len(self.artifacts)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["method"] = self.method.value
        data["duration_days"] = self.duration_seconds / 86400.0
        return data


@dataclass
class MetricComparison:
    metric: str
    build_project_value: float
    automated_build_value: float
    automated_is_better: bool
    margin: float
    margin_pct: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ComparisonResult:
    metrics: list[MetricComparison] = field(default_factory=list)
    automated_wins: int = 0
    build_project_wins: int = 0
    overall_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "metrics": [metric.to_dict() for metric in self.metrics],
            "automated_wins": self.automated_wins,
            "build_project_wins": self.build_project_wins,
            "overall_score": self.overall_score,
        }


@dataclass
class PromotionDecision:
    action: PromotionAction | str
    confidence: float
    reasoning: str
    comparison: ComparisonResult | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.action, PromotionAction):
            self.action = PromotionAction(str(self.action))

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action.value,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "comparison": self.comparison.to_dict() if self.comparison else None,
        }


@dataclass
class BenchmarkSession:
    session_id: str
    goal: str
    strategy_decision_id: str
    build_project_run: BenchmarkRun
    automated_build_run: BenchmarkRun
    comparison: ComparisonResult | None = None
    promotion_decision: PromotionDecision | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "goal": self.goal,
            "strategy_decision_id": self.strategy_decision_id,
            "build_project": self.build_project_run.to_dict(),
            "automated_build": self.automated_build_run.to_dict(),
            "comparison": self.comparison.to_dict() if self.comparison else None,
            "promotion_decision": self.promotion_decision.to_dict() if self.promotion_decision else None,
        }


def _pct_margin(base: float, other: float) -> float:
    return abs(base - other) / max(abs(base), 1.0) * 100.0


def compute_comparison(build_project_run: BenchmarkRun, automated_build_run: BenchmarkRun) -> ComparisonResult:
    metrics: list[MetricComparison] = []
    auto_wins = 0
    bp_wins = 0
    score = 0.0

    comparisons = [
        ("success", float(build_project_run.success), float(automated_build_run.success), automated_build_run.success >= build_project_run.success, 0.45),
        ("duration_seconds", build_project_run.duration_seconds, automated_build_run.duration_seconds, automated_build_run.duration_seconds <= build_project_run.duration_seconds, 0.25),
        ("repair_cycles", float(build_project_run.repair_cycles), float(automated_build_run.repair_cycles), automated_build_run.repair_cycles <= build_project_run.repair_cycles, 0.15),
        ("artifact_count", float(build_project_run.artifact_count), float(automated_build_run.artifact_count), automated_build_run.artifact_count >= build_project_run.artifact_count, 0.15),
    ]
    for name, bp_value, auto_value, auto_better, weight in comparisons:
        if bp_value == auto_value:
            margin = 0.0
            margin_pct = 0.0
        else:
            margin = abs(bp_value - auto_value)
            margin_pct = _pct_margin(bp_value, auto_value)
        metrics.append(MetricComparison(name, bp_value, auto_value, auto_better, margin, margin_pct))
        contribution = weight
        if name == "duration_seconds":
            contribution = weight * min(1.0, margin_pct / 100.0)
        if auto_better and bp_value != auto_value:
            auto_wins += 1
            score += contribution
        elif not auto_better and bp_value != auto_value:
            bp_wins += 1
            score -= contribution
    return ComparisonResult(metrics, auto_wins, bp_wins, round(score, 3))


async def async_compute_comparison(*args, **kwargs) -> ComparisonResult:
    return compute_comparison(*args, **kwargs)


def decide_promotion(comparison: ComparisonResult, build_project_run: BenchmarkRun, automated_build_run: BenchmarkRun) -> PromotionDecision:
    adjusted = comparison.overall_score + 0.05
    if abs(adjusted) < 0.05:
        return PromotionDecision(PromotionAction.INCONCLUSIVE, 0.3, "Benchmark scores are too close to promote either path", comparison)
    if adjusted >= 0.25:
        return PromotionDecision(PromotionAction.PROMOTE_AUTOMATED, min(0.95, 0.55 + abs(adjusted)), "automated_build outperformed build_project on benchmark metrics", comparison)
    if adjusted <= -0.25:
        return PromotionDecision(PromotionAction.PROMOTE_BUILD_PROJECT, min(0.95, 0.55 + abs(adjusted)), "build_project outperformed automated_build on benchmark metrics", comparison)
    return PromotionDecision(PromotionAction.KEEP_BOTH, 0.45, "Both build paths remain useful based on this benchmark", comparison)


async def async_decide_promotion(*args, **kwargs) -> PromotionDecision:
    return decide_promotion(*args, **kwargs)


async def get_strategy_prediction(goal: str) -> tuple[str, float, float]:
    try:
        from core.strategy.generator import StrategyGenerator
        from core.strategy.predictor import OutcomePredictor
        from core.strategy.selector import StrategySelector

        strategies = StrategyGenerator().generate(goal)
        predicted = OutcomePredictor().predict_all(strategies)
        chosen, decision = StrategySelector().select(goal, predicted)
        prediction = chosen.prediction if chosen else None
        return (
            decision.decision_id,
            getattr(prediction, "estimated_duration_days", 7.0) if prediction else 7.0,
            getattr(prediction, "success_probability", 0.5) if prediction else 0.5,
        )
    except Exception:
        return ("default_strategy", 7.0, 0.5)


async def async_get_strategy_prediction(*args, **kwargs):
    return await get_strategy_prediction(*args, **kwargs)


async def _record_benchmark_graph(session: BenchmarkSession) -> None:
    try:
        from core.activity.models import ActivityNode
        from core.activity.storage import ActivityStore

        store = ActivityStore()
        nodes = [
            ActivityNode(node_type="benchmark_session", label=session.goal, output=session.to_dict()),
            ActivityNode(node_type="benchmark_run", label="build_project", output=session.build_project_run.to_dict()),
            ActivityNode(node_type="benchmark_run", label="automated_build", output=session.automated_build_run.to_dict()),
        ]
        if session.promotion_decision:
            nodes.append(ActivityNode(node_type="promotion_decision", label=session.promotion_decision.action.value, output=session.promotion_decision.to_dict()))
        for artifact in session.build_project_run.artifacts + session.automated_build_run.artifacts:
            nodes.append(ActivityNode(node_type="artifact", label=str(artifact.get("path", artifact)), output=artifact))
        for node in nodes:
            store.create_node(node)
    except Exception:
        return None


async def _record_benchmark_calibration(session: BenchmarkSession) -> None:
    try:
        from core.strategy.calibration import PredictionCalibrator

        calibrator = PredictionCalibrator()
        record = getattr(calibrator, "record", None)
        if callable(record):
            record(session.to_dict())
    except Exception:
        return None


async def _record_benchmark_knowledge(session: BenchmarkSession) -> None:
    try:
        from memory.task_store import TaskStore

        TaskStore().store(
            action_name="coding_build_benchmark",
            action_params={"goal": session.goal},
            observation=str(session.to_dict())[:1000],
            success=bool(session.promotion_decision),
            task_id=session.session_id,
            tags=["coding", "benchmark"],
        )
    except Exception:
        return None


def _run_from_build_project(result: dict[str, Any], goal: str, strategy_id: str) -> BenchmarkRun:
    artifacts = result.get("artifacts") or []
    return BenchmarkRun(
        run_id=uuid.uuid4().hex,
        goal=goal,
        method=BuildMethod.BUILD_PROJECT,
        strategy_decision_id=strategy_id,
        success=bool(result.get("success")),
        status=str(result.get("status", "unknown")),
        duration_seconds=float(result.get("elapsed_s", result.get("duration_seconds", 0.0))),
        repair_cycles=int(result.get("repair_cycles", 0)),
        repaired_errors=int(result.get("repaired_errors", 0)),
        artifact_count=len(artifacts),
        artifacts=artifacts,
    )


def _run_from_automated(record: Any, goal: str, strategy_id: str) -> BenchmarkRun:
    artifacts = list(getattr(record, "artifacts", []) or [])
    return BenchmarkRun(
        run_id=str(getattr(record, "execution_id", uuid.uuid4().hex)),
        goal=goal,
        method=BuildMethod.AUTOMATED_BUILD,
        strategy_decision_id=strategy_id,
        success=bool(getattr(record, "success", False)),
        status=str(getattr(record, "status", "unknown")),
        duration_seconds=float(getattr(record, "actual_duration_seconds", 0.0) or 0.0),
        artifact_count=len(artifacts),
        artifacts=artifacts,
        failure_reason=getattr(record, "failure_reason", None),
    )


async def run_benchmark(goal: str, project_dir: str | None = None) -> BenchmarkSession:
    strategy_id, predicted_duration, predicted_success = await get_strategy_prediction(goal)
    from core.tools.automated_build import do_automated_build
    from core.tools.build_tools import do_build_project

    start = time.time()
    bp_result = do_build_project(goal=goal, project_dir=project_dir)
    if bp_result is None:
        bp_result = {"success": False, "status": "failed", "elapsed_s": time.time() - start}
    bp_run = _run_from_build_project(bp_result, goal, strategy_id)
    bp_run.predicted_duration_days = predicted_duration
    bp_run.predicted_success = predicted_success

    ab_record = do_automated_build(goal=goal, project_dir=project_dir)
    ab_run = _run_from_automated(ab_record, goal, strategy_id)
    ab_run.predicted_duration_days = predicted_duration
    ab_run.predicted_success = predicted_success

    comparison = compute_comparison(bp_run, ab_run)
    decision = decide_promotion(comparison, bp_run, ab_run)
    session = BenchmarkSession(uuid.uuid4().hex, goal, strategy_id, bp_run, ab_run, comparison, decision)
    await _record_benchmark_graph(session)
    await _record_benchmark_calibration(session)
    await _record_benchmark_knowledge(session)
    return session


async def async_run_benchmark(*args, **kwargs) -> BenchmarkSession:
    return await run_benchmark(*args, **kwargs)
