"""Multi-provider orchestrator: executes plans with verification and replanning.

Completed from the committed contracts in tests/unit/test_orchestration.py
(TestOrchestrator, TestOrchestratorReplanning, consensus) and
tests/unit/test_provider_feedback.py (feedback loop: every executed attempt
records a decision + outcome through the existing feedback store).

Bounded execution: each plan step gets an initial attempt plus a limited
number of replans (alternative provider → capability substitution → abort).
No infinite retry loops.
"""
from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Any, Optional

from core.providers.orchestration.adapt import AdaptEngine, ReplanLevel
from core.providers.orchestration.models import (
    ChainType,
    OrchestrationPlan,
    OrchestrationResult,
    ProviderStep,
    StepResult,
    typed_artifact_from,
)

logger = logging.getLogger(__name__)

# Initial attempt + this many replans per step (bounded, no infinite loops).
_MAX_ATTEMPTS_PER_STEP = 3


class Orchestrator:
    """Executes an OrchestrationPlan against the registered providers."""

    def __init__(
        self,
        registry: Any = None,
        adapt_engine: Optional[AdaptEngine] = None,
    ) -> None:
        # Eagerly bind the global registry when none is injected (tests and
        # callers may access ``_registry`` directly after construction).
        if registry is None:
            try:
                from core.providers.registry import provider_registry
                registry = provider_registry
            except Exception as exc:
                logger.debug("[orchestrator] registry unavailable: %s", exc)
        self._registry = registry
        self._adapt = adapt_engine or AdaptEngine()
        self._feedback: Optional[dict[str, Any]] = None

    # ── Infrastructure resolution ───────────────────────────────────────────

    def _get_registry(self) -> Any:
        if self._registry is not None:
            return self._registry
        try:
            from core.providers.registry import provider_registry
            return provider_registry
        except Exception as exc:
            logger.debug("[orchestrator] registry unavailable: %s", exc)
            return None

    def _get_feedback(self) -> Optional[dict[str, Any]]:
        """Lazy feedback loop (recorder + calibrator) over the existing store."""
        if self._feedback is not None:
            return self._feedback
        try:
            from core.constants import DATA_DIR
            from core.providers.feedback.calibrator import CalibrationEngine
            from core.providers.feedback.recorder import DecisionRecorder
            from core.providers.feedback.store import FeedbackStore
            db_path = str(Path(DATA_DIR) / "orchestration_feedback.db")
            store = FeedbackStore(db_path=db_path)
            self._feedback = {
                "store": store,
                "recorder": DecisionRecorder(store),
                "calibrator": CalibrationEngine(store=store),
            }
            return self._feedback
        except Exception as exc:
            logger.debug("[orchestrator] feedback loop unavailable: %s", exc)
            self._feedback = {}
            return None

    # ── Execution ───────────────────────────────────────────────────────────

    async def execute(self, plan: OrchestrationPlan) -> OrchestrationResult:
        # Ensure default providers exist so the replan ladder always has a
        # live alternative (bootstrap is idempotent and never raises).
        try:
            from core.providers.bootstrap import bootstrap_providers
            bootstrap_providers()
        except Exception as exc:
            logger.debug("[orchestrator] provider bootstrap unavailable: %s", exc)
        result = OrchestrationResult(plan=plan)
        result.start_time = time.time()
        completed: set[str] = set()
        last_output = ""

        for step in plan.steps:
            if not step.is_ready(completed):
                result.step_results.append(
                    StepResult(
                        step_id=step.step_id,
                        provider_id=step.provider_id,
                        chain_type=step.chain_type,
                        success=False,
                        error="skipped: dependencies not completed",
                    )
                )
                continue
            step_output = await self._execute_step_chain(plan, step, result, last_output)
            # Consensus steps merge at the end; their outputs still complete.
            completed.add(step.step_id)
            if step_output:
                last_output = step_output

        # A step's outcome is its FINAL attempt (replan retries supersede the
        # failed first try); attempts keep their records for evidence.
        # Group by replan_of (the root step id): first-try attempts have
        # step_id == replan_of, retries carry a cloned step_id.
        final_by_step: dict[str, bool] = {}
        for r in result.step_results:
            key = r.replan_of or r.step_id
            final_by_step[key] = r.success
        result.overall_success = all(final_by_step.values())  # empty plan -> True
        result.end_time = time.time()
        return result

    async def _execute_step_chain(
        self,
        plan: OrchestrationPlan,
        step: ProviderStep,
        result: OrchestrationResult,
        last_output: str,
    ) -> str:
        """Run one plan step with bounded replanning; every attempt is recorded."""
        base_id = step.step_id  # root id — retries clone ids but keep this
        attempted: set[str] = set()
        current = step
        replan_level: Optional[ReplanLevel] = None

        for attempt_index in range(_MAX_ATTEMPTS_PER_STEP):
            outcome = await self._attempt(
                current, replan_level, len(attempted), last_output, base_id
            )
            result.step_results.append(outcome)
            if outcome.success:
                return outcome.output
            attempted.add(current.provider_id)
            if attempt_index == _MAX_ATTEMPTS_PER_STEP - 1:
                return ""
            level, new_step = self._adapt.create_replan(
                plan, current, outcome.error or "step failed", attempted
            )
            if level == ReplanLevel.ABORT or new_step is None:
                return ""
            replan_level = level
            current = new_step
        return ""

    async def _attempt(
        self,
        step: ProviderStep,
        replan_level: Optional[ReplanLevel],
        retries: int,
        last_output: str,
        base_id: str = "",
    ) -> StepResult:
        registry = self._get_registry()
        provider = registry.get(step.provider_id) if registry is not None else None
        base = dict(
            step_id=step.step_id,
            provider_id=step.provider_id,
            chain_type=step.chain_type,
            attempts=retries + 1,
        )
        if provider is None:
            return StepResult(
                success=False,
                error=f"provider '{step.provider_id}' not found",
                confidence=self._adapt.compute_confidence(False, retries, 0.0),
                replan_of=base_id,
                **base,
            )
        if not provider.enabled:
            return StepResult(
                success=False,
                error=f"provider '{step.provider_id}' is disabled",
                confidence=self._adapt.compute_confidence(False, retries, 0.0),
                replan_of=base_id,
                **base,
            )

        task = dict(step.task or {})
        if step.chain_type == ChainType.PIPELINE and last_output:
            task["pipeline_input"] = last_output

        started = time.time()
        try:
            outcome = await asyncio.wait_for(
                provider.execute(task, {"step_id": step.step_id}),
                timeout=float(step.timeout),
            )
        except asyncio.TimeoutError:
            outcome = None
            error = f"step timed out after {step.timeout}s"
        except Exception as exc:
            outcome = None
            error = f"{type(exc).__name__}: {exc}"
        duration_ms = (time.time() - started) * 1000.0

        success = bool(outcome is not None and getattr(outcome, "success", False))
        output = str(getattr(outcome, "output", "") or "") if outcome is not None else ""
        error = "" if success else (error if outcome is None else str(getattr(outcome, "error", "") or "execution failed"))
        artifacts = dict(getattr(outcome, "artifacts", {}) or {}) if outcome is not None else {}

        result = StepResult(
            success=success,
            output=output,
            error=error,
            duration_ms=duration_ms,
            artifacts=artifacts,
            typed_artifacts=[
                typed_artifact_from(key, str(value))
                for key, value in artifacts.items()
                if isinstance(value, str)
            ],
            confidence=self._adapt.compute_confidence(
                success=success,
                retries=retries,
                duration_ms=duration_ms,
                replan_level=replan_level,
            ),
            replan_of=base_id or step.step_id,
            **base,
        )
        self._record_execution(step, result, retries)
        return result

    def _record_execution(self, step: ProviderStep, result: StepResult, retries: int) -> None:
        """Feed the existing provider memory + feedback loop (never raises)."""
        capability = str((step.task or {}).get("capability", "") or "")
        try:
            from core.providers.memory import provider_memory
            provider_memory.record_execution(
                provider_id=step.provider_id,
                success=result.success,
                duration_ms=result.duration_ms,
                capability=capability,
                retries=retries,
            )
        except Exception as exc:
            logger.debug("[orchestrator] memory record failed: %s", exc)
        try:
            feedback = self._get_feedback()
            if feedback:
                decision = feedback["recorder"].record_decision(
                    capability=capability,
                    task=dict(step.task or {}),
                    selected_provider=step.provider_id,
                )
                feedback["recorder"].record_outcome(
                    decision_id=decision.decision_id,
                    success=result.success,
                    duration_ms=result.duration_ms,
                    quality_score=result.confidence.quality_score,
                    retries=retries,
                    replan_level=int(replan_level_value(result)),
                )
        except Exception as exc:
            logger.debug("[orchestrator] feedback record failed: %s", exc)

    # ── Consensus ───────────────────────────────────────────────────────────

    def _merge_consensus(self, results: list[StepResult]) -> str:
        successful = [r for r in results if r.success and r.output]
        if not successful:
            return ""
        if len(successful) == 1:
            return successful[0].output
        sections = [
            f"--- {r.provider_id} output ---\n{r.output}" for r in successful
        ]
        return "\n\n".join(sections)


def replan_level_value(level: Any) -> int:
    try:
        return int(level)
    except Exception:
        return 0


def replan_level_value_of(result: StepResult) -> int:
    """0 when the step succeeded first try; >0 once replanning was involved."""
    return 0 if result.attempts <= 1 else 1


def replan_level_value(result: StepResult) -> int:
    return replan_level_value_of(result)
