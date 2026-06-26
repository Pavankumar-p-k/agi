from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from core.providers.base import ExecutionProvider
from core.providers.memory import provider_memory
from core.providers.orchestration.adapt import AdaptEngine, ReplanLevel
from core.providers.orchestration.models import (
    ArtifactType, ChainType, OrchestrationPlan, OrchestrationResult,
    ProviderStep, StepConfidence, StepResult, TypedArtifact,
    infer_artifact_type, typed_artifact_from,
)
from core.providers.orchestration.store import orchestration_store
from core.providers.registry import provider_registry
from core.providers.router import provider_router

logger = logging.getLogger(__name__)


class Orchestrator:
    """Executes multi-provider orchestration plans.

    Features:
      - Dependency-aware scheduling with sequential/parallel/pipeline/verify/consensus
      - Dynamic replanning on step failure (alternative provider → capability substitution)
      - Confidence propagation (per-step quality/cost/risk)
      - Typed artifact tracking
      - Execution history persisted to SQLite
    """

    def __init__(
        self,
        registry=provider_registry,
        router=provider_router,
        store=orchestration_store,
    ):
        self._registry = registry
        self._router = router
        self._store = store
        self._adapt = AdaptEngine(registry, router)

    async def execute(self, plan: OrchestrationPlan) -> OrchestrationResult:
        """Execute an orchestration plan with adaptive replanning."""

        start = time.time()
        logger.info("[Orchestrator] Executing plan %s (%d steps)", plan.plan_id, plan.total_steps)

        result = OrchestrationResult(plan=plan, start_time=start)

        completed_steps: set[str] = set()
        step_results: dict[str, StepResult] = {}
        pipeline_context: dict[str, Any] = dict(plan.context) if plan.context else {}
        attempted_providers: dict[str, set[str]] = {}
        """step_id → set of provider_ids that have been tried."""

        remaining = set(plan.step_ids())
        ready_queue: list[ProviderStep] = []
        in_flight: set[str] = set()

        try:
            while remaining:
                newly_ready = [
                    s for s in plan.steps
                    if s.step_id in remaining
                    and s.step_id not in in_flight
                    and s.is_ready(completed_steps)
                ]

                ready_queue.extend(newly_ready)
                for s in newly_ready:
                    in_flight.add(s.step_id)

                if not ready_queue:
                    if remaining:
                        blocked = [s.step_id for s in plan.steps if s.step_id in remaining]
                        result.error = f"Deadlock: blocked steps {blocked}"
                        logger.warning("[Orchestrator] %s", result.error)
                    break

                parallel_steps = [s for s in ready_queue if s.chain_type == ChainType.PARALLEL]
                non_parallel = [s for s in ready_queue if s.chain_type != ChainType.PARALLEL]

                for step in non_parallel:
                    ready_queue.remove(step)
                    if step.chain_type == ChainType.PIPELINE and step_results:
                        last = list(step_results.values())[-1]
                        if last.success:
                            step.task["pipeline_input"] = last.output

                    s_result = await self._execute_step_with_replan(
                        step, plan, pipeline_context, completed_steps,
                        step_results, attempted_providers,
                    )

                    if s_result:
                        step_results[s_result.step_id] = s_result
                        completed_steps.add(s_result.step_id)
                        # If replanning created a new step, remove the original from tracking
                        if s_result.step_id != step.step_id:
                            remaining.discard(step.step_id)
                            in_flight.discard(step.step_id)
                        remaining.discard(s_result.step_id)
                        in_flight.discard(s_result.step_id)

                        if s_result.success:
                            pipeline_context[s_result.step_id] = s_result.output
                            for key, val in s_result.artifacts.items():
                                pipeline_context[f"artifact_{key}"] = val

                if parallel_steps:
                    for s in parallel_steps:
                        ready_queue.remove(s)

                    coros = [
                        self._execute_step_with_replan(
                            s, plan, pipeline_context, completed_steps,
                            step_results, attempted_providers,
                        )
                        for s in parallel_steps
                    ]
                    p_results = await asyncio.gather(*coros, return_exceptions=True)

                    for step, p_res in zip(parallel_steps, p_results):
                        if isinstance(p_res, Exception):
                            s_result = StepResult(
                                step_id=step.step_id,
                                provider_id=step.provider_id,
                                chain_type=step.chain_type,
                                success=False,
                                error=str(p_res),
                            )
                        elif p_res is not None:
                            s_result = p_res
                        else:
                            continue

                        step_results[s_result.step_id] = s_result
                        completed_steps.add(s_result.step_id)
                        if s_result.step_id != step.step_id:
                            remaining.discard(step.step_id)
                            in_flight.discard(step.step_id)
                        remaining.discard(s_result.step_id)
                        in_flight.discard(s_result.step_id)

                        if s_result.success:
                            pipeline_context[s_result.step_id] = s_result.output
                            for key, val in s_result.artifacts.items():
                                pipeline_context[f"artifact_{key}"] = val

                # Consensus merging
                consensus_results = [
                    r for r in step_results.values()
                    if r.chain_type == ChainType.CONSENSUS and r.step_id in completed_steps
                ]
                if consensus_results:
                    merged = self._merge_consensus(consensus_results)
                    pipeline_context["consensus_merged"] = merged

            # ── Determine overall success ──────────────────────────────
            result.step_results = list(step_results.values())
            failed = [r for r in result.step_results if not r.success]

            if failed:
                verify_failures = [r for r in failed if r.chain_type == ChainType.VERIFY]
                if verify_failures:
                    result.error = f"Verify step(s) failed: {[r.step_id for r in verify_failures]}"
                else:
                    result.error = f"Step(s) failed: {[r.step_id for r in failed]}"
                result.overall_success = False
            else:
                result.overall_success = True

        except Exception as e:
            logger.exception("[Orchestrator] Execution error: %s", e)
            result.error = str(e)
            result.overall_success = False

        result.end_time = time.time()

        # ── Record to memory and store ────────────────────────────────
        for s_result in result.step_results:
            if s_result.provider_id:
                provider_memory.record_execution(
                    provider_id=s_result.provider_id,
                    success=s_result.success,
                    duration_ms=s_result.duration_ms,
                )

        try:
            self._store.save_result(result)
        except Exception as e:
            logger.warning("[Orchestrator] Failed to save to store: %s", e)

        elapsed = result.duration_ms
        logger.info(
            "[Orchestrator] Plan %s complete: %s (%d/%d steps, %.0fms, conf=%.2f, cost=$%.4f)",
            plan.plan_id,
            "PASS" if result.overall_success else "FAIL",
            len(result.successful_steps), len(result.step_results),
            elapsed, result.avg_confidence, result.total_cost,
        )
        return result

    async def _execute_step_with_replan(
        self,
        step: ProviderStep,
        plan: OrchestrationPlan,
        context: dict[str, Any],
        completed_steps: set[str],
        step_results: dict[str, StepResult],
        attempted_providers: dict[str, set[str]],
    ) -> StepResult | None:
        """Execute a step with adaptive replanning on failure."""

        # Track attempted providers
        if step.step_id not in attempted_providers:
            attempted_providers[step.step_id] = set()
        attempted_providers[step.step_id].add(step.provider_id)

        s_result = await self._execute_step(step, context)

        # If successful, return immediately
        if s_result.success:
            return s_result

        # Step failed — attempt adaptive replanning
        logger.info(
            "[Orchestrator] Step %s failed (%s) — attempting replan...",
            step.step_id, s_result.error,
        )

        level, new_step = self._adapt.create_replan(
            plan, step, s_result.error,
            attempted_providers=attempted_providers.get(step.step_id),
        )

        if level == ReplanLevel.ABORT or new_step is None:
            return s_result

        # Add the new step to the plan
        plan.add_step(new_step)

        # Execute the replacement step
        if new_step.step_id not in attempted_providers:
            attempted_providers[new_step.step_id] = set()
        attempted_providers[new_step.step_id].add(new_step.provider_id)

        new_result = await self._execute_step(new_step, context)

        # Update confidence to reflect replanning
        new_result.confidence = self._adapt.compute_confidence(
            success=new_result.success,
            retries=new_result.retries,
            duration_ms=new_result.duration_ms,
            quality_score=0.5 if new_result.success else 0.0,
            cost=0.0,
            replan_level=level,
        )

        return new_result

    async def _execute_step(
        self,
        step: ProviderStep,
        context: dict[str, Any],
    ) -> StepResult:
        provider = self._registry.get(step.provider_id)
        if not provider:
            return StepResult(
                step_id=step.step_id, provider_id=step.provider_id,
                chain_type=step.chain_type,
                success=False,
                error=f"Provider '{step.provider_id}' not found",
            )

        if not provider.enabled:
            fallback = self._router.select(
                step.task.get("capability", "coding"), step.task,
            )
            if fallback and fallback.provider_id != step.provider_id:
                logger.info(
                    "[Orchestrator] Step %s: %s disabled, falling back to %s",
                    step.step_id, step.provider_id, fallback.provider_id,
                )
                provider = fallback
                step.provider_id = fallback.provider_id
            else:
                return StepResult(
                    step_id=step.step_id, provider_id=step.provider_id,
                    chain_type=step.chain_type,
                    success=False,
                    error=f"Provider '{step.provider_id}' disabled and no fallback available",
                )

        step_start = time.time()
        error = ""
        retries = 0

        for attempt in range(step.max_retries + 1):
            try:
                exec_result = await asyncio.wait_for(
                    provider.execute(step.task, context),
                    timeout=step.timeout,
                )

                if exec_result.success:
                    # Build typed artifacts
                    typed_artifacts = []
                    for key, path in exec_result.artifacts.items():
                        typed_artifacts.append(typed_artifact_from(key, path))

                    # Estimate quality from output length as a heuristic
                    quality = min(1.0, len(exec_result.output) / 500) if exec_result.output else 0.0

                    confidence = self._adapt.compute_confidence(
                        success=True, retries=retries,
                        duration_ms=exec_result.duration_ms or (time.time() - step_start) * 1000,
                        quality_score=quality,
                        cost=exec_result.metadata.get("cost", 0.0),
                    )

                    step_result = StepResult(
                        step_id=step.step_id,
                        provider_id=step.provider_id,
                        chain_type=step.chain_type,
                        success=True,
                        output=exec_result.output,
                        duration_ms=exec_result.duration_ms or (time.time() - step_start) * 1000,
                        artifacts=exec_result.artifacts,
                        typed_artifacts=typed_artifacts,
                        confidence=confidence,
                        retries=retries,
                        metadata=exec_result.metadata,
                    )

                    if step.chain_type == ChainType.VERIFY and not exec_result.output.strip():
                        error = "Verify step produced empty output"
                        continue

                    return step_result

                error = exec_result.error or "Execution returned success=False"
                retries = attempt + 1
                logger.debug(
                    "[Orchestrator] Step %s attempt %d: %s",
                    step.step_id, attempt + 1, error,
                )

            except asyncio.TimeoutError:
                error = f"timeout after {step.timeout}s"
                retries = attempt + 1
            except Exception as e:
                error = str(e)
                retries = attempt + 1

        return StepResult(
            step_id=step.step_id,
            provider_id=step.provider_id,
            chain_type=step.chain_type,
            success=False,
            error=error,
            duration_ms=(time.time() - step_start) * 1000,
            retries=retries,
            confidence=self._adapt.compute_confidence(
                success=False, retries=retries,
                duration_ms=(time.time() - step_start) * 1000,
            ),
        )

    def _merge_consensus(self, results: list[StepResult]) -> str:
        outputs = [r.output for r in results if r.success]
        if not outputs:
            return ""
        if len(outputs) == 1:
            return outputs[0]
        merged: list[str] = []
        for i, output in enumerate(outputs):
            pid = results[i].provider_id if i < len(results) else f"provider_{i}"
            merged.append(f"--- {pid} output ---\n{output}")
        return "\n\n".join(merged)
