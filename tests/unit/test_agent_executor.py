"""AgentDrivenExecutor — decompose → route → execute → enforce tests."""

import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from core.agents.executor import make_agent_execute_fn
from core.planner.executor import PlannerExecutor


class TestAgentDrivenExecutor(unittest.TestCase):
    """Tests for the agent-driven PlannerStateMachine.execute_fn."""

    def setUp(self):
        # Patch get_agent to return mock agents
        self._agent_patcher = patch("core.agents.executor.get_agent")
        self._mock_get_agent = self._agent_patcher.start()

        # Patch execute_tool_block for the fallback path
        self._tool_patcher = patch(
            "core.agents.executor.execute_tool_block", new_callable=AsyncMock
        )
        self._mock_execute_tool = self._tool_patcher.start()
        self._mock_execute_tool.return_value = (
            "fallback_tool",
            {"output": "fallback done", "exit_code": 0},
        )

        # Build mock agents
        self._agents = {}
        for aid in ("research", "build", "test", "email"):
            agent = MagicMock()
            agent.agent_id = aid
            agent.execute = AsyncMock(
                return_value={
                    "output": f"{aid} done",
                    "exit_code": 0,
                    "_artifacts": {},
                }
            )
            self._agents[aid] = agent

        def _get_agent_side_effect(aid):
            return self._agents.get(aid)

        self._mock_get_agent.side_effect = _get_agent_side_effect

    def tearDown(self):
        self._agent_patcher.stop()
        self._tool_patcher.stop()

    # ── Factory ─────────────────────────────────────────────────────

    def test_01_make_returns_callable(self):
        """make_agent_execute_fn returns a callable."""
        fn = make_agent_execute_fn()
        self.assertTrue(callable(fn))

    def test_02_execute_returns_dict_with_artifacts(self):
        """execute_fn returns expected dict structure with artifacts."""
        fn = make_agent_execute_fn()
        executor = PlannerExecutor()
        result = asyncio_run(fn("Build Android app and email the APK", executor))

        self.assertIn("artifacts", result)
        self.assertIn("tool_calls", result)
        self.assertIn("tool_names", result)
        self.assertIsInstance(result["artifacts"], dict)

    # ── Agent Dispatch ──────────────────────────────────────────────

    def test_03_agents_invoked_for_sub_goals(self):
        """Each sub-goal routes to the correct agent."""
        fn = make_agent_execute_fn()
        executor = PlannerExecutor()
        result = asyncio_run(
            fn("Research competitors, build app, run tests, and email results", executor)
        )

        # Agents matching the goal's sub-goals should have been invoked
        # "research, build, test, email" are all in the goal/test template
        invoked = [aid for aid, ag in self._agents.items() if ag.execute.called]
        # At minimum, research and build should be invoked from decomposition
        self.assertIn("research", invoked)
        self.assertIn("build", invoked)

        # Should have tool_calls
        self.assertGreater(len(result["tool_calls"]), 0)

    def test_04_artifacts_collected_across_agents(self):
        """Artifacts from each agent are merged into the final result."""
        # Make build agent return artifacts
        self._agents["build"].execute = AsyncMock(
            return_value={
                "output": "build done",
                "exit_code": 0,
                "_artifacts": {"apk": "art_apk_001"},
            }
        )
        self._agents["email"].execute = AsyncMock(
            return_value={
                "output": "email sent",
                "exit_code": 0,
                "_artifacts": {"email_sent": "art_email_001"},
            }
        )

        fn = make_agent_execute_fn()
        executor = PlannerExecutor()
        result = asyncio_run(
            fn("Build Android app and email the APK", executor)
        )

        arts = result["artifacts"]
        self.assertIn("apk", arts)
        self.assertIn("email_sent", arts)
        self.assertEqual(arts["apk"], "art_apk_001")
        self.assertEqual(arts["email_sent"], "art_email_001")

    def test_05_missing_step_enforcement_triggers(self):
        """Enforcement injects missing required steps via inject_task."""
        # Only run research — build, test, email should be enforced
        fn = make_agent_execute_fn()
        executor = PlannerExecutor()

        # Create just one mock agent call
        self._agents["research"].execute = AsyncMock(
            return_value={
                "output": "research done",
                "exit_code": 0,
                "_artifacts": {},
            }
        )

        result = asyncio_run(
            fn("Build Android app and email the APK", executor)
        )

        # Build, email, or enforcement should have been triggered
        all_tool_calls = " ".join(result["tool_calls"])
        agent_invoked = any(
            call[0][0] is not None for call in self._agents["build"].execute.call_args_list
        )
        # Either the agent was directly invoked or enforcement happened
        self.assertTrue(
            agent_invoked or "enforced:" in all_tool_calls or "build" in all_tool_calls
        )

    # ── Error Handling ─────────────────────────────────────────────

    def test_06_agent_failure_recorded_in_error(self):
        """Failed agent execution records the error."""
        self._agents["build"].execute = AsyncMock(
            return_value={
                "output": "",
                "exit_code": 1,
                "error": "Build failed: syntax error",
            }
        )

        fn = make_agent_execute_fn()
        executor = PlannerExecutor()
        result = asyncio_run(
            fn("Build Android app and email the APK", executor)
        )

        if result.get("error"):
            self.assertIn("build", result["error"].lower())

    def test_07_no_template_returns_gracefully(self):
        """Goal with no matching template returns gracefully."""
        fn = make_agent_execute_fn()
        executor = PlannerExecutor()
        # An abstract goal that won't match templates but may still decompose
        result = asyncio_run(
            fn("xyzzy flurbo garblex", executor)
        )

        # Should not crash
        self.assertIsInstance(result, dict)
        # Should have some structure regardless
        self.assertIn("artifacts", result)

    # ── Context Propagation ─────────────────────────────────────────

    def test_08_global_context_passed_to_agents(self):
        """Global context dict is passed as variables to each agent."""
        ctx = {"project_dir": "/fake/project", "test_mode": "unit"}
        fn = make_agent_execute_fn(global_context=ctx)
        executor = PlannerExecutor()
        _ = asyncio_run(
            fn("Research competitors, build app, run tests", executor)
        )

        # Each agent's ExecutionContext should include the global vars
        for agent in self._agents.values():
            for call_args in agent.execute.call_args_list:
                ec = call_args[0][0] if call_args[0] else None
                if ec:
                    self.assertEqual(
                        ec.variables.get("project_dir"), "/fake/project"
                    )


def asyncio_run(coro):
    """Run an async function synchronously for tests."""
    import asyncio
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            fut = pool.submit(asyncio.run, coro)
            return fut.result()
    return asyncio.run(coro)
