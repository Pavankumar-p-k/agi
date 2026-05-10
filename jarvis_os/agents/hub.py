from __future__ import annotations

from .coding_agent import CodingAgent
from .debugging_agent import DebuggingAgent
from .planner_agent import PlannerAgent
from .research_agent import ResearchAgent


class AgentHub:
    def __init__(self, reasoning, planner, runtime_manager=None) -> None:
        self.reasoning = reasoning
        self.runtime_manager = runtime_manager
        self.agents = {
            "research": ResearchAgent(planner),
            "coding": CodingAgent(planner),
            "planning": PlannerAgent(planner),
            "debugging": DebuggingAgent(planner),
            "auto": PlannerAgent(planner),
        }
        if self.runtime_manager is not None:
            model_tasks = {
                "research_agent": "analysis",
                "coding_agent": "coding",
                "planner_agent": "reasoning",
                "debugging_agent": "coding",
            }
            for agent in self.agents.values():
                self.runtime_manager.register(agent.profile, model_task=model_tasks.get(agent.profile.name, "reasoning"))

    def select(self, intent_name: str, agent_name: str = "auto"):
        if agent_name != "auto" and agent_name in self.agents:
            return self.agents[agent_name]
        mapping = {
            "research": "research",
            "browser": "research",
            "coding": "coding",
            "filesystem": "planning",
            "automation": "planning",
            "system": "planning",
        }
        return self.agents[mapping.get(intent_name, "auto")]

    def collaborate(self, intent_name: str, agent_name: str = "auto") -> list:
        primary = self.select(intent_name, agent_name)
        collaborators = [primary]
        if primary.profile.name != "planner_agent":
            collaborators.append(self.agents["planning"])
        if intent_name in {"coding", "filesystem"}:
            collaborators.append(self.agents["debugging"])
        unique = []
        seen = set()
        for agent in collaborators:
            if agent.profile.name in seen:
                continue
            seen.add(agent.profile.name)
            unique.append(agent)
        return unique

    def runtime_context(self, profile_name: str) -> dict:
        if self.runtime_manager is None:
            return {}
        return self.runtime_manager.context_for(profile_name)

    def runtime_status(self, profile_name: str) -> dict | None:
        if self.runtime_manager is None:
            return None
        return self.runtime_manager.get(profile_name)
