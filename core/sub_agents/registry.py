"""Central registry for all JARVIS sub-agents."""
from __future__ import annotations
import asyncio
from typing import Type, Optional
from core.sub_agents.base_agent import SubAgent, AgentResult

# Import all agents
from core.sub_agents.agents.nexus   import NexusAgent
from core.sub_agents.agents.forge   import ForgeAgent
from core.sub_agents.agents.oracle  import OracleAgent
from core.sub_agents.agents.phantom import PhantomAgent
from core.sub_agents.agents.cipher  import CipherAgent
from core.sub_agents.agents.herald  import HeraldAgent
from core.sub_agents.agents.scribe  import ScribeAgent
from core.sub_agents.agents.atlas   import AtlasAgent
from core.sub_agents.agents.sentinel import SentinelAgent
from core.sub_agents.agents.maestro import MaestroAgent

_REGISTRY: dict[str, Type[SubAgent]] = {
    "NEXUS":    NexusAgent,
    "FORGE":    ForgeAgent,
    "ORACLE":   OracleAgent,
    "PHANTOM":  PhantomAgent,
    "CIPHER":   CipherAgent,
    "HERALD":   HeraldAgent,
    "SCRIBE":   ScribeAgent,
    "ATLAS":    AtlasAgent,
    "SENTINEL": SentinelAgent,
    "MAESTRO":  MaestroAgent,
}

class AgentRegistry:
    def get(self, name: str) -> Optional[Type[SubAgent]]:
        return _REGISTRY.get(name.upper())

    def list_agents(self) -> list[dict]:
        return [cls().info() for cls in _REGISTRY.values()]

    def names(self) -> list[str]:
        return list(_REGISTRY.keys())

    async def run(self, agent_name: str, task: str, mode: str = None, **kwargs) -> AgentResult:
        cls = self.get(agent_name)
        if not cls:
            raise ValueError(f"Unknown agent: {agent_name}. Available: {self.names()}")
        agent = cls()
        return await agent.run(task, mode=mode, **kwargs)

    async def run_parallel(self, tasks: list[dict]) -> list[AgentResult]:
        """Run multiple agents in parallel.
        tasks = [{"agent": "NEXUS", "task": "...", "mode": "research"}, ...]
        """
        coros = [self.run(t["agent"], t["task"], t.get("mode"), **{k:v for k,v in t.items() if k not in ["agent", "task", "mode"]}) for t in tasks]
        return await asyncio.gather(*coros, return_exceptions=False)

agent_registry = AgentRegistry()
