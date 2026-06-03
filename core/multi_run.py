"""core/multi_run.py
Multi-run / Best-of-N executor.
Runs multiple strategies in parallel, scores each, picks the best result.
"""
import asyncio, logging, copy
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Callable
from datetime import datetime

logger = logging.getLogger(__name__)

from core.control_loop import ControlLoop
from core.quality_scorer import QualityScorer, ScoreBreakdown


@dataclass
class StrategyVariant:
    name: str
    goal_modifier: str
    template_preference: Optional[str] = None
    style: Optional[str] = None
    tech_override: Optional[list[str]] = None


DEFAULT_STRATEGIES = [
    StrategyVariant("template_heavy", "", template_preference="best_match"),
    StrategyVariant("minimal_custom", "keep it minimal, single page", style="modern_minimal", tech_override=["html", "css"]),
    StrategyVariant("full_featured", "full featured with all pages", style="business"),
]


@dataclass
class RunResult:
    strategy: str
    project_name: str
    state: dict
    score: Optional[ScoreBreakdown] = None
    duration: float = 0.0
    success: bool = False
    deploy_url: str = ""


class MultiRunExecutor:
    def __init__(self, max_parallel: int = 3):
        self.max_parallel = max_parallel
        self.results: list[RunResult] = []

    async def execute(
        self,
        goal: str,
        strategies: list[StrategyVariant] = None,
        workspace_base: str = "",
        progress_callback: Optional[Callable] = None,
    ) -> RunResult:
        strategies = strategies or DEFAULT_STRATEGIES
        active = min(len(strategies), self.max_parallel)

        logger.info(f"[MULTIRUN] Starting {len(strategies)} strategies ({active} parallel)")

        score_results = []
        sem = asyncio.Semaphore(active)

        async def run_strategy(sv: StrategyVariant) -> RunResult:
            async with sem:
                start = datetime.now()
                variant_goal = goal
                if sv.goal_modifier:
                    variant_goal = f"{goal}, {sv.goal_modifier}" if "with" not in sv.goal_modifier else sv.goal_modifier

                safe_name = f"multirun_{sv.name}_{int(start.timestamp())}"
                ws = Path(workspace_base) / safe_name if workspace_base else Path.cwd() / safe_name

                cl = ControlLoop(auto_approve=True)
                try:
                    state = await cl.run_build(variant_goal, str(ws))
                    scorer = QualityScorer(str(ws))
                    score = scorer.score_all(safe_name)
                    duration = (datetime.now() - start).total_seconds()

                    result = RunResult(
                        strategy=sv.name,
                        project_name=safe_name,
                        state={"status": state.status, "pages": state.pages, "retries": state.retries},
                        score=score,
                        duration=duration,
                        success=state.status == "done",
                        deploy_url=state.outputs.get("deploy_url", "") if hasattr(state, "outputs") else "",
                    )
                    score_results.append(result)
                    logger.info(f"[MULTIRUN] {sv.name}: score={score.average:.1f} status={state.status} {duration:.0f}s")

                    if progress_callback:
                        await progress_callback(sv.name, score, state)

                    return result
                except Exception as e:
                    logger.error(f"[MULTIRUN] {sv.name} failed: {e}")
                    result = RunResult(strategy=sv.name, project_name=safe_name, state={}, duration=0, success=False)
                    score_results.append(result)
                    return result

        tasks = [asyncio.create_task(run_strategy(sv)) for sv in strategies]
        await asyncio.gather(*tasks, return_exceptions=True)

        self.results = score_results
        best = self.pick_best()
        logger.info(f"[MULTIRUN] Best: {best.strategy} (score={best.score.average:.1f})" if best.score else f"[MULTIRUN] Best: {best.strategy} (no score)")
        return best

    def pick_best(self) -> Optional[RunResult]:
        scored = [r for r in self.results if r.score and r.success]
        if not scored:
            if self.results:
                return self.results[0]
            return None
        scored.sort(key=lambda r: r.score.total if r.score else 0, reverse=True)
        return scored[0]

    def summary(self) -> str:
        lines = [f"Multi-Run: {len(self.results)} strategies"]
        for r in sorted(self.results, key=lambda x: x.score.average if x.score else 0, reverse=True):
            score_str = f"{r.score.average:.1f}/10" if r.score else "N/A"
            lines.append(f"  {r.strategy}: {score_str} {'✅' if r.success else '❌'} {r.duration:.0f}s")
        return "\n".join(lines)


multi_run = MultiRunExecutor()
