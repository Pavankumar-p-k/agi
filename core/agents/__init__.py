"""JARVIS agent system: router, registry, tool agents, LLM specialist adapters."""
from core.agents.base import AgentResult, BaseAgent
from core.agents.capabilities import CAPABILITIES
from core.agents.registry import AgentRegistry, agent_registry
from core.agents.router import (
    find_agent_for_goal,
    find_agents_for_subgoal,
    get_agent,
    list_agents,
    register_agent,
)

__all__ = [
    "AgentResult", "BaseAgent", "CAPABILITIES", "AgentRegistry",
    "agent_registry", "find_agent_for_goal", "find_agents_for_subgoal",
    "get_agent", "list_agents", "register_agent",
]
