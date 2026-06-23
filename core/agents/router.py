"""AgentRouter — matches decomposed goals to capable agents.

Receives a SubGoal tree from the Planner, matches each leaf sub-goal
to an agent via can_handle(), and returns an execution plan.

Agents are evaluated in priority order (lower = checked first).
"""

from __future__ import annotations

import logging

from core.agents.base import BaseAgent
from core.agents.browser_agent import BrowserAgent
from core.agents.build_agent import BuildAgent
from core.agents.email_agent import EmailAgent
from core.agents.memory_agent import MemoryAgent
from core.agents.research_agent import ResearchAgent
from core.agents.test_agent import TestAgent
from core.agents.adapters import (
    AtlasAdapter,
    CipherAdapter,
    ForgeAdapter,
    HeraldAdapter,
    NexusAdapter,
    OracleAdapter,
    PhantomAdapter,
    ScribeAdapter,
    SentinelAdapter,
)
from core.planner.models import SubGoal
from core.workflow.models import StepDefinition

logger = logging.getLogger(__name__)

# Registry of all available agents.
_AGENT_REGISTRY: dict[str, BaseAgent] = {}


def register_agent(agent: BaseAgent) -> None:
    _AGENT_REGISTRY[agent.agent_id] = agent


def get_agent(agent_id: str) -> BaseAgent | None:
    return _AGENT_REGISTRY.get(agent_id)


def list_agents() -> list[BaseAgent]:
    return list(_AGENT_REGISTRY.values())


def _sorted_agents() -> list[BaseAgent]:
    """Return all agents sorted by priority ascending."""
    return sorted(_AGENT_REGISTRY.values(), key=lambda a: a.priority)


# Register built-in agents (tool agents first, then LLM specialists)
register_agent(ResearchAgent(priority=10))
register_agent(BuildAgent(priority=10))
register_agent(TestAgent(priority=10))
register_agent(BrowserAgent(priority=10))
register_agent(MemoryAgent(priority=10))
register_agent(EmailAgent(priority=10))

# LLM specialist adapters
register_agent(ForgeAdapter())
register_agent(NexusAdapter())
register_agent(OracleAdapter())
register_agent(PhantomAdapter())
register_agent(CipherAdapter())
register_agent(HeraldAdapter())
register_agent(AtlasAdapter())
register_agent(ScribeAdapter())
register_agent(SentinelAdapter())


def find_agent_for_goal(goal: str, exclude: set[str] | None = None) -> BaseAgent | None:
    """Return the first matching agent, evaluated in priority order."""
    exclude = exclude or set()
    for agent in _sorted_agents():
        if agent.agent_id in exclude:
            continue
        if agent.can_handle(goal):
            return agent
    return None


def find_agents_for_subgoal(subgoal: SubGoal, context: dict | None = None) -> list[BaseAgent]:
    """Return all agents that can handle a sub-goal, in priority order.

    Most sub-goals map to a single agent, but some may require multiple
    (e.g. "build and test" -> [BuildAgent, TestAgent]).
    """
    goal_text = f"{subgoal.description} {subgoal.step_name or ''}"
    agents: list[BaseAgent] = []
    seen: set[str] = set()

    for candidate in _sorted_agents():
        if candidate.agent_id in seen:
            continue
        if candidate.can_handle(goal_text):
            agents.append(candidate)
            seen.add(candidate.agent_id)

    # If no agent matched the goal text, fall back to step_name lookup
    if not agents and subgoal.step_name:
        step_agent = _AGENT_REGISTRY.get(subgoal.step_name)
        if step_agent:
            agents.append(step_agent)

    return agents


def find_best_agent_for_subgoal(subgoal: SubGoal,
                                 step_name: str | None = None) -> BaseAgent | None:
    """Return the single best (highest priority) agent for a sub-goal, or None.

    Unlike find_agents_for_subgoal() which returns all candidates, this returns
    exactly one — the first match in priority order. No fallback to step_name.

    If step_name is provided, it overrides subgoal.step_name for matching.
    """
    goal_text = f"{subgoal.description} {step_name or subgoal.step_name or ''}"
    for agent in _sorted_agents():
        if agent.can_handle(goal_text):
            return agent
    return None


class AgentRouter:
    """Routes planner sub-goals to capable agents and creates execution plans.

    Usage:
        router = AgentRouter()
        plan = router.route(subgoal_tree, context)
        for step in plan:
            result = await agents.execute(step, context)
    """

    def route(self, root: SubGoal, context: dict | None = None) -> list[dict]:
        """Convert a SubGoal tree into an ordered list of agent execution tasks.

        Each task has:
          agent_id: str  — which agent to invoke
          goal: str      — the sub-goal description
          step: str      — the step name
          parameters: dict — execution parameters

        Returns a flat ordered list (depth-first traversal of leaf sub-goals).
        """
        leaves = root.flatten()
        tasks: list[dict] = []

        for leaf in leaves:
            agents = find_agents_for_subgoal(leaf, context)
            if not agents:
                logger.warning("Router: no agent for subgoal %s (%s)",
                               leaf.id, leaf.description[:60])
                continue
            for agent in agents:
                tasks.append({
                    "agent_id": agent.agent_id,
                    "goal": leaf.description,
                    "step": leaf.step_name or agent.agent_id,
                    "parameters": dict(leaf.parameters),
                })

        return tasks

    def route_steps(self, steps: list[dict], context: dict | None = None) -> list[dict]:
        """Route abstract step names to agent tasks.

        Accepts step dicts like [{"name": "research"}, {"name": "build"}, ...]
        and returns agent tasks.
        """
        tasks: list[dict] = []
        for step in steps:
            step_name = step.get("name", "")
            agent = _AGENT_REGISTRY.get(step_name)
            if not agent:
                agent = find_agent_for_goal(step_name)
            if not agent:
                logger.warning("Router: no agent for step %s", step_name)
                continue
            tasks.append({
                "agent_id": agent.agent_id,
                "goal": step.get("description", step_name),
                "step": step_name,
                "parameters": step.get("parameters", {}),
            })
        return tasks
