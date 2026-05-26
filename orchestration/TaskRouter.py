"""
GOD LEVEL AI — Cognitive Operating System
Phase 1: Meta Controller → Core Orchestrator

Full multi-agent, multi-model cognitive AI system with:
- Adaptive reasoning (multi-path)
- Autonomous execution (AutoGPT-style loops)
- Self-verification and reflection
- Cross-model orchestration
- Persistent memory
- Self-Critic agent
- Specialist routing
- Self-Learning system
"""

import asyncio
import json
import time
import uuid
from typing import Any, Callable, Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum
import logging

from core.context import ExecutionContext, TaskState, Confidence
from core.protocol import GlobalExecutionProtocol, ProtocolStep
from core.self_learning import SelfLearningSystem
from reasoning.multi_path import MultiPathEngine
from reasoning.evaluator import ReasoningEvaluator, OutputVerifier
from reasoning.meta import MetaReasoningEngine
from agents.planner import TaskPlanner, AutonomousExecutor
from agents.debate import DebateEngine
from agents.self_critic import SelfCriticAgent
from agents.specialist import SpecialistRouter
from jarvis_os.memory.memory_manager import MemoryManager
from routing.model_router import ModelRouter
from execution.action_loop import ActionLoop
from execution.confidence_engine import ConfidenceEngine
from utils.logger import SystemLogger, Telemetry
from convergence.engine import ConvergenceDetector, ComputeBudget
from rag.pipeline import RAGPipeline, CrossModelAgreement, ContextCompressor, BM25Reranker
from core.safe_learning import SafeSelfLearner
from benchmarks.runner import BenchmarkRunner

logger = SystemLogger(__name__)


class SystemMode(Enum):
    REASONING   = "reasoning"
    EXECUTION   = "execution"
    VERIFICATION= "verification"
    DEBATE      = "debate"
    REFLECTION  = "reflection"
    AUTONOMOUS  = "autonomous"


@dataclass
class SystemState:
    session_id:      str
    mode:            SystemMode
    current_task:    Optional[str]
    active_agents:   List[str]
    confidence:      float
    iteration:       int
    max_iterations:  int
    abort:           bool = False
    metadata:        Dict[str, Any] = field(default_factory=dict)


class GodLevelOrchestrator:
    """
    Master controller. Implements the 7-step Global Execution Protocol
    across all 11 phases. Routes tasks through the full cognitive pipeline:

    Meta Controller → Planner → Multi-Path Engine → Evaluator →
    Verifier → Confidence Engine → Action Loop → Memory → Output
    """

    def __init__(self, config: Dict[str, Any]):
        self.config     = config
        self.session_id = str(uuid.uuid4())
        self.telemetry  = Telemetry(self.session_id)

        # ── Phase 1: Core system init ──────────────────────────────
        self.protocol         = GlobalExecutionProtocol()
        self.working_memory   = WorkingMemory(capacity=config.get("working_memory_capacity", 50))
        self.episodic_memory  = EpisodicMemory(path=config.get("memory_path", "./data/episodic"))
        self.reflection_memory= ReflectionMemory(path=config.get("memory_path", "./data/reflection"))

        # ── Phase 9: Model router (init early so others can use it) ─
        self.model_router = ModelRouter(config=config.get("models", {}))

        # ── Phase 2-3: Reasoning engines ──────────────────────────
        self.multi_path_engine = MultiPathEngine(
            num_paths=config.get("reasoning_paths", 5),
            model_router=self.model_router
        )
        self.evaluator = ReasoningEvaluator()

        # ── Phase 4: Verifier ─────────────────────────────────────
        self.verifier = OutputVerifier()

        # ── Phase 5: Adaptive compute ─────────────────────────────
        self.confidence_engine = ConfidenceEngine(
            threshold=config.get("confidence_threshold", 0.85)
        )

        # ── Phase 6: Action loop (AutoGPT-style) ──────────────────
        self.action_loop = ActionLoop(
            max_iterations=config.get("max_action_iterations", 20),
            tools_registry=None  # injected after tools init
        )
        self.action_loop.model_router = self.model_router

        # ── Phase 7: Memory integration (done above) ──────────────

        # ── Phase 8: Meta reasoning ───────────────────────────────
        self.meta_engine = MetaReasoningEngine(
            reflection_memory=self.reflection_memory
        )
        self.meta_engine.model_router = self.model_router

        # ── Phase 10: Debate engine ───────────────────────────────
        self.debate_engine = DebateEngine(
            model_router=self.model_router,
            rounds=config.get("debate_rounds", 3)
        )

        # ── Phase 11: Planner + Executor (full integration) ───────
        self.planner = TaskPlanner(
            model_router=self.model_router,
            memory=self.working_memory
        )
        self.executor = AutonomousExecutor(
            action_loop=self.action_loop,
            memory=self.working_memory,
            verifier=self.verifier
        )

        # ── Self-Critic ───────────────────────────────────────────
        self.self_critic = SelfCriticAgent(model_router=self.model_router)

        # ── Specialist Router ─────────────────────────────────────
        self.specialist_router = SpecialistRouter(
            model_router=self.model_router
        )

        # ── Self-Learning System ──────────────────────────────────
        self.self_learning = SelfLearningSystem(
            reflection_memory=self.reflection_memory,
            path=config.get("memory_path", "./data") + "/learning"
        )

        # ── Register tools ────────────────────────────────────────
        from tools.registry import ToolRegistry
        from tools.code_tools import PythonREPLTool, LintTool, GitTool, FormatCodeTool
        self.tools = ToolRegistry(memory=self.working_memory)
        for t in [PythonREPLTool(), LintTool(), GitTool(), FormatCodeTool()]:
            self.tools.register(t)
        self.action_loop.tools_registry = self.tools

                # ── V3: CONVERGENCE ENGINE ────────────────────────────────
        complexity = config.get("default_complexity", "medium")
        self.compute_budget = ComputeBudget(complexity)
        self.convergence = ConvergenceDetector(
            window=config.get("convergence_window", 3),
            min_delta=config.get("convergence_min_delta", 0.02),
            quality_threshold=config.get("confidence_threshold", 0.90),
            max_iterations=config.get("max_global_iterations", 8),
            max_tokens=config.get("max_total_tokens", 40_000),
            max_seconds=config.get("max_task_seconds", 240.0),
        )

        # ── V3: RAG PIPELINE ──────────────────────────────────────
        self.rag = RAGPipeline(
            semantic_memory=None,   # injected after memory init below
            top_k=config.get("rag_top_k", 5),
            context_budget=config.get("rag_context_budget", 2000),
        )

        # ── V3: CROSS-MODEL AGREEMENT ─────────────────────────────
        self.cross_model = CrossModelAgreement(
            model_router=self.model_router,
            agreement_threshold=config.get("agreement_threshold", 0.65)
        )

        # ── V3: SAFE SELF-LEARNER ─────────────────────────────────
        self.safe_learner = SafeSelfLearner(
            dataset_path=config.get("memory_path", "./data") + "/safe_learning",
            min_confidence=config.get("safe_learning_min_confidence", 0.75),
            snapshot_every=config.get("dataset_snapshot_every", 50)
        )

        # ── V3: BENCHMARK RUNNER ──────────────────────────────────
        self.benchmarks = BenchmarkRunner(
            path=config.get("memory_path", "./data") + "/benchmarks",
            run_every=config.get("benchmark_every", 100)
        )

        # Wire RAG to semantic memory if available
        try:
            from jarvis_os.memory.memory_manager import MemoryManager
            self.semantic_memory = SemanticMemory(
                path=config.get("memory_path", "./data") + "/semantic"
            )
            self.rag.memory = self.semantic_memory
        except Exception:
            self.semantic_memory = None

        logger.info(f"GOD LEVEL AI [MYTHOS V3] initialized | session={self.session_id}")

    # ──────────────────────────────────────────────────────────────────
    # PUBLIC ENTRY POINTS
    # ──────────────────────────────────────────────────────────────────

    async def run(self, task: str, context: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Main entry point. Executes the full 7-step Global Execution Protocol.
        Returns structured output with reasoning trace, result, confidence, and memory updates.
        """
        state = SystemState(
            session_id=self.session_id,
            mode=SystemMode.REASONING,
            current_task=task,
            active_agents=[],
            confidence=0.0,
            iteration=0,
            max_iterations=self.config.get("max_global_iterations", 5)
        )

        exec_ctx = ExecutionContext(
            task=task,
            session_id=self.session_id,
            context=context or {},
            working_memory=self.working_memory,
            episodic_memory=self.episodic_memory
        )

        self.telemetry.start_task(task)

        try:
            result = await self._execute_protocol(state, exec_ctx)
            await self._persist_session(exec_ctx, result)

            # Record outcome for self-learning
            strategies = [
                p.get("strategy", "unknown")
                for p in result.get("reasoning_paths", [])
                if isinstance(p, dict)
            ]
            models = list({
                p.get("model", "unknown")
                for p in result.get("reasoning_paths", [])
                if isinstance(p, dict)
            })
            await self.self_learning.record_outcome(
                task=task,
                result=result,
                strategies_used=strategies or ["multi_path"],
                models_used=models or ["unknown"]
            )

            self.telemetry.end_task(success=True)
            return result

        except Exception as e:
            logger.error(f"Orchestrator error: {e}", exc_info=True)
            self.telemetry.end_task(success=False, error=str(e))
            return self._error_output(task, str(e))

    async def autonomous_loop(
        self, goal: str, max_steps: int = 50,
        on_step: Optional[Callable] = None
    ) -> Dict[str, Any]:
        """
        Full AutoGPT-style autonomous loop.
        Decomposes goal → plans → executes → evaluates → iterates until goal achieved.
        """
        logger.info(f"[AutoLoop] Starting autonomous execution | goal={goal[:80]}...")

        goal_state = {
            "goal": goal,
            "achieved": False,
            "steps_taken": [],
            "total_steps": 0,
            "artifacts": []
        }

        decomposition = await self.planner.decompose_goal(goal)
        pending_tasks  = decomposition["tasks"]
        completed_tasks: List[str] = []

        while pending_tasks and goal_state["total_steps"] < max_steps:
            task = pending_tasks.pop(0)
            goal_state["total_steps"] += 1

            logger.info(f"[AutoLoop] Step {goal_state['total_steps']}: {task['name']}")

            step_result = await self.run(task["prompt"], context={
                "goal": goal,
                "completed": completed_tasks,
                "remaining": [t["name"] for t in pending_tasks]
            })

            step_summary = {
                "task":       task["name"],
                "result":     step_result.get("result"),
                "confidence": step_result.get("confidence"),
                "success":    step_result.get("confidence", 0) > 0.7
            }
            goal_state["steps_taken"].append(step_summary)
            completed_tasks.append(task["name"])

            if step_result.get("execution", {}).get("artifacts"):
                goal_state["artifacts"].extend(step_result["execution"]["artifacts"])

            if on_step:
                await on_step(step_summary)

            if step_result.get("confidence", 0) < 0.6:
                replanned = await self.planner.replan(
                    goal=goal,
                    completed=completed_tasks,
                    failed_task=task,
                    result=step_result
                )
                pending_tasks = replanned["tasks"] + pending_tasks

            goal_check = await self.meta_engine.check_goal_achieved(
                goal=goal,
                completed_steps=goal_state["steps_taken"]
            )
            if goal_check["achieved"]:
                goal_state["achieved"] = True
                goal_state["achievement_reason"] = goal_check["reason"]
                break

        goal_state["final_summary"] = await self.meta_engine.summarize_session(
            goal=goal,
            steps=goal_state["steps_taken"],
            artifacts=goal_state["artifacts"]
        )

        return goal_state

    # ──────────────────────────────────────────────────────────────────
    # PROTOCOL IMPLEMENTATION
    # ──────────────────────────────────────────────────────────────────

    async def _execute_protocol(
        self, state: SystemState, ctx: ExecutionContext
    ) -> Dict[str, Any]:
        """
        7-Step Global Execution Protocol loop with confidence-gated iteration.
        """
        trace      = []
        plan       = None
        generation = None
        verification: Dict = {}

        while state.iteration < state.max_iterations and not state.abort:
            state.iteration += 1
            logger.info(f"[Protocol] Iteration {state.iteration}/{state.max_iterations}")

            # ── STEP 1: SELF-THINK ─────────────────────────────────
            step1 = await self.protocol.step(
                ProtocolStep.SELF_THINK,
                task=ctx.task,
                context=ctx.to_dict(),
                meta_engine=self.meta_engine,
                memory=self.episodic_memory
            )
            trace.append({"step": "SELF_THINK", **step1})
            ctx.update("self_think", step1)

            # ── STEP 2: PREDICT ────────────────────────────────────
            step2 = await self.protocol.step(
                ProtocolStep.PREDICT,
                reasoning=step1,
                task=ctx.task,
                meta_engine=self.meta_engine,
                memory=None
            )
            trace.append({"step": "PREDICT", **step2})
            ctx.update("predictions", step2)

            # ── STEP 3: PLAN ───────────────────────────────────────
            plan = await self.planner.create_plan(
                task=ctx.task,
                self_think=step1,
                predictions=step2,
                context=ctx.to_dict()
            )
            trace.append({"step": "PLAN", "plan": plan.to_dict()})
            ctx.update("plan", plan.to_dict())
            state.active_agents = plan.required_agents

            # ── STEP 4: GENERATE (Multi-Path or Debate) ────────────
            if plan.requires_debate:
                state.mode = SystemMode.DEBATE
                generation = await self.debate_engine.run(
                    task=ctx.task,
                    plan=plan,
                    context=ctx.to_dict()
                )
            else:
                state.mode = SystemMode.REASONING
                generation = await self.multi_path_engine.generate(
                    task=ctx.task,
                    plan=plan,
                    context=ctx.to_dict()
                )
            trace.append({"step": "GENERATE", "output": generation.summary})
            ctx.update("generation", generation.to_dict())

            # ── STEP 5: VERIFY ─────────────────────────────────────
            state.mode = SystemMode.VERIFICATION
            verification = await self.verifier.verify(
                task=ctx.task,
                generation=generation,
                plan=plan,
                context=ctx.to_dict()
            )
            trace.append({"step": "VERIFY", **verification})
            ctx.update("verification", verification)

            # Self-Critic pass (semantic check on top of structural verify)
            if verification.get("passed") and generation.best_output:
                critic_result = await self.self_critic.critique(
                    task=ctx.task,
                    response=generation.best_output
                )
                trace.append({"step": "SELF_CRITIC", **critic_result})
                if not critic_result.get("passed", True) and critic_result.get("fixes"):
                    # Apply critic fixes and update generation
                    improved = await self.self_critic.iterative_improve(
                        task=ctx.task,
                        response=generation.best_output,
                        max_rounds=2
                    )
                    if improved and len(improved) > len(generation.best_output) // 2:
                        from core.context import ReasoningPath
                        generation.all_paths.append(ReasoningPath(
                            strategy="self_critic_improved",
                            output=improved,
                            confidence=0.85
                        ))
                        generation.best_path = generation.all_paths[-1]
                        generation.consensus  = improved

            # ── STEP 6: REFINE ─────────────────────────────────────
            confidence_score = await self.confidence_engine.score(
                generation=generation,
                verification=verification,
                plan=plan
            )
            state.confidence = confidence_score

            # ── MYTHOS BRAIN ENHANCEMENT ──────────────────────────────────
            if generation and generation.best_output:
                # MythosBrain removed; no enhancement performed
                pass

            # ── V3: CONVERGENCE GATE ──────────────────────────────────────
            conv = self.convergence.record(
                iteration=state.iteration,
                confidence=confidence_score,
                verification_score=verification.get("score", 0.5),
                issues_count=len(verification.get("issues", [])),
                tokens_used=self.compute_budget._used_tokens,
                elapsed_ms=0.0,
            )
            self.compute_budget.tick()
            trace.append({"step": "CONVERGENCE", "should_stop": conv.should_stop,
                          "reason": conv.reason, "score": conv.final_score,
                          "recommendation": conv.recommendation})

            if verification["passed"] and confidence_score >= self.confidence_engine.threshold:
                logger.info(f"[Protocol] Confidence {confidence_score:.3f} ≥ threshold. Proceeding.")
                break
            elif conv.should_stop:
                logger.info(f"[Protocol] Convergence stop: {conv.reason} ({conv.recommendation})")
                if conv.recommendation == "escalate" and state.iteration <= 2:
                    # One more pass with stronger model
                    logger.info("[Protocol] Escalating to stronger model for one more pass")
                else:
                    break
            else:
                logger.info(f"[Protocol] Confidence {confidence_score:.3f} — refining...")
                refinement = await self._refine(ctx, generation, verification, confidence_score)
                ctx.update("refinement", refinement)
                trace.append({"step": "REFINE", **refinement})

                await self.reflection_memory.store_improvement(
                    task=ctx.task,
                    iteration=state.iteration,
                    issue=verification.get("issues", []),
                    fix=refinement.get("changes", [])
                )

        # ── STEP 7: FINAL OUTPUT ───────────────────────────────────
        if generation is None:
            # Safety net — should never happen in normal flow
            from core.context import GenerationResult
            generation = GenerationResult(task=ctx.task)

        state.mode = SystemMode.EXECUTION
        if plan and plan.requires_execution:
            execution_result = await self.executor.execute(
                plan=plan,
                generation=generation,
                context=ctx.to_dict()
            )
        else:
            execution_result = {"executed": False, "result": generation.best_output}

        final = await self._build_final_output(
            task=ctx.task,
            trace=trace,
            generation=generation,
            verification=verification,
            execution=execution_result,
            confidence=state.confidence,
            iterations=state.iteration
        )

        await self.episodic_memory.store(
            task=ctx.task,
            output=final,
            confidence=state.confidence
        )

        return final

    async def _refine(
        self, ctx: ExecutionContext, generation: Any,
        verification: Dict, confidence: float
    ) -> Dict[str, Any]:
        """
        Adaptive refinement based on verifier feedback and low confidence signals.
        Uses reflection memory to avoid repeating past mistakes.
        """
        past_mistakes = await self.reflection_memory.retrieve_similar(ctx.task)
        evaluation = await self.evaluator.evaluate(
            generation=generation,
            verification=verification,
            past_mistakes=past_mistakes,
            confidence=confidence
        )
        return {
            "evaluation":       evaluation.to_dict(),
            "changes":          evaluation.suggested_changes,
            "strategy_shift":   evaluation.requires_strategy_shift
        }

    async def _build_final_output(
        self, task: str, trace: List, generation: Any,
        verification: Dict, execution: Dict,
        confidence: float, iterations: int
    ) -> Dict[str, Any]:
        return {
            "task":             task,
            "result":           execution.get("result") or generation.best_output,
            "confidence":       round(confidence, 4),
            "iterations":       iterations,
            "verification":     verification,
            "execution":        execution,
            "reasoning_trace":  trace,
            "reasoning_paths":  [p.to_dict() for p in generation.all_paths]
                                if hasattr(generation, "all_paths") else [],
            "session_id":       self.session_id,
            "timestamp":        time.time()
        }

    async def _persist_session(self, ctx: ExecutionContext, result: Dict):
        await self.working_memory.flush_to_episodic(self.episodic_memory)
        await self.reflection_memory.reflect_on_session(
            session_id=self.session_id,
            task=ctx.task,
            result=result
        )
        # V3: Safe self-learning — only admits verified, high-confidence outputs
        trace = result.get("reasoning_trace", [])
        strategies = [p.get("strategy","") for p in result.get("reasoning_paths",[]) if p.get("strategy")]
        models = list({p.get("model","") for p in result.get("reasoning_paths",[]) if p.get("model")})
        admission = await self.safe_learner.observe(
            task=ctx.task,
            result=result,
            strategies_used=strategies or ["multi_path"],
            models_used=models or ["default"]
        )
        if admission.get("drift", {}).get("severity") in ("high", "critical"):
            logger.warning(f"[V3] Learning drift detected: {admission['drift']['message']}")

        # V3: Store in semantic memory for RAG
        if self.semantic_memory and admission.get("admitted"):
            await self.semantic_memory.store(
                task=ctx.task,
                output={"result": result.get("result",""), "confidence": result.get("confidence",0)},
                confidence=result.get("confidence", 0.5)
            )

        # V3: Benchmark tick
        if self.benchmarks.tick():
            self.benchmarks.reset_tick()
            logger.info("[V3] Running automated benchmark suite...")
            try:
                bench_run = await self.benchmarks.run(self)
                regression = self.benchmarks.detect_regression()
                if regression and regression.get("regression"):
                    logger.warning(f"[V3] BENCHMARK REGRESSION: {regression}")
            except Exception as e:
                logger.error(f"[V3] Benchmark run failed: {e}")

    def _error_output(self, task: str, error: str) -> Dict[str, Any]:
        return {
            "task":       task,
            "result":     None,
            "error":      error,
            "confidence": 0.0,
            "session_id": self.session_id,
            "timestamp":  time.time()
        }

    # ──────────────────────────────────────────────────────────────────
    # CONVENIENCE / STATUS
    # ──────────────────────────────────────────────────────────────────

    def get_learning_insights(self) -> Dict[str, Any]:
        """Return self-learning system insights."""
        return self.self_learning.get_insights()

    async def specialist_run(
        self, task: str, specialty: str = None, context: Dict = None
    ) -> Dict[str, Any]:
        """Route a task directly to the best specialist agent."""
        return await self.specialist_router.run(task, specialty=specialty, context=context)
