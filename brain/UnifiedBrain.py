from __future__ import annotations

import json
import logging
import os
import threading
from collections.abc import Callable
from typing import Any

from core.plugins import plugin_registry
from core.schemas import CritiqueResult, ReasonResult, Step
from core.llm_router import refresh_router

from .cognitive_patterns import CognitivePatterns
from .epistemic_tagger import EpistemicTagger
from .reasoning_engine import reasoning_engine

from memory.memory_facade import memory as _canonical_memory
from .memory import MemoryManager as _MemoryManager
from .goals import Goal, GoalStatus, GoalManager
from .planner import Planner
from .planner.task_graph import TaskGraph
from .executor import Executor, Verifier, executor as _executor_singleton
from .automation import AutomationLoop

from .events import EventBus, Event, global_event_bus
from .events.event_types import (
    GoalCreated as GoalCreatedEvent,
    GoalCompleted as GoalCompletedEvent,
    GoalFailed as GoalFailedEvent,
    TaskCompleted,
    TaskFailed,
    MemoryStored,
    VerificationPassed,
    VerificationFailed,
)

from .observers import ObserverManager, FileSystemObserver, SystemMonitor, TimeObserver
from .world_model import WorldModel, Entity
from .learning_engine import LearningEngine
from .goal_generator import GoalGenerator
from .self_improvement import SelfImprovementEngine
from .persistence import ProjectPersistence
from .skill_acquisition import SkillAcquisition
from .tools import ToolRegistry, register_all_tools, ProjectTool

logger = logging.getLogger(__name__)


class UnifiedBrain:
    """Unified cognitive core — reasoning, planning, critique, governance, memory, goals, automation.

    Architecture:
        UnifiedBrain
        ├── EventBus (typed publish/subscribe)
        ├── MemoryManager (Episodic | Semantic | Task | Decision)
        ├── GoalManager (persistent goal tracking)
        ├── Planner (DAG-based task graphs)
        ├── Executor (unified tool execution)
        ├── Verifier (verify every action)
        ├── AutomationLoop (autonomous execution)
        ├── ObserverManager (environment observation)
        ├── WorldModel (global state awareness)
        ├── LearningEngine (auto-modify behavior from lessons)
        ├── GoalGenerator (autonomous goal creation)
        ├── ReasoningEngine (CoT LLM reasoning)
        ├── CognitivePatterns (10 cognitive strategies)
        └── EpistemicTagger (confidence tagging)

    The system is event-driven: every subsystem publishes and subscribes
    to typed events, making the system reactive instead of call-chain-driven.
    """

    def __init__(self, data_dir: str | None = None):
        # Refresh the LLM router to ensure Ollama connection is fresh
        refresh_router()

        if data_dir is None:
            data_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "data",
            )
        os.makedirs(data_dir, exist_ok=True)
        db_path = os.path.join(data_dir, "brain.db")

        # Event bus (heart of the system)
        self.events = global_event_bus

        # Core cognitive layers
        self.reasoning = reasoning_engine
        self.patterns = CognitivePatterns()
        self.tagger = EpistemicTagger()

        # Autonomous OS subsystems
        self.memory = _MemoryManager(db_path)
        self.goals = GoalManager(db_path)
        self.planner = Planner()
        self.executor = _executor_singleton
        self.verifier = Verifier()

        # World model (situational awareness)
        self.world = WorldModel(
            goal_manager=self.goals,
            memory_manager=self.memory,
        )

        # Learning engine (auto-improve from lessons)
        self.learning = LearningEngine(
            memory_manager=self.memory,
            goal_manager=self.goals,
        )

        # Goal generator (autonomous goal creation)
        self.goal_generator = GoalGenerator(
            goal_manager=self.goals,
            world_model=self.world,
            event_bus=self.events,
        )

        # Self-improvement engine (recursive A/B testing)
        self.self_improvement = SelfImprovementEngine(
            memory_manager=self.memory,
            goal_manager=self.goals,
        )

        # Project persistence (multi-day checkpoint/resume)
        self.persistence = ProjectPersistence(
            db_path=db_path,
            goal_manager=self.goals,
        )

        # Skill acquisition (pattern detection → reusable workflows)
        self.skill_acquisition = SkillAcquisition(
            memory_manager=self.memory,
            goal_manager=self.goals,
        )

        # Tool bridge (existing core/tools/ implementations)
        self.tool_registry = ToolRegistry()
        self.project_tool = ProjectTool()
        self.project_tool.root_dir = data_dir

        # Register project tool with executor
        self.executor.register_tool("create_directory", self.project_tool.create_directory)
        self.executor.register_tool("write_file", self.project_tool.write_file)
        self.executor.register_tool("read_file", self.project_tool.read_file)
        self.executor.register_tool("edit_file_text", self.project_tool.edit_file)
        self.executor.register_tool("delete_file", self.project_tool.delete_file)
        self.executor.register_tool("list_directory", self.project_tool.list_directory)
        self.executor.register_tool("run_command", self.project_tool.run_command)
        self.executor.register_tool("compile_java", self.project_tool.compile_java)
        self.executor.register_tool("run_tests", self.project_tool.run_tests)
        self.executor.register_tool("build_project", self.project_tool.build_project)

        # Automation loop (lazy started)
        self.automation = AutomationLoop(
            goal_manager=self.goals,
            memory_manager=self.memory,
            project_dir=data_dir,
        )

        # Observer manager (environment observation)
        self.observers = ObserverManager(event_bus=self.events)
        self._setup_observers()

        # Wire event bus to subsystems
        self._wire_events()

        # Governance
        self._governor = None
        self._gov_lock = threading.Lock()
        self._trace_listeners: list[Callable] = []

    def _setup_observers(self):
        """Register default environment observers."""
        self.observers.register(SystemMonitor())
        self.observers.register(TimeObserver())
        self.observers.register(FileSystemObserver())

    def _wire_events(self):
        """Subscribe internal handlers to relevant events."""
        self.events.subscribe("goal.created", self._on_goal_created)
        self.events.subscribe("goal.completed", self._on_goal_completed)
        self.events.subscribe("goal.failed", self._on_goal_failed)
        self.events.subscribe("task.completed", self._on_task_completed)
        self.events.subscribe("task.failed", self._on_task_failed)
        self.events.subscribe("system.disk_low", self._on_disk_low)

    async def _on_goal_created(self, event: Event):
        logger.debug("[Brain] event: goal.created — %s", event.payload.get("objective", "")[:60])

    async def _on_goal_completed(self, event: Event):
        logger.info("[Brain] event: goal.completed — %s", event.payload.get("objective", "")[:60])

    async def _on_goal_failed(self, event: Event):
        logger.warning("[Brain] event: goal.failed — %s", event.payload.get("objective", "")[:60])

    async def _on_task_completed(self, event: Event):
        _canonical_memory.store_trace(
            action_name=event.payload.get("label", "unknown"),
            observation=event.payload.get("output", ""),
            success=True,
            duration_ms=event.payload.get("duration_ms", 0),
            task_id=event.payload.get("goal_id", ""),
        )

    async def _on_task_failed(self, event: Event):
        _canonical_memory.store_trace(
            action_name=event.payload.get("label", "unknown"),
            observation=event.payload.get("error", ""),
            success=False,
            duration_ms=event.payload.get("duration_ms", 0),
            task_id=event.payload.get("goal_id", ""),
        )

    async def _on_disk_low(self, event: Event):
        logger.info("[Brain] disk low, auto-generating cleanup goal")
        await self.goal_generator.evaluate_world()

    # ---- Governance (lazy init, thread-safe) ----

    def _init_governor(self):
        if self._governor is not None:
            return
        with self._gov_lock:
            if self._governor is not None:
                return
            try:
                from governance.GovernanceValidator import GovernanceValidator
                validator = GovernanceValidator()
                self._governor = validator
            except ImportError as e:
                logger.warning("Governance modules not available, governor disabled: %s", e)
                self._governor = None

    @property
    def governor(self):
        self._init_governor()
        return self._governor

    # ---- Trace emission (for dashboard WebSocket) ----

    def on_trace(self, listener: Callable):
        self._trace_listeners.append(listener)

    async def _emit_trace(self, thinking: str):
        for listener in self._trace_listeners:
            try:
                import inspect
                if inspect.iscoroutinefunction(listener):
                    await listener(thinking)
                else:
                    listener(thinking)
            except Exception as e:
                logger.exception("Trace listener failed: %s", e)

    # ---- Core reasoning methods ----

    async def reason(self, goal: str, context: dict | None = None) -> ReasonResult:
        ctx_str = json.dumps(context or {}, indent=2)
        result = await self.reasoning.reason(goal, ctx_str)
        if result.thinking_trace:
            await self._emit_trace(result.thinking_trace)
        return result

    async def plan(self, goal: str, context: str = "") -> list[Step]:
        raw = await self.patterns.decompose(goal, context)
        conclusion = raw.get("conclusion", "")
        lines = [l.strip() for l in conclusion.split("\n") if l.strip()]
        steps = []
        for i, line in enumerate(lines):
            if line.startswith("-") or line.startswith("*") or line[0].isdigit():
                steps.append(Step(
                    id=f"step_{i}",
                    description=line.lstrip("-*1234567890. "),
                ))
        return steps or [Step(id="step_0", description=conclusion)]

    async def critique(self, output: str, context: str = "") -> CritiqueResult:
        raw = await self.patterns.critique(output, context)
        conclusion = raw.get("conclusion", "")
        trace = raw.get("trace", [])
        flaws = [conclusion] + [t for t in trace if t]
        severity = "major"
        lowered = conclusion.lower()
        if any(w in lowered for w in ["minor", "small", "nitpick", "cosmetic"]):
            severity = "minor"
        elif any(w in lowered for w in ["critical", "severe", "fatal", "broken", "incorrect"]):
            severity = "critical"
        return CritiqueResult(
            flaws=flaws,
            severity=severity,
            revised_output=conclusion,
        )

    async def reflect(self, session: list[dict]) -> str:
        conversation = json.dumps(session, indent=2)
        raw = await self.patterns.reflect(conversation)
        return raw.get("conclusion", "")

    async def three_pass(self, goal: str, context: dict | None = None) -> str:
        for _, result in await plugin_registry.run_hook("before_agent_run", task=goal):
            if result is False:
                return ""

        turn_ctx = {"goal": goal, "context": context or {}}
        r1 = await self.reason(goal, turn_ctx)
        if len(r1.answer) < 200:
            await plugin_registry.run_hook("agent_end", result={"goal": goal, "answer": r1.answer, "pass": 1})
            return r1.answer
        c = await self.critique(r1.answer)
        if c.severity == "minor":
            await plugin_registry.run_hook("agent_end", result={"goal": goal, "answer": r1.answer, "pass": 2})
            return r1.answer
        turn_ctx["flaws"] = c.flaws
        turn_ctx["draft"] = r1.answer
        r3 = await self.reason("Revise this output fixing the flaws listed.", turn_ctx)
        await plugin_registry.run_hook("agent_end", result={"goal": goal, "answer": r3.answer, "pass": 3})
        return r3.answer

    # ---- Autonomous OS methods ----

    async def create_goal(self, objective: str, priority: int = 0,
                          blockers: list[str] | None = None,
                          next_action: str = "",
                          tags: list[str] | None = None) -> Goal:
        """Create a new persistent goal and publish a GoalCreated event."""
        goal = self.goals.create(
            objective=objective,
            priority=priority,
            blockers=blockers,
            next_action=next_action,
            tags=tags,
        )
        await self.events.publish(Event(
            type="goal.created",
            source="brain",
            payload=GoalCreatedEvent(
                goal_id=goal.id,
                objective=objective,
                priority=priority,
            ).__dict__,
        ))
        return goal

    async def complete_goal(self, goal_id: str, result: str = "") -> Goal | None:
        """Complete a goal and publish a GoalCompleted event."""
        goal = self.goals.complete(goal_id, result)
        if goal:
            await self.events.publish(Event(
                type="goal.completed",
                source="brain",
                payload=GoalCompletedEvent(
                    goal_id=goal_id,
                    objective=goal.objective,
                    result=result,
                ).__dict__,
            ))
        return goal

    async def fail_goal(self, goal_id: str, reason: str = "") -> Goal | None:
        """Fail a goal and publish a GoalFailed event."""
        goal = self.goals.fail(goal_id, reason)
        if goal:
            await self.events.publish(Event(
                type="goal.failed",
                source="brain",
                payload=GoalFailedEvent(
                    goal_id=goal_id,
                    objective=goal.objective,
                    reason=reason,
                ).__dict__,
            ))
        return goal

    async def plan_goal(self, goal_id: str) -> TaskGraph:
        """Generate a DAG-based task graph for a goal."""
        goal = self.goals.get(goal_id)
        if not goal:
            raise ValueError(f"Goal not found: {goal_id}")
        graph = await self.planner.plan(goal.objective, goal.next_action)
        return graph

    async def execute_with_verification(self, action_name: str,
                                        params: dict | None = None) -> dict:
        """Execute an action, verify the result, and publish events."""
        result = await self.executor.execute(action_name, params)
        if result.success:
            verification = await self.verifier.verify_action(
                action_description=action_name,
                intended_outcome=str(params) if params else "",
                actual_result=result.output,
            )
        else:
            verification = None

        _canonical_memory.store_trace(
            action_name=action_name,
            action_params=params,
            observation=result.output,
            success=result.success,
            duration_ms=result.duration_ms,
        )

        if verification and verification.verified:
            await self.events.publish(Event(
                type="verification.passed",
                source="brain",
                payload=VerificationPassed(
                    action=action_name,
                    confidence=verification.confidence,
                    evidence=verification.evidence,
                ).__dict__,
            ))
        elif verification:
            await self.events.publish(Event(
                type="verification.failed",
                source="brain",
                payload=VerificationFailed(
                    action=action_name,
                    issues=verification.issues,
                    confidence=verification.confidence,
                ).__dict__,
            ))

        return {
            "success": result.success,
            "output": result.output,
            "confidence": result.confidence,
            "verified": verification.verified if verification else False,
            "verification_confidence": verification.confidence if verification else 0.0,
            "duration_ms": result.duration_ms,
            "error": result.error,
        }

    def store_memory(self, fact: str, category: str = "general",
                     confidence: float = 1.0, source: str = "inference") -> str:
        """Store a semantic fact in long-term memory."""
        mem_id = _canonical_memory.store_fact(fact, category, confidence, source)
        return mem_id

    def retrieve_memories(self, query: str, top_k: int = 8) -> dict:
        """Retrieve relevant memories across all memory types."""
        return {
            "episodes": _canonical_memory.retrieve_episodes(query, top_k=top_k // 2),
            "facts": _canonical_memory.retrieve_facts(query, top_k=top_k // 2),
            "decisions": _canonical_memory.retrieve_decisions(query, top_k=top_k // 2),
        }

    async def auto_generate_goals(self) -> list[Goal]:
        """Autonomously detect opportunities/threats and create goals."""
        return await self.goal_generator.evaluate_world()

    async def apply_learning(self) -> dict:
        """Read stored lessons and modify future behavior."""
        return await self.learning.auto_improve()

    async def run_self_improvement(self, intervention_name: str,
                                   intervention_fn: Any,
                                   rollback_fn: Any | None = None) -> dict:
        """Propose, apply, and A/B test a behavioral change."""
        iid = await self.self_improvement.propose_intervention(
            name=intervention_name,
            description="User-triggered intervention",
            intervention_fn=intervention_fn,
            rollback_fn=rollback_fn,
        )
        return await self.self_improvement.apply_and_test(iid)

    def save_checkpoint(self, goal_id: str,
                        context_summary: str = "") -> dict:
        """Save a project checkpoint for multi-day persistence."""
        cp = self.persistence.save_checkpoint(
            goal_id=goal_id,
            context_summary=context_summary,
        )
        return {"checkpoint_id": cp.id, "created_at": cp.created_at}

    def resume_project(self, goal_id: str) -> str:
        """Generate resume context for a previously saved project."""
        return self.persistence.resume_context(goal_id)

    def record_decision(self, goal_id: str, title: str, decision: str,
                        rationale: str = "") -> str:
        """Record an architecture decision in the journal."""
        return self.persistence.record_decision(
            goal_id=goal_id, title=title, decision=decision,
            rationale=rationale,
        )

    async def discover_skills(self) -> list:
        """Analyze recent traces and discover reusable workflows."""
        return await self.skill_acquisition.analyze_recent_traces()

    async def start_observers(self):
        """Start all environment observers."""
        await self.observers.start_all()

    async def stop_observers(self):
        """Stop all environment observers."""
        await self.observers.stop_all()

    async def start_automation(self):
        """Start the autonomous execution loop."""
        await self.automation.start()

    async def stop_automation(self):
        """Stop the autonomous execution loop."""
        await self.automation.stop()

    def get_world_context(self) -> str:
        """Get formatted world state for LLM reasoning."""
        return self.world.get_context_for_llm()

    def get_status(self) -> dict:
        """Get full system status."""
        return {
            "automation": self.automation.status(),
            "memory": _canonical_memory.summarize(),
            "goals": self.goals.count(),
            "observers": self.observers.list_observers(),
            "events": self.events.stats(),
            "learning": {
                "suppressed_actions": list(self.learning._suppressed_actions),
                "preferred_actions": list(self.learning._preferred_actions),
            },
            "self_improvement": self.self_improvement.get_stats(),
            "persistence": {
                "checkpoints": self.persistence.get_all_checkpoints_count(),
                "decisions": self.persistence.get_all_decisions_count(),
            },
            "skill_acquisition": self.skill_acquisition.get_stats(),
            "tools": {
                "registered": len(self.executor._tools),
                "project_tool_available": True,
            },
            "goal_generator": {
                "total_generated": self.goal_generator.goals_generated,
            },
            "patterns_loaded": 10,
        }


unified_brain = UnifiedBrain()
