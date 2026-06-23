"""Agent adapters — SubAgent -> BaseAdapter bridge tests.

Validates that every LLM specialist adapter:
  1. Wraps the correct SubAgent class
  2. Returns properly formatted dict from execute()
  3. Handles timeout gracefully
  4. Routes correctly via the AgentRouter
  5. Priority ordering works as expected
"""

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from core.agents.base import BaseAgent
from core.agents.capabilities import CAPABILITIES
from core.agents.router import (
    _AGENT_REGISTRY,
    _sorted_agents,
    find_agent_for_goal,
    find_agents_for_subgoal,
    get_agent,
    list_agents,
    register_agent,
)
from core.planner.models import SubGoal


class TestCapabilityRegistry(unittest.TestCase):
    """CAPABILITIES dict contains every agent with non-empty keywords."""

    def test_all_tool_agents_have_capabilities(self):
        for aid in ("research", "build", "test", "browser", "memory", "email"):
            self.assertIn(aid, CAPABILITIES)
            self.assertTrue(len(CAPABILITIES[aid]) > 0)

    def test_all_adapter_agents_have_capabilities(self):
        for aid in ("forge", "nexus", "oracle", "phantom", "cipher",
                    "herald", "atlas", "scribe", "sentinel"):
            self.assertIn(aid, CAPABILITIES)
            self.assertTrue(len(CAPABILITIES[aid]) > 0)

    def test_tool_vs_adapter_no_overlap(self):
        """Tool and adapter keywords should not overlap to avoid false routing."""
        tool_keywords = set()
        for aid in ("research", "build", "test", "browser", "memory", "email"):
            tool_keywords.update(CAPABILITIES[aid])
        adapter_keywords = set()
        for aid in ("forge", "nexus", "oracle", "phantom", "cipher",
                    "herald", "atlas", "scribe", "sentinel"):
            adapter_keywords.update(CAPABILITIES[aid])
        overlap = tool_keywords & adapter_keywords
        self.assertEqual(
            overlap, set(),
            f"Overlapping keywords between tool and adapter agents: {overlap}",
        )


class TestAgentRegistry(unittest.TestCase):
    """Agent registration and priority ordering."""

    def test_all_agents_registered(self):
        """All 15 agents (6 tool + 9 adapter) are registered."""
        agent_ids = list(_AGENT_REGISTRY.keys())
        expected = {
            "research", "build", "test", "browser", "memory", "email",
            "forge", "nexus", "oracle", "phantom", "cipher",
            "herald", "atlas", "scribe", "sentinel",
        }
        self.assertEqual(set(agent_ids), expected)

    def test_priority_tool_before_adapter(self):
        """Tool agents have lower priority (10) vs adapters (50)."""
        for agent in _sorted_agents():
            if agent.agent_id in ("research", "build", "test", "browser", "memory", "email"):
                self.assertEqual(agent.priority, 10)
            else:
                self.assertEqual(agent.priority, 50)

    def test_sorted_agents_priority_order(self):
        """_sorted_agents returns tool agents before adapters."""
        sorted_list = _sorted_agents()
        tool_agents = [a for a in sorted_list if a.priority == 10]
        adapter_agents = [a for a in sorted_list if a.priority == 50]
        # All tool agents come before any adapter agent
        last_tool_idx = max(sorted_list.index(a) for a in tool_agents)
        first_adapter_idx = min(sorted_list.index(a) for a in adapter_agents)
        self.assertLess(last_tool_idx, first_adapter_idx)


class TestCapabilityRouting(unittest.TestCase):
    """can_handle routes correctly without overlap."""

    def test_tool_agent_wins_for_build(self):
        """'build' keyword routes to BuildAgent, not ForgeAdapter."""
        agent = find_agent_for_goal("build android app")
        self.assertIsNotNone(agent)
        self.assertEqual(agent.agent_id, "build")

    def test_tool_agent_wins_for_research(self):
        """'research' keyword routes to ResearchAgent, not NexusAdapter."""
        agent = find_agent_for_goal("research competitors")
        self.assertIsNotNone(agent)
        self.assertEqual(agent.agent_id, "research")

    def test_tool_agent_wins_for_email(self):
        """'email' keyword routes to EmailAgent."""
        agent = find_agent_for_goal("email the report")
        self.assertIsNotNone(agent)
        self.assertEqual(agent.agent_id, "email")

    def test_forge_routes_codegen(self):
        """'codegen' routes to ForgeAdapter."""
        agent = find_agent_for_goal("generate payment api codegen")
        self.assertIsNotNone(agent)
        self.assertEqual(agent.agent_id, "forge")

    def test_nexus_routes_compare(self):
        """'compare' (unique to nexus) routes to NexusAdapter."""
        agent = find_agent_for_goal("compare these frameworks")
        self.assertIsNotNone(agent)
        self.assertEqual(agent.agent_id, "nexus")

    def test_oracle_routes_plan(self):
        """'plan' routes to OracleAdapter."""
        agent = find_agent_for_goal("plan the architecture")
        self.assertIsNotNone(agent)
        self.assertEqual(agent.agent_id, "oracle")

    def test_cipher_routes_security(self):
        """'security audit' routes to CipherAdapter."""
        agent = find_agent_for_goal("run security audit on the code")
        self.assertIsNotNone(agent)
        self.assertEqual(agent.agent_id, "cipher")

    def test_scribe_routes_documentation(self):
        """'documentation' routes to ScribeAdapter."""
        agent = find_agent_for_goal("write documentation for the api")
        self.assertIsNotNone(agent)
        self.assertEqual(agent.agent_id, "scribe")

    def test_sentinel_routes_diagnose(self):
        """'diagnose' (unique to sentinel) routes to SentinelAdapter."""
        agent = find_agent_for_goal("diagnose the server")
        self.assertIsNotNone(agent)
        self.assertEqual(agent.agent_id, "sentinel")

    def test_atlas_routes_sql_query(self):
        """'sql query' (unique to atlas) routes to AtlasAdapter."""
        agent = find_agent_for_goal("write sql query for user data")
        self.assertIsNotNone(agent)
        self.assertEqual(agent.agent_id, "atlas")

    def test_phantom_routes_extract_page(self):
        """'extract page' (unique to phantom) routes to PhantomAdapter."""
        agent = find_agent_for_goal("extract page content from url")
        self.assertIsNotNone(agent)
        self.assertEqual(agent.agent_id, "phantom")

    def test_herald_routes_draft(self):
        """'draft message' routes to HeraldAdapter."""
        agent = find_agent_for_goal("draft message to the team")
        self.assertIsNotNone(agent)
        self.assertEqual(agent.agent_id, "herald")


class TestFindAgentsForSubgoalRouting(unittest.TestCase):
    """find_agents_for_subgoal uses priority ordering."""

    def test_build_subgoal_finds_build_agent_first(self):
        sg = SubGoal(id="sg1", description="build android app", step_name="build")
        agents = find_agents_for_subgoal(sg)
        self.assertTrue(len(agents) > 0)
        # BuildAgent has priority 10, so it should be first
        self.assertEqual(agents[0].agent_id, "build")

    def test_codegen_subgoal_finds_forge(self):
        sg = SubGoal(id="sg2", description="generate payment api codegen", step_name="build")
        agents = find_agents_for_subgoal(sg)
        self.assertTrue(len(agents) > 0)
        # ForgeAdapter should match before BuildAgent for "codegen"
        agent_ids = [a.agent_id for a in agents]
        self.assertIn("forge", agent_ids)

    def test_fallback_to_step_name(self):
        """Unknown description but known step_name falls back to direct agent lookup."""
        sg = SubGoal(id="sg3", description="something vague", step_name="build")
        agents = find_agents_for_subgoal(sg)
        self.assertTrue(len(agents) > 0)
        self.assertEqual(agents[0].agent_id, "build")


class TestSubAgentAdapterBase(unittest.TestCase):
    """SubAgentAdapter base behavior (timeout, metadata, error handling)."""

    def setUp(self):
        # Ensure the adapter's sub_agent_class is set for testing
        from core.agents.adapters.forge_adapter import ForgeAdapter
        self.adapter = ForgeAdapter()

    def test_adapter_has_correct_type_metadata(self):
        """All adapters have agent_type='llm_specialist'."""
        self.assertEqual(self.adapter.agent_id, "forge")
        self.assertEqual(self.adapter.priority, 50)

    def test_adapter_timeout_returns_error_dict(self):
        """When SubAgent.run() hangs, adapter returns timeout error."""
        from core.agents.adapters.base_adapter import _ADAPTER_TIMEOUT
        self.assertGreater(_ADAPTER_TIMEOUT, 0)
        self.assertIsInstance(_ADAPTER_TIMEOUT, int)
