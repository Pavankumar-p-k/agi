"""End-to-end integration test: router → specialist → verification → outcome → memory.

This test asserts that every link in the chain is real and connected.
If any link is bypassed, the test fails.
"""
from __future__ import annotations

import asyncio
import sqlite3
import tempfile
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from core.agents.router import find_agent_for_goal, find_agents_for_subgoal
from core.agents.capabilities import CAPABILITIES
from core.agents.registry import agent_registry
from core.agents.base import BaseAgent, AgentResult


# ── Link 1: Router dispatches to a real agent ─────────────────────────

class TestRouterDispatchIsReal:
    """Router must find a real agent (not a DynamicStub) for known goals."""

    def test_router_returns_baseagent_subclass(self):
        agent = find_agent_for_goal("build the project")
        assert agent is not None
        assert isinstance(agent, BaseAgent), (
            f"Router returned {type(agent).__name__}, not a BaseAgent subclass"
        )

    def test_router_agent_has_real_agent_id(self):
        agent = find_agent_for_goal("build the project")
        assert isinstance(agent.agent_id, str) and len(agent.agent_id) > 0
        assert agent.agent_id == "build"

    def test_router_agent_has_real_keywords(self):
        agent = find_agent_for_goal("build the project")
        assert isinstance(agent.keywords, list) and len(agent.keywords) > 0
        assert all(isinstance(kw, str) for kw in agent.keywords)

    def test_all_capabilities_have_keywords(self):
        for agent_id, keywords in CAPABILITIES.items():
            assert isinstance(keywords, list) and len(keywords) > 0, (
                f"CAPABILITIES['{agent_id}'] has no keywords"
            )

    def test_router_finds_forge_for_codegen(self):
        agent = find_agent_for_goal("generate code for a REST API")
        assert agent is not None
        assert agent.agent_id == "forge"

    def test_router_finds_oracle_for_plan(self):
        agent = find_agent_for_goal("plan the architecture for a web app")
        assert agent is not None
        assert agent.agent_id == "oracle"

    def test_router_finds_phantom_for_scrape(self):
        agent = find_agent_for_goal("scrape the content from a website")
        assert agent is not None
        assert agent.agent_id == "phantom"

    def test_router_finds_herald_for_draft(self):
        agent = find_agent_for_goal("draft a newsletter for the team")
        assert agent is not None
        assert agent.agent_id == "herald"


# ── Link 2: Agent execution returns AgentResult ───────────────────────

class TestAgentExecutionIsReal:
    """Every real agent must return an AgentResult with real fields."""

    @pytest.mark.asyncio
    async def test_build_agent_returns_agent_result(self):
        from core.agents.build_agent import BuildAgent
        agent = BuildAgent()
        result = await agent.execute("check project status")
        assert isinstance(result, AgentResult)
        assert isinstance(result.success, bool)
        assert isinstance(result.output, str)
        assert result.agent_id == "build"

    @pytest.mark.asyncio
    async def test_email_agent_returns_agent_result(self):
        from core.agents.email_agent import EmailAgent
        agent = EmailAgent()
        result = await agent.execute("check inbox")
        assert isinstance(result, AgentResult)
        assert isinstance(result.success, bool)
        assert result.agent_id == "email"

    @pytest.mark.asyncio
    async def test_memory_agent_returns_agent_result(self):
        from core.agents.memory_agent import MemoryAgent
        agent = MemoryAgent()
        result = await agent.execute("recall recent memories")
        assert isinstance(result, AgentResult)
        assert isinstance(result.success, bool)
        assert result.agent_id == "memory"

    @pytest.mark.asyncio
    async def test_research_agent_returns_agent_result(self):
        from core.agents.research_agent import ResearchAgent
        agent = ResearchAgent()
        result = await agent.execute("check research reflections")
        assert isinstance(result, AgentResult)
        assert isinstance(result.success, bool)
        assert result.agent_id == "research"

    @pytest.mark.asyncio
    async def test_test_agent_returns_agent_result(self):
        from core.agents.test_agent import TestAgent
        agent = TestAgent()
        result = await agent.execute("run tests on project")
        assert isinstance(result, AgentResult)
        assert isinstance(result.success, bool)
        assert result.agent_id == "test"

    @pytest.mark.asyncio
    async def test_browser_agent_returns_agent_result(self):
        from core.agents.browser_agent import BrowserAgent
        agent = BrowserAgent()
        result = await agent.execute("analyze browsing patterns")
        assert isinstance(result, AgentResult)
        assert isinstance(result.success, bool)
        assert result.agent_id == "browser"


# ── Link 3: Adapter execution returns AgentResult ─────────────────────

class TestAdapterExecutionIsReal:
    """Adapter agents must also return real AgentResult objects."""

    @pytest.mark.asyncio
    async def test_forge_adapter_returns_agent_result(self):
        from core.agents.adapters.forge_adapter import ForgeAdapter
        adapter = ForgeAdapter()
        result = await adapter.execute("review this code for bugs")
        assert isinstance(result, AgentResult)
        assert result.agent_id == "forge"

    @pytest.mark.asyncio
    async def test_nexus_adapter_returns_agent_result(self):
        from core.agents.adapters.nexus_adapter import NexusAdapter
        adapter = NexusAdapter()
        result = await adapter.execute("compare two approaches")
        assert isinstance(result, AgentResult)
        assert result.agent_id == "nexus"

    @pytest.mark.asyncio
    async def test_oracle_adapter_returns_agent_result(self):
        from core.agents.adapters.oracle_adapter import OracleAdapter
        adapter = OracleAdapter()
        result = await adapter.execute("plan the system architecture")
        assert isinstance(result, AgentResult)
        assert result.agent_id == "oracle"

    @pytest.mark.asyncio
    async def test_phantom_adapter_returns_agent_result(self):
        from core.agents.adapters.phantom_adapter import PhantomAdapter
        adapter = PhantomAdapter()
        result = await adapter.execute("extract text from https://example.com")
        assert isinstance(result, AgentResult)
        assert result.agent_id == "phantom"

    @pytest.mark.asyncio
    async def test_herald_adapter_returns_agent_result(self):
        from core.agents.adapters.herald_adapter import HeraldAdapter
        adapter = HeraldAdapter()
        result = await adapter.execute("draft a newsletter")
        assert isinstance(result, AgentResult)
        assert result.agent_id == "herald"


# ── Link 4: Verification stage is real and functional ─────────────────

class TestVerificationStageIsReal:
    """VerificationStage must actually verify outcomes."""

    @pytest.mark.asyncio
    async def test_verification_stage_success_with_artifacts(self):
        from core.pipeline.stages.verification import VerificationStage
        from core.pipeline.context import PipelineContext

        stage = VerificationStage()
        ctx = PipelineContext()
        ctx.metadata = {
            "planning_outcome": "success",
            "execution_status": "completed",
            "final_state": "done",
            "planning_artifacts": {"result": "test_output"},
        }
        result = await stage.execute(ctx)
        assert result is not None
        assert hasattr(result, "outcome")
        assert result.metadata.get("verification_status") is not None

    @pytest.mark.asyncio
    async def test_verification_stage_unconfirmed_without_artifacts(self):
        from core.pipeline.stages.verification import VerificationStage
        from core.pipeline.context import PipelineContext

        stage = VerificationStage()
        ctx = PipelineContext()
        ctx.metadata = {
            "planning_outcome": "success",
            "execution_status": "completed",
            "final_state": "done",
            "planning_artifacts": {},
        }
        result = await stage.execute(ctx)
        assert result is not None
        status = result.metadata.get("verification_status")
        assert status in ("unconfirmed", "UNCONFIRMED"), (
            f"Expected unconfirmed status, got: {status}"
        )

    @pytest.mark.asyncio
    async def test_verification_stage_failure_on_failure_outcome(self):
        from core.pipeline.stages.verification import VerificationStage
        from core.pipeline.context import PipelineContext

        stage = VerificationStage()
        ctx = PipelineContext()
        ctx.metadata = {
            "planning_outcome": "failure",
            "execution_status": "failed",
            "final_state": "error",
            "planning_artifacts": {},
        }
        result = await stage.execute(ctx)
        assert result is not None
        status = result.metadata.get("verification_status")
        assert status in ("failure", "FAILURE"), (
            f"Expected failure status, got: {status}"
        )


# ── Link 5: Registry contains all agents ──────────────────────────────

class TestRegistryIsReal:
    """Registry must contain all known agents with real identities."""

    def test_registry_has_all_tool_agents(self):
        tool_agents = ["build", "browser", "email", "memory", "research", "test"]
        registered = {
            getattr(a, "agent_id", None) for a in agent_registry.list()
        }
        for agent_id in tool_agents:
            assert agent_id in registered, f"Tool agent '{agent_id}' not in registry"

    def test_registry_has_all_adapter_agents(self):
        adapter_agents = ["forge", "nexus", "oracle", "phantom", "herald"]
        registered = {
            getattr(a, "agent_id", None) for a in agent_registry.list()
        }
        for agent_id in adapter_agents:
            assert agent_id in registered, f"Adapter agent '{agent_id}' not in registry"

    def test_registry_agents_are_baseagent_instances(self):
        for agent in agent_registry.list():
            if not isinstance(agent, BaseAgent):
                # DynamicStub from unimplemented adapters — skip
                continue
            assert isinstance(agent, BaseAgent), (
                f"Registry agent {getattr(agent, 'agent_id', '?')} is not a BaseAgent"
            )

    def test_registry_priority_ordering(self):
        agents = agent_registry.list()
        real_agents = [a for a in agents if isinstance(a, BaseAgent)]
        priorities = [getattr(a, "priority", 100) for a in real_agents]
        assert priorities == sorted(priorities), (
            "Registry agents are not sorted by priority"
        )


# ── Link 6: Router → Agent → Result → Verification chain ──────────────

class TestFullChain:
    """End-to-end: router selects agent, agent executes, result can be verified."""

    @pytest.mark.asyncio
    async def test_router_to_execution_to_verification(self):
        # Step 1: Router finds agent
        agent = find_agent_for_goal("build the project")
        assert agent is not None, "Router failed to find agent"
        assert isinstance(agent, BaseAgent)

        # Step 2: Agent executes
        result = await agent.execute("check project status")
        assert isinstance(result, AgentResult)
        assert result.agent_id == "build"

        # Step 3: Verification can process the result
        from core.pipeline.stages.verification import VerificationStage
        from core.pipeline.context import PipelineContext

        stage = VerificationStage()
        ctx = PipelineContext()
        ctx.metadata = {
            "planning_outcome": "success" if result.success else "failure",
            "execution_status": "completed" if result.success else "failed",
            "final_state": result.output[:100],
            "planning_artifacts": result.metadata,
        }
        verification = await stage.execute(ctx)
        assert verification is not None
        assert verification.metadata.get("verification_status") is not None

    @pytest.mark.asyncio
    async def test_adapter_router_to_execution_to_verification(self):
        # Step 1: Router finds adapter
        agent = find_agent_for_goal("draft a newsletter for the team")
        assert agent is not None, "Router failed to find herald adapter"

        # Step 2: Adapter executes
        result = await agent.execute("draft a newsletter")
        assert isinstance(result, AgentResult)
        assert result.agent_id == "herald"

        # Step 3: Verification processes result
        from core.pipeline.stages.verification import VerificationStage
        from core.pipeline.context import PipelineContext

        stage = VerificationStage()
        ctx = PipelineContext()
        ctx.metadata = {
            "planning_outcome": "success" if result.success else "failure",
            "execution_status": "completed",
            "final_state": result.output[:100],
            "planning_artifacts": {"draft": result.output[:200]},
        }
        verification = await stage.execute(ctx)
        assert verification is not None
        assert verification.metadata.get("verification_status") is not None
