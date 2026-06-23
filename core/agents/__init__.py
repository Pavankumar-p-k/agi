"""core.agents — Multi-Agent Graph for JARVIS.

Each agent owns a capability domain and follows the lifecycle:
  can_handle() → plan() → execute() → verify()

The AgentRouter matches planner sub-goals to agents and returns
execution plans consumable by WorkflowEngine.
"""

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
    SubAgentAdapter,
)
from core.agents.base import BaseAgent
from core.agents.browser_agent import BrowserAgent
from core.agents.build_agent import BuildAgent
from core.agents.capabilities import CAPABILITIES
from core.agents.email_agent import EmailAgent
from core.agents.events import AgentEvent
from core.agents.executor import make_agent_execute_fn, make_parallel_agent_execute_fn
from core.agents.graph import AgentExecutionGraph, GraphNode, NodeStatus, build_graph_from_tasks
from core.agents.memory_agent import MemoryAgent
from core.agents.research_agent import ResearchAgent
from core.agents.router import (
    AgentRouter,
    find_agent_for_goal,
    find_agents_for_subgoal,
    find_best_agent_for_subgoal,
    get_agent,
    list_agents,
    register_agent,
)
from core.agents.test_agent import TestAgent

__all__ = [
    "AgentExecutionGraph",
    "AgentRouter",
    "AgentEvent",
    "AtlasAdapter",
    "BaseAgent",
    "BrowserAgent",
    "BuildAgent",
    "CAPABILITIES",
    "CipherAdapter",
    "EmailAgent",
    "find_agent_for_goal",
    "find_best_agent_for_subgoal",
    "find_agents_for_subgoal",
    "ForgeAdapter",
    "get_agent",
    "GraphNode",
    "HeraldAdapter",
    "list_agents",
    "make_agent_execute_fn",
    "make_parallel_agent_execute_fn",
    "MemoryAgent",
    "NexusAdapter",
    "NodeStatus",
    "OracleAdapter",
    "PhantomAdapter",
    "register_agent",
    "ResearchAgent",
    "ScribeAdapter",
    "SentinelAdapter",
    "SubAgentAdapter",
    "TestAgent",
]
