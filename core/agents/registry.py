# Copyright (c) 2024-2026 JARVIS Project
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Central registry for all JARVIS sub-agents."""
from __future__ import annotations

import asyncio

from core.agents._legacy.atlas import AtlasAgent
from core.agents._legacy.cipher import CipherAgent
from core.agents._legacy.forge import ForgeAgent
from core.agents._legacy.herald import HeraldAgent
from core.agents._legacy.nexus import NexusAgent
from core.agents._legacy.oracle import OracleAgent
from core.agents._legacy.phantom import PhantomAgent
from core.agents._legacy.scribe import ScribeAgent
from core.agents._legacy.sentinel import SentinelAgent
from core.agents._sub_agent_base import AgentResult, SubAgent

_REGISTRY: dict[str, type[SubAgent]] = {
    "NEXUS":    NexusAgent,
    "FORGE":    ForgeAgent,
    "ORACLE":   OracleAgent,
    "PHANTOM":  PhantomAgent,
    "CIPHER":   CipherAgent,
    "HERALD":   HeraldAgent,
    "SCRIBE":   ScribeAgent,
    "ATLAS":    AtlasAgent,
    "SENTINEL": SentinelAgent,
}

class AgentRegistry:
    def get(self, name: str) -> type[SubAgent] | None:
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
