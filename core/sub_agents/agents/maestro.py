"""MAESTRO — Master orchestrator that routes tasks to the right sub-agent."""
from __future__ import annotations
import asyncio, json, re
from core.sub_agents.base_agent import SubAgent, AgentResult
from typing import Optional

MAESTRO_SYSTEM = (
    "You are MAESTRO, the master orchestration sub-agent inside Jarvis — Pavan's personal AI OS. "
    "Your role: analyze any user task and decide which sub-agent should handle it. "
    "\n\nAvailable agents:\n"
    "- NEXUS: research, analysis, comparisons, intelligence briefs\n"
    "- FORGE: code generation, debugging, refactoring, code explanation\n"
    "- ORACLE: planning, decomposition, prioritization, time estimates\n"
    "- PHANTOM: web scraping, URL content extraction, page monitoring\n"
    "- CIPHER: security audit, threat model, code security review\n"
    "- HERALD: message drafting, summaries, alerts, smart replies\n"
    "- ATLAS: data analysis, SQL queries, pandas code, visualizations\n"
    "- SCRIBE: documentation, reports, READMEs, changelogs\n"
    "- SENTINEL: system health, diagnostics, performance optimization\n"
    "\n"
    "Output ONLY valid JSON in this exact format (no prose, no markdown):\n"
    '{"agent": "AGENT_NAME", "mode": "mode_name", "reasoning": "one sentence", '
    '"confidence": 0.95, "subtasks": []}\n'
    "\n"
    "If the task needs multiple agents, list them in subtasks array: "
    '[{"agent": "NEXUS", "mode": "research", "input": "research X"}, ...]'
    "\nFor simple single-agent tasks, subtasks should be empty array []."
)

AGENT_KEYWORDS = {
    "NEXUS":   ["research", "find out", "what is", "who is", "compare", "analyze", "brief", "summarize topic"],
    "FORGE":   ["code", "write function", "implement", "debug", "fix bug", "refactor", "script", "program"],
    "ORACLE":  ["plan", "break down", "steps to", "prioritize", "estimate", "how long", "roadmap"],
    "PHANTOM": ["scrape", "website", "http", "url", "webpage", "extract from", "monitor site"],
    "CIPHER":  ["security", "vulnerability", "audit", "threat", "harden", "pentest", "secure"],
    "HERALD":  ["draft", "email", "message", "notify", "alert", "reply to", "write to"],
    "ATLAS":   ["data", "sql", "query", "pandas", "csv", "chart", "graph", "visualize"],
    "SCRIBE":  ["documentation", "readme", "report", "changelog", "docs", "write report"],
    "SENTINEL":["cpu", "memory", "system", "monitor", "health check", "performance", "optimize system"],
}

class MaestroAgent(SubAgent):
    NAME = "MAESTRO"
    DESCRIPTION = "Routes any task to the right sub-agent(s) and orchestrates multi-agent workflows"
    DEFAULT_MODE = "route"
    AVAILABLE_MODES = ["route", "orchestrate"]
    MAX_TOKENS = 500

    def get_system_prompt(self, mode: str) -> str:
        return MAESTRO_SYSTEM

    async def run(self, task: str, mode: Optional[str] = None, **kwargs) -> AgentResult:
        """Route task and optionally execute via the target agent."""
        route_result = await super().run(task, mode="route")
        if not route_result.success:
            return route_result

        try:
            # Clean output if it contains markdown markers
            clean_output = route_result.output.strip()
            if clean_output.startswith("```json"):
                clean_output = clean_output[7:-3].strip()
            elif clean_output.startswith("```"):
                clean_output = clean_output[3:-3].strip()
            routing = json.loads(clean_output)
        except json.JSONDecodeError:
            # Fallback: keyword matching
            routing = self._keyword_route(task)

        route_result.metadata["routing"] = routing

        if kwargs.get("execute", False):
            target_result = await self._execute_route(task, routing)
            route_result.metadata["execution"] = target_result.to_dict()
            route_result.output = target_result.output

        return route_result

    def _keyword_route(self, task: str) -> dict:
        task_lower = task.lower()
        scores = {}
        for agent, keywords in AGENT_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in task_lower)
            if score > 0:
                scores[agent] = score
        if not scores:
            return {"agent": "NEXUS", "mode": "research", "reasoning": "default fallback", "confidence": 0.4, "subtasks": []}
        best = max(scores, key=scores.get)
        return {"agent": best, "mode": self._default_mode(best), "reasoning": "keyword match", "confidence": 0.6, "subtasks": []}

    def _default_mode(self, agent_name: str) -> str:
        defaults = {"NEXUS":"research","FORGE":"generate","ORACLE":"plan","PHANTOM":"scrape",
                    "CIPHER":"audit","HERALD":"draft","ATLAS":"analyze","SCRIBE":"docs","SENTINEL":"diagnose"}
        return defaults.get(agent_name, "default")

    async def _execute_route(self, task: str, routing: dict) -> AgentResult:
        from core.sub_agents.registry import agent_registry
        agent_name = routing.get("agent", "NEXUS")
        mode = routing.get("mode", "default")
        agent_cls = agent_registry.get(agent_name)
        if not agent_cls:
            return AgentResult(self.id, "MAESTRO", "route", task, f"Unknown agent: {agent_name}", False, 0, 0)
        agent = agent_cls()
        return await agent.run(task, mode=mode)
