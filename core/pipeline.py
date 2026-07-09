"""pipeline.py — Unified Runtime Pipeline.

Every request flows through:
  Knowledge Injection → Planning → Strategy → Decision →
  Capability/Provider → Workflow → Activity Recording →
  Execution → Learning Feedback

This is the single entry point that wires all existing architectural
components into one execution path.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, AsyncGenerator

import importlib as _il
ActivityManager = _il.import_module("core.activity.manager").ActivityManager
from core.decision.evidence import DecisionEvidence
from core.decision.scoring import UnifiedDecisionModel
from core.graph import build_default_graph
from core.graph.state import AgentState
from core.long_term_memory.adapter import BehaviorAdapter
from core.planner.executor import PlannerExecutor
from core.providers.router import ProviderRouter
from core.strategy.generator import StrategyGenerator
from core.strategy.selector import StrategySelector
from core.tools._constants import MAX_AGENT_ROUNDS
from core.workflow.engine import WorkflowEngine
from core.workflow.models import StepDefinition

logger = logging.getLogger(__name__)

_PIPELINE_ENABLED = True


def infer_capabilities(goal: str) -> list[str]:
    """Map a user goal to required capabilities.

    Returns a sorted list of capability names like 'coding', 'browser',
    'research', 'deployment', 'messaging', 'storage'.
    """
    gl = goal.lower()
    caps: list[str] = []
    if any(kw in gl for kw in ("build", "code", "implement", "create", "fix", "refactor")):
        caps.append("coding")
    if any(kw in gl for kw in ("search", "browse", "navigate", "open", "web", "browser", "lookup")):
        caps.append("browser")
    if any(kw in gl for kw in ("research", "find", "learn", "what is", "how does", "investigate")):
        caps.append("research")
    if any(kw in gl for kw in ("deploy", "publish", "release", "host")):
        caps.append("deployment")
    if any(kw in gl for kw in ("email", "send", "message", "notify", "slack", "telegram")):
        caps.append("messaging")
    if any(kw in gl for kw in ("schedule", "automate", "background", "cron", "recurring")):
        caps.append("automation")
    if not caps:
        caps.append("research")
    return sorted(set(caps))


class RuntimePipeline:
    """Unified runtime pipeline orchestrator.

    Wires all existing architectural components into a single execution
    path. Every request flows through this pipeline.

    Usage:
        pipeline = RuntimePipeline()
        async for event in pipeline.execute(goal, messages, ...):
            yield event
    """

    def __init__(
        self,
        planner: PlannerExecutor | None = None,
        activity_manager: ActivityManager | None = None,
        workflow_engine: WorkflowEngine | None = None,
        behavior_adapter: BehaviorAdapter | None = None,
        decision_evidence: DecisionEvidence | None = None,
        decision_scorer: UnifiedDecisionModel | None = None,
        strategy_generator: StrategyGenerator | None = None,
        strategy_selector: StrategySelector | None = None,
        provider_router: ProviderRouter | None = None,
    ):
        self._planner = planner or PlannerExecutor()
        self._activity_manager = activity_manager or ActivityManager()

        # Wire WorkflowEngine with outcome recorder for learning feedback
        if workflow_engine is not None:
            self._workflow_engine = workflow_engine
        else:
            try:
                from core.workflow.recorder import WorkflowExecutionRecorder
                wf_recorder = WorkflowExecutionRecorder()
                self._workflow_engine = WorkflowEngine(
                    workflow_recorder=wf_recorder,
                )
            except Exception:
                self._workflow_engine = WorkflowEngine()
        self._behavior_adapter = behavior_adapter or BehaviorAdapter()
        self._decision_evidence = decision_evidence or DecisionEvidence()
        self._decision_scorer = decision_scorer or UnifiedDecisionModel()
        self._strategy_generator = strategy_generator or StrategyGenerator()
        self._strategy_selector = strategy_selector or StrategySelector()
        self._provider_router = provider_router or ProviderRouter()

    async def execute(
        self,
        messages: list[dict],
        endpoint_url: str,
        model: str,
        headers: dict | None = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        prompt_type: str | None = None,
        max_rounds: int = MAX_AGENT_ROUNDS,
        max_tool_calls: int = 0,
        context_length: int = 0,
        active_document=None,
        session_id: str | None = None,
        disabled_tools: set[str] | None = None,
        owner: str | None = None,
        relevant_tools: set[str] | None = None,
        fallbacks: list[tuple] | None = None,
        _is_teacher_run: bool = False,
        pause_before_effectful: bool = False,
        mode: str | None = None,
        project_context: dict | None = None,
    ) -> AsyncGenerator[str, None]:
        """Execute the full runtime pipeline for a user request.

        Yields SSE events just like the existing stream_agent_loop.
        """
        if not _PIPELINE_ENABLED:
            # Bypass: run the legacy graph directly
            graph = build_default_graph()
            state = AgentState(
                endpoint_url=endpoint_url, model=model, messages=messages,
                headers=headers or {}, temperature=temperature,
                max_tokens=max_tokens, prompt_type=mode or prompt_type,
                max_rounds=max_rounds or MAX_AGENT_ROUNDS,
                max_tool_calls=max_tool_calls, context_length=context_length,
                active_document=active_document, session_id=session_id,
                disabled_tools=disabled_tools, owner=owner,
                relevant_tools=relevant_tools,
                fallbacks=list(fallbacks or []),
                _is_teacher_run=_is_teacher_run,
                pause_before_effectful=pause_before_effectful,
                mode=mode, project_context=project_context,
            )
            async for event in graph.execute(state):
                yield event
            return

        goal = _extract_goal(messages)
        logger.info("[PIPELINE] Starting: goal=%r", goal[:80] if goal else "(chat)")

        # ── Phase A.8: Knowledge Injection ────────────────────────────────
        knowledge_ctx = {}
        knowledge_prompt = ""
        try:
            knowledge_ctx = self._behavior_adapter.for_planner(goal)
            knowledge_prompt = self._behavior_adapter.format_for_prompt(knowledge_ctx)
            if knowledge_prompt:
                logger.info("[PIPELINE] Knowledge injected: %d items",
                            sum(len(v) for v in knowledge_ctx.values()))
        except Exception as e:
            logger.debug("[PIPELINE] Knowledge injection skipped: %s", e)

        # ── Phase A.1: Planning ───────────────────────────────────────────
        plan = None
        plan_id = None
        plan_steps: list[dict] = []
        try:
            plan = self._planner.create_plan(goal)
            if plan:
                plan_id = plan.template_id
                plan_steps = list(plan.steps)
                logger.info("[PIPELINE] Plan created: %s (%d steps)", plan_id, len(plan_steps))
        except Exception as e:
            logger.debug("[PIPELINE] Planning skipped: %s", e)

        # ── Phase A.2: Strategy Selection ─────────────────────────────────
        strategy = None
        strategy_decision = None
        try:
            strategies = self._strategy_generator.generate(goal)
            if strategies:
                chosen, decision = self._strategy_selector.select(strategies)
                strategy = chosen
                strategy_decision = decision
                logger.info("[PIPELINE] Strategy: %s", strategy.name if strategy else "none")
        except Exception as e:
            logger.debug("[PIPELINE] Strategy selection skipped: %s", e)

        # ── Phase A.3 + A.4: Decision + Capability ───────────────────────
        capabilities = infer_capabilities(goal)
        decision_result = None
        provider = None
        try:
            evidence = self._decision_evidence.collect(
                template_ids=[(plan_id or "default", 1)] if plan_id else [("default", 1)],
                task_type=mode or "",
                capabilities=capabilities,
            )
            decision_result = self._decision_scorer.rank(evidence)
            logger.info("[PIPELINE] Decision: %s score=%.3f",
                        decision_result.selected.template_id if decision_result.selected else "none",
                        decision_result.selected.final_score if decision_result.selected else 0)
        except Exception as e:
            logger.debug("[PIPELINE] Decision skipped: %s", e)

        # ── Phase A.5: Provider Selection ────────────────────────────────
        selected_capability = ""
        try:
            task_ctx = {
                "capability": "",
                "goal": goal,
                "model": model,
                "task_type": mode or "",
                "language": "",
                "framework": "",
            }
            for cap in capabilities:
                task_ctx["capability"] = cap
                p = self._provider_router.select(cap, task=task_ctx, record_decision=True)
                if p:
                    provider = p
                    selected_capability = cap
                    logger.info("[PIPELINE] Provider: %s for capability=%s", p.provider_id, cap)
                    break
        except Exception as e:
            logger.debug("[PIPELINE] Provider selection skipped: %s", e)

        # ── Phase A.7: Activity Recording (begin) ────────────────────────
        activity = None
        exec_node: ActivityNode | None = None
        try:
            activity = self._activity_manager.create_activity(
                goal,
                metadata={
                    "plan_id": plan_id,
                    "strategy": strategy.name if strategy else None,
                    "capabilities": capabilities,
                    "provider": provider.provider_id if provider else None,
                    "model": model,
                },
            )
            logger.info("[PIPELINE] Activity created: %s", activity.node_id)
            # Create an execution subgoal node under the root activity
            exec_node = self._activity_manager.create_agent_task(
                activity,
                agent_id="pipeline",
                goal=goal[:200],
                step_name="execute",
            )
            self._activity_manager.mark_running(exec_node.node_id)
        except Exception as e:
            logger.debug("[PIPELINE] Activity recording skipped: %s", e)

        # ── Phase A.6: Workflow Execution ────────────────────────────────
        workflow = None
        try:
            if plan_steps:
                step_defs = []
                for s in plan_steps:
                    task = self._planner.get_task_for_step(plan_id or "", s.get("name", ""))
                    if task:
                        step_defs.append(StepDefinition(
                            tool_name=task["tool"],
                            input_data=task.get("default_args", {}),
                            max_retries=2,
                        ))
                if step_defs:
                    workflow = await self._workflow_engine.start_workflow(
                        workflow_type=plan_id or "agent_task",
                        steps=step_defs,
                        session_id=session_id or "",
                        owner=owner or "dev",
                        launch_background=False,
                    )
                    logger.info("[PIPELINE] Workflow created: %s", workflow.workflow_id)
                    if activity:
                        self._activity_manager.link_workflow(activity.node_id, workflow.workflow_id)
        except Exception as e:
            logger.debug("[PIPELINE] Workflow creation skipped: %s", e)

        # ── Assemble pipeline context for graph ──────────────────────────
        pipeline_ctx = {
            "knowledge_prompt": knowledge_prompt,
            "knowledge_ctx": knowledge_ctx,
            "plan": plan,
            "plan_id": plan_id,
            "strategy": strategy,
            "strategy_decision": strategy_decision,
            "decision_result": decision_result,
            "capabilities": capabilities,
            "provider": provider,
            "activity_id": activity.node_id if activity else None,
            "workflow_id": workflow.workflow_id if workflow else None,
        }

        graph = build_default_graph()
        state = AgentState(
            endpoint_url=endpoint_url, model=model, messages=messages,
            headers=headers or {}, temperature=temperature,
            max_tokens=max_tokens, prompt_type=mode or prompt_type,
            max_rounds=max_rounds or MAX_AGENT_ROUNDS,
            max_tool_calls=max_tool_calls, context_length=context_length,
            active_document=active_document, session_id=session_id,
            disabled_tools=disabled_tools, owner=owner,
            relevant_tools=relevant_tools,
            fallbacks=list(fallbacks or []),
            _is_teacher_run=_is_teacher_run,
            pause_before_effectful=pause_before_effectful,
            mode=mode, project_context=project_context,
            pipeline_context=pipeline_ctx,
        )

        # Track tool calls for activity recording
        executed_tools: list[dict] = []
        tool_call_nodes: list[ActivityNode] = []

        async for event in graph.execute(state):
            yield event
            # Track tool outputs and record activity nodes for each tool call
            if event.startswith('data: '):
                import json as _json
                try:
                    data = _json.loads(event[6:])
                    etype = data.get("type")

                    if etype == "tool_start":
                        # Record tool_start as a tool_call activity node
                        if exec_node:
                            tool_node = self._activity_manager.create_tool_call(
                                exec_node,
                                tool_type=data.get("tool", ""),
                                input_data={"command": data.get("command", "")},
                            )
                            self._activity_manager.mark_running(tool_node.node_id)
                            tool_call_nodes.append(tool_node)

                    elif etype == "tool_output":
                        # Mark the corresponding tool_call completed/failed
                        if tool_call_nodes:
                            tool_node = tool_call_nodes.pop(0)
                            exit_code = data.get("exit_code")
                            if exit_code is not None and exit_code != 0:
                                self._activity_manager.mark_failed(
                                    tool_node.node_id,
                                    error=f"exit_code={exit_code}",
                                )
                            else:
                                self._activity_manager.mark_completed(
                                    tool_node.node_id,
                                    output={"exit_code": exit_code},
                                )
                        executed_tools.append({
                            "tool": data.get("tool", ""),
                            "command": data.get("command", ""),
                            "output": data.get("output", ""),
                            "exit_code": exit_code,
                        })
                except Exception:
                    pass

        # ── Post-execution: Activity Recording (end) ─────────────────────
        try:
            success = state.error is None and state.phase.name not in ("ERROR",)
            if exec_node:
                if success:
                    self._activity_manager.mark_completed(
                        exec_node.node_id,
                        output={
                            "rounds": state.round_num,
                            "tool_calls": len(executed_tools),
                        },
                    )
                else:
                    self._activity_manager.mark_failed(
                        exec_node.node_id,
                        error=state.error or f"Phase: {state.phase.name}",
                    )
            if activity:
                if success:
                    self._activity_manager.complete_activity(
                        activity.node_id,
                        output={
                            "rounds": state.round_num,
                            "tool_calls": state.total_tool_calls,
                            "tools_used": [t["tool"] for t in executed_tools],
                            "phase": state.phase.name,
                        },
                        artifacts={},
                    )
                else:
                    self._activity_manager.fail_activity(
                        activity.node_id,
                        error=state.error or f"Phase: {state.phase.name}",
                    )
                logger.info("[PIPELINE] Activity %s: %s",
                            activity.node_id,
                            "completed" if success else "failed")
        except Exception as e:
            logger.debug("[PIPELINE] Activity completion skipped: %s", e)

        # ── Phase A.8.5: Provider Memory Feedback ─────────────────────────
        try:
            if provider:
                from core.providers.feedback.models import ProviderResult
                from core.providers.memory import provider_memory
                pr = ProviderResult(
                    provider_id=provider.provider_id,
                    capability=selected_capability or (capabilities[0] if capabilities else "coding"),
                    success=success,
                    duration_ms=(time.time() - state.total_start) * 1000 if state.total_start else 0.0,
                    error=state.error or "",
                    tokens=state.real_input_tokens + state.real_output_tokens,
                    metrics={
                        "model": model,
                        "mode": mode or "",
                        "rounds": state.round_num,
                        "tool_calls": len(executed_tools),
                        "tools_used": [t["tool"] for t in executed_tools],
                    },
                )
                provider_memory.record(pr)
                logger.info("[PIPELINE] Provider memory recorded for %s (success=%s)",
                            provider.provider_id, success)

                # Wire outcome into FeedbackStore + CalibrationEngine
                try:
                    decision_id = getattr(self._provider_router, "last_decision_id", None)
                    if decision_id:
                        recorder = self._provider_router._get_decision_recorder()
                        if recorder:
                            recorder.record_outcome(
                                decision_id=decision_id,
                                success=success,
                                duration_ms=pr.duration_ms,
                                cost=getattr(pr, "cost", 0.0),
                                error=pr.error or "",
                            )
                        calibrator = self._provider_router._get_calibration_engine()
                        if calibrator:
                            calibrator.update_from_outcomes(provider.provider_id, selected_capability)
                except Exception as cal_err:
                    logger.debug("[PIPELINE] Calibration update skipped: %s", cal_err)
        except Exception as e:
            logger.debug("[PIPELINE] Provider memory feedback skipped: %s", e)

        # ── Phase A.9: Learning Feedback ─────────────────────────────────
        try:
            from core.long_term_memory.consolidator import Consolidator
            consolidator = Consolidator()
            async def _consolidate_with_timeout():
                try:
                    await asyncio.wait_for(consolidator.consolidate_once_async(), timeout=120)
                except asyncio.TimeoutError:
                    logger.warning("[PIPELINE] Consolidation timed out after 120s")
            asyncio.create_task(_consolidate_with_timeout())
            logger.info("[PIPELINE] Learning feedback triggered")
        except Exception as e:
            logger.debug("[PIPELINE] Learning feedback skipped: %s", e)


def _extract_goal(messages: list[dict]) -> str:
    """Extract user goal from messages — last user message content."""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg.get("content", "")
            if isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        return part["text"]
            return str(content)[:500]
    return ""
