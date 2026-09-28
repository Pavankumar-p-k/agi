"""Agent registry — singleton holding all 15 agent instances.

Registers 6 tool agents + 9 LLM specialist adapters at import time.
Each adapter's run() routes through core.llm_router (Ollama by default,
cloud providers when API keys are configured).
"""
from __future__ import annotations

import threading
from typing import Any, Optional


class AgentRegistry:
    """Thread-safe registry of agent instances."""

    def __init__(self) -> None:
        self._agents: dict[str, Any] = {}
        self._lock = threading.Lock()

    def register(self, agent: Any, replace: bool = True) -> Any:
        agent_id = getattr(agent, "agent_id", None)
        if not agent_id:
            raise ValueError("agent must define an agent_id")
        with self._lock:
            if agent_id in self._agents and not replace:
                return self._agents[agent_id]
            self._agents[agent_id] = agent
        return agent

    def get(self, agent_id: str) -> Optional[Any]:
        with self._lock:
            agent = self._agents.get(agent_id)
            if agent is None and agent_id:
                # Case-insensitive fallback: "ORACLE" -> "oracle"
                agent = self._agents.get(agent_id.lower())
            return agent

    def has(self, agent_id: str) -> bool:
        with self._lock:
            return agent_id in self._agents

    def list(self) -> list[Any]:
        """All registered agents sorted by priority (stable)."""
        with self._lock:
            agents = list(self._agents.values())
        return sorted(agents, key=lambda a: getattr(a, "priority", 100))

    def names(self) -> list[str]:
        """Registered ids sorted by priority.

        Specialist adapters report their uppercase NAME (NEXUS, FORGE, ...);
        tool agents report their lowercase agent_id.
        """
        out: list[str] = []
        for a in self.list():
            name = getattr(a, "NAME", None)
            if not name:
                inner = getattr(a, "agent", None)
                name = getattr(inner, "NAME", None)
            if not name and getattr(a, "priority", 10) >= 50:
                name = str(getattr(a, "agent_id", "?")).upper()
            out.append(str(name or getattr(a, "agent_id", "?")))
        return out

    def remove(self, agent_id: str) -> bool:
        with self._lock:
            return self._agents.pop(agent_id, None) is not None

    def __len__(self) -> int:
        with self._lock:
            return len(self._agents)

    async def run(self, agent_id: str, task: str, mode: str = "", **kwargs: Any):
        """Run one agent's specialist execution path and return its result."""
        agent = self.get(agent_id)
        if agent is None:
            from core.agents._sub_agent_base import AgentResult
            return AgentResult(success=False, output="",
                               agent_name=agent_id, error=f"Unknown agent: {agent_id}")
        # Adapters expose run(task, mode=...); tool agents expose execute(goal).
        if hasattr(agent, "run") and callable(getattr(agent, "run")):
            result = await agent.run(task, mode=mode, **kwargs)
        else:
            result = await agent.execute(task, **kwargs)
            # Normalize tool-agent AgentResult into the SubAgent shape the
            # registry contract uses (agent_name/mode/duration_s fields).
            if hasattr(result, "to_dict") and not hasattr(result, "agent_name"):
                from core.agents._sub_agent_base import AgentResult as _AR
                d = result.to_dict()
                result = _AR(
                    success=bool(d.get("success")),
                    output=str(d.get("output", "")),
                    agent_name=str(d.get("agent_id", agent_id)).upper(),
                    mode=mode,
                    duration_s=float(d.get("duration", 0.0)),
                    error=str(d.get("error", "")),
                )
        return result

    async def run_parallel(self, tasks: list[dict[str, Any]]) -> list[Any]:
        """Run multiple agent tasks concurrently, preserving input order."""
        import asyncio
        from core.agents._sub_agent_base import AgentResult

        async def _one(t: dict[str, Any]):
            agent_id = str(t.get("agent", t.get("agent_id", "")))
            task = str(t.get("task", ""))
            mode = str(t.get("mode", ""))
            agent = self.get(agent_id)
            if agent is None:
                return AgentResult(success=False, output="", agent_name=agent_id.upper(),
                                   error=f"Unknown agent: {agent_id}")
            try:
                if hasattr(agent, "run") and callable(getattr(agent, "run")):
                    return await agent.run(task, mode=mode)
                res = await agent.execute(task)
                d = res.to_dict() if hasattr(res, "to_dict") else {}
                if "agent_name" not in d:
                    return AgentResult(
                        success=bool(d.get("success")),
                        output=str(d.get("output", "")),
                        agent_name=str(d.get("agent_id", agent_id)).upper(),
                        mode=mode,
                        duration_s=float(d.get("duration", 0.0)),
                        error=str(d.get("error", "")),
                    )
                return res
            except Exception as exc:  # noqa: BLE001
                return AgentResult(success=False, output="", agent_name=agent_id.upper(),
                                   error=f"{type(exc).__name__}: {exc}")

        return list(await asyncio.gather(*[_one(t) for t in tasks]))


def _build_default_registry() -> AgentRegistry:
    registry = AgentRegistry()

    # 6 tool agents
    from core.agents.build_agent import BuildAgent
    from core.agents.email_agent import EmailAgent
    from core.agents.memory_agent import MemoryAgent
    from core.agents.research_agent import ResearchAgent
    from core.agents.test_agent import TestAgent
    from core.agents.browser_agent import BrowserAgent

    for cls in (BuildAgent, EmailAgent, MemoryAgent, ResearchAgent,
                TestAgent, BrowserAgent):
        registry.register(cls())

    # 9 LLM specialist adapters
    from core.agents.adapters.atlas_adapter import AtlasAdapter
    from core.agents.adapters.cipher_adapter import CipherAdapter
    from core.agents.adapters.forge_adapter import ForgeAdapter
    from core.agents.adapters.herald_adapter import HeraldAdapter
    from core.agents.adapters.nexus_adapter import NexusAdapter
    from core.agents.adapters.oracle_adapter import OracleAdapter
    from core.agents.adapters.phantom_adapter import PhantomAdapter
    from core.agents.adapters.scribe_adapter import ScribeAdapter
    from core.agents.adapters.sentinel_adapter import SentinelAdapter

    for cls in (ForgeAdapter, NexusAdapter, OracleAdapter, PhantomAdapter,
                CipherAdapter, HeraldAdapter, AtlasAdapter, ScribeAdapter,
                SentinelAdapter):
        registry.register(cls())

    return registry


agent_registry = _build_default_registry()

__all__ = ["AgentRegistry", "agent_registry"]
