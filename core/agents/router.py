"""Agent router — keyword-based goal routing with priority ordering.

Tool agents (priority 10) win over LLM adapters (priority 50) when both
match, so "build android app" dispatches to BuildAgent, not ForgeAdapter.
"""
from __future__ import annotations

from typing import Optional

from core.agents.base import BaseAgent
from core.agents.capabilities import CAPABILITIES

PRIORITY_TOOL = 10
PRIORITY_ADAPTER = 50


def _sorted_pairs() -> list[tuple[str, list[str], int]]:
    """All (agent_id, keywords, priority) sorted: tool agents before adapters."""
    from core.agents.capabilities import ADAPTER_AGENT_KEYWORDS, TOOL_AGENT_KEYWORDS
    pairs = [(aid, kws, PRIORITY_TOOL) for aid, kws in TOOL_AGENT_KEYWORDS.items()]
    pairs += [(aid, kws, PRIORITY_ADAPTER) for aid, kws in ADAPTER_AGENT_KEYWORDS.items()]
    return pairs


def find_agent_for_goal(goal: str) -> Optional[BaseAgent]:
    """First registered agent whose keywords match the goal (priority order)."""
    text = (goal or "").lower()
    if not text:
        return None
    from core.agents.registry import agent_registry
    for aid, _kws, _prio in _sorted_pairs():
        agent = agent_registry.get(aid)
        if agent is not None and agent.can_handle(goal):
            return agent
    return None


def find_agents_for_subgoal(subgoal: Any) -> list[BaseAgent]:
    """All agents matching a SubGoal (description first, then step_name)."""
    from core.agents.registry import agent_registry

    description = getattr(subgoal, "description", "") or ""
    step_name = getattr(subgoal, "step_name", "") or ""

    matches: list[BaseAgent] = []
    seen: set[str] = set()
    for aid, _kws, _prio in _sorted_pairs():
        agent = agent_registry.get(aid)
        if agent is None or aid in seen:
            continue
        if description and agent.can_handle(description):
            matches.append(agent)
            seen.add(aid)
    if not matches and step_name:
        agent = agent_registry.get(step_name)
        if agent is not None:
            matches.append(agent)
    return matches


def register_agent(agent: BaseAgent, replace: bool = True) -> None:
    """Register an agent instance in the global registry."""
    from core.agents.registry import agent_registry
    agent_registry.register(agent, replace=replace)


def get_agent(agent_id: str) -> Optional[BaseAgent]:
    """Look up a registered agent by id."""
    from core.agents.registry import agent_registry
    return agent_registry.get(agent_id)


def list_agents() -> list[BaseAgent]:
    """All registered agents sorted by priority."""
    from core.agents.registry import agent_registry
    return agent_registry.list()


# Backwards-compatible module-level registry views.
def _sorted_agents() -> list[BaseAgent]:
    return list_agents()


class _AgentRegistryView:
    """Dict-like view over registered agent ids (for legacy _AGENT_REGISTRY use)."""

    def keys(self) -> list[str]:
        return [a.agent_id for a in list_agents()]

    def items(self):
        return [(a.agent_id, a) for a in list_agents()]

    def values(self):
        return list_agents()

    def __iter__(self):
        return iter(self.keys())

    def __len__(self) -> int:
        return len(list_agents())

    def __contains__(self, agent_id: object) -> bool:
        return any(a.agent_id == agent_id for a in list_agents())

    def __getitem__(self, agent_id: str) -> Optional[BaseAgent]:
        return get_agent(agent_id)


_AGENT_REGISTRY = _AgentRegistryView()

__all__ = [
    "find_agent_for_goal", "find_agents_for_subgoal", "register_agent",
    "get_agent", "list_agents", "_sorted_agents", "_AGENT_REGISTRY",
    "PRIORITY_TOOL", "PRIORITY_ADAPTER",
]
