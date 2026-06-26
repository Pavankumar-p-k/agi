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
from core.providers.router import ProviderRouter, provider_router
from core.providers.registry import provider_registry
from core.providers.base import ExecutionProvider
from core.capability.registry import capability_registry

logger = logging.getLogger(__name__)

_AGENT_REGISTRY: dict[str, BaseAgent] = {}


def register_agent(agent: BaseAgent) -> None:
    _AGENT_REGISTRY[agent.agent_id] = agent


def get_agent(agent_id: str) -> BaseAgent | None:
    return _AGENT_REGISTRY.get(agent_id)


def list_agents() -> list[BaseAgent]:
    return list(_AGENT_REGISTRY.values())


def _sorted_agents() -> list[BaseAgent]:
    return sorted(_AGENT_REGISTRY.values(), key=lambda a: a.priority)


register_agent(ResearchAgent(priority=10))
register_agent(BuildAgent(priority=10))
register_agent(TestAgent(priority=10))
register_agent(BrowserAgent(priority=10))
register_agent(MemoryAgent(priority=10))
register_agent(EmailAgent(priority=10))

register_agent(ForgeAdapter())
register_agent(NexusAdapter())
register_agent(OracleAdapter())
register_agent(PhantomAdapter())
register_agent(CipherAdapter())
register_agent(HeraldAdapter())
register_agent(AtlasAdapter())
register_agent(ScribeAdapter())
register_agent(SentinelAdapter())


_CAPABILITY_TO_DEFAULT_AGENT: dict[str, str] = {
    "research": "research",
    "build": "build",
    "test": "test",
    "browser": "browser",
    "memory": "memory",
    "email": "email",
    "coding": "forge",
}


def find_agent_for_goal(goal: str, exclude: set[str] | None = None) -> BaseAgent | None:
    exclude = exclude or set()
    for agent in _sorted_agents():
        if agent.agent_id in exclude:
            continue
        if agent.can_handle(goal):
            return agent
    return None


def find_providers_for_goal(goal: str) -> list[ExecutionProvider]:
    matched = capability_registry.get_providers_for_task(goal)
    all_providers: list[ExecutionProvider] = []
    seen: set[str] = set()
    for capability, providers in matched.items():
        for p in providers:
            if p.provider_id not in seen:
                all_providers.append(p)
                seen.add(p.provider_id)
    return all_providers


def find_agents_for_subgoal(subgoal: SubGoal, context: dict | None = None) -> list[BaseAgent]:
    goal_text = f"{subgoal.description} {subgoal.step_name or ''}"
    agents: list[BaseAgent] = []
    seen: set[str] = set()

    for candidate in _sorted_agents():
        if candidate.agent_id in seen:
            continue
        if candidate.can_handle(goal_text):
            agents.append(candidate)
            seen.add(candidate.agent_id)

    if not agents and subgoal.step_name:
        step_agent = _AGENT_REGISTRY.get(subgoal.step_name)
        if step_agent:
            agents.append(step_agent)

    return agents


def find_best_agent_for_subgoal(subgoal: SubGoal,
                                 step_name: str | None = None) -> BaseAgent | None:
    goal_text = f"{subgoal.description} {step_name or subgoal.step_name or ''}"
    for agent in _sorted_agents():
        if agent.can_handle(goal_text):
            return agent
    return None


def select_provider(
    goal: str,
    workflow_id: str = "",
    exclude: set[str] | None = None,
) -> ExecutionProvider | None:
    return provider_router.select_with_fallback(
        capability="coding",
        task={"goal": goal},
        workflow_id=workflow_id,
        exclude=exclude,
    )


class AgentRouter:
    def route(self, root: SubGoal, context: dict | None = None) -> list[dict]:
        leaves = root.flatten()
        tasks: list[dict] = []

        for leaf in leaves:
            agents = find_agents_for_subgoal(leaf, context)
            if not agents:
                logger.warning("Router: no agent for subgoal %s (%s)",
                               leaf.id, leaf.description[:60])
                continue
            for agent in agents:
                task = {
                    "agent_id": agent.agent_id,
                    "goal": leaf.description,
                    "step": leaf.step_name or agent.agent_id,
                    "parameters": dict(leaf.parameters),
                }

                providers = find_providers_for_goal(leaf.description)
                if providers:
                    task["providers"] = [p.provider_id for p in providers]
                    ranked = provider_router.select_with_fallback(
                        capability="coding" if any("coding" in p.capabilities().capability_names for p in providers) else leaf.step_name or "",
                        task={"goal": leaf.description},
                    )
                    if ranked:
                        task["selected_provider"] = ranked[0].provider_id

                tasks.append(task)

        return tasks

    def route_steps(self, steps: list[dict], context: dict | None = None) -> list[dict]:
        tasks: list[dict] = []
        for step in steps:
            step_name = step.get("name", "")
            agent = _AGENT_REGISTRY.get(step_name)
            if not agent:
                agent = find_agent_for_goal(step_name)
            if not agent:
                logger.warning("Router: no agent for step %s", step_name)
                continue
            task = {
                "agent_id": agent.agent_id,
                "goal": step.get("description", step_name),
                "step": step_name,
                "parameters": step.get("parameters", {}),
            }

            providers = find_providers_for_goal(step_name)
            if providers:
                task["providers"] = [p.provider_id for p in providers]

            tasks.append(task)

        return tasks
