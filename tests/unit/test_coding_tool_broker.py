"""Unit tests for CodingToolBroker capability-selection layer.

Tests the broker in isolation using a minimal CodingAI stub — no real
filesystem, no real subprocess calls beyond what already runs in this process.
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.coding.change_planner import ChangePlan, ChangeType, FileChange
from core.coding.tool_broker import (
    CapabilityInfo,
    CodingCapability,
    CodingToolBroker,
    ToolSelection,
    _change_to_shell_cmd,
)


# ---------------------------------------------------------------------------
# Minimal stub for CodingAI (avoids heavy filesystem/db setup)
# ---------------------------------------------------------------------------

def _make_ai_stub(tmp_dir: str | None = None) -> MagicMock:
    """Return a minimal CodingAI mock suitable for broker construction."""
    tmp = tmp_dir or tempfile.mkdtemp()
    ai = MagicMock()
    ai.repository = Path(tmp)
    # refactoring engine stub that returns valid patches/snapshots
    ai.refactoring.generate_patches.return_value = []
    ai.refactoring.apply_patches.return_value = []
    return ai


def _plan(*changes: FileChange, request: str = "test") -> ChangePlan:
    return ChangePlan(request=request, changes=list(changes))


def _modify(path: str) -> FileChange:
    return FileChange(ChangeType.MODIFY, path, "test modify")


def _create(path: str) -> FileChange:
    return FileChange(ChangeType.CREATE, path, "test create")


def _delete(path: str) -> FileChange:
    return FileChange(ChangeType.DELETE, path, "test delete")


def _rename(src: str, dst: str) -> FileChange:
    return FileChange(ChangeType.RENAME, src, "test rename", new_file=dst)


# ===========================================================================
# Test: tool enumeration
# ===========================================================================

class TestEnumerateAvailableTools(unittest.TestCase):

    def setUp(self) -> None:
        self.ai = _make_ai_stub()
        self.broker = CodingToolBroker(self.ai)

    def test_returns_all_six_capabilities(self) -> None:
        caps = self.broker.enumerate_available_tools()
        expected = {
            CodingCapability.PATCH_APPLICATOR,
            CodingCapability.SHELL,
            CodingCapability.GIT,
            CodingCapability.TEST_RUNNER,
            CodingCapability.LINTER,
            CodingCapability.CLI_AGENT,
        }
        self.assertEqual(set(caps.keys()), expected)

    def test_patch_applicator_is_always_available(self) -> None:
        caps = self.broker.enumerate_available_tools()
        self.assertTrue(caps[CodingCapability.PATCH_APPLICATOR].available)

    def test_shell_is_always_available(self) -> None:
        caps = self.broker.enumerate_available_tools()
        self.assertTrue(caps[CodingCapability.SHELL].available)

    def test_test_runner_is_always_available(self) -> None:
        caps = self.broker.enumerate_available_tools()
        self.assertTrue(caps[CodingCapability.TEST_RUNNER].available)

    def test_git_availability_matches_system(self) -> None:
        caps = self.broker.enumerate_available_tools()
        expected = shutil.which("git") is not None
        self.assertEqual(caps[CodingCapability.GIT].available, expected)

    def test_results_are_cached(self) -> None:
        first = self.broker.enumerate_available_tools()
        second = self.broker.enumerate_available_tools()
        self.assertIs(first, second)

    def test_refresh_clears_cache(self) -> None:
        first = self.broker.enumerate_available_tools()
        second = self.broker.enumerate_available_tools(refresh=True)
        self.assertIsNot(first, second)

    def test_all_infos_have_to_dict(self) -> None:
        caps = self.broker.enumerate_available_tools()
        for cap, info in caps.items():
            d = info.to_dict()
            self.assertIn("capability", d)
            self.assertIn("available", d)


# ===========================================================================
# Test: capability selection
# ===========================================================================

class TestSelectCapability(unittest.TestCase):

    def setUp(self) -> None:
        self.ai = _make_ai_stub()
        self.broker = CodingToolBroker(self.ai)

    def test_empty_plan_selects_none(self) -> None:
        plan = _plan()
        sel = self.broker.select_capability(plan)
        self.assertEqual(sel.capability, CodingCapability.NONE)

    def test_single_modify_selects_patch_applicator(self) -> None:
        plan = _plan(_modify("src/a.py"))
        sel = self.broker.select_capability(plan)
        self.assertEqual(sel.capability, CodingCapability.PATCH_APPLICATOR)

    def test_all_modify_selects_patch_applicator(self) -> None:
        plan = _plan(_modify("a.py"), _modify("b.py"), _modify("c.py"))
        sel = self.broker.select_capability(plan)
        # 3 MODIFYs — could be CLI agent rule, but CLI agent not available in test env
        # patch_applicator is the deterministic fallback for MODIFY
        self.assertIn(sel.capability, {CodingCapability.PATCH_APPLICATOR, CodingCapability.CLI_AGENT})

    def test_delete_selects_patch_applicator(self) -> None:
        plan = _plan(_delete("src/old.py"))
        sel = self.broker.select_capability(plan)
        self.assertEqual(sel.capability, CodingCapability.PATCH_APPLICATOR)
        self.assertIn("DELETE", sel.rationale.upper())

    def test_rename_selects_patch_applicator(self) -> None:
        plan = _plan(_rename("src/old.py", "src/new.py"))
        sel = self.broker.select_capability(plan)
        self.assertEqual(sel.capability, CodingCapability.PATCH_APPLICATOR)
        self.assertIn("RENAME", sel.rationale.upper())

    def test_selection_has_rationale(self) -> None:
        plan = _plan(_modify("src/a.py"))
        sel = self.broker.select_capability(plan)
        self.assertTrue(sel.rationale, "Selection must have a non-empty rationale")

    def test_selection_has_to_dict(self) -> None:
        plan = _plan(_modify("src/a.py"))
        sel = self.broker.select_capability(plan)
        d = sel.to_dict()
        self.assertIn("capability", d)
        self.assertIn("rationale", d)
        self.assertIn("available", d)

    def test_cli_agent_selected_for_large_plan_when_available(self) -> None:
        """When a CLI agent is available, plans with >= 3 changes use it."""
        broker = CodingToolBroker(self.ai)
        # Force CLI agent as available by patching enumerate_available_tools
        fake_cli = CapabilityInfo(
            CodingCapability.CLI_AGENT, available=True, binary="/usr/bin/aider", notes="aider"
        )
        original = broker.enumerate_available_tools
        broker._capability_cache = {
            CodingCapability.PATCH_APPLICATOR: CapabilityInfo(CodingCapability.PATCH_APPLICATOR, available=True),
            CodingCapability.SHELL: CapabilityInfo(CodingCapability.SHELL, available=True),
            CodingCapability.GIT: CapabilityInfo(CodingCapability.GIT, available=True),
            CodingCapability.TEST_RUNNER: CapabilityInfo(CodingCapability.TEST_RUNNER, available=True),
            CodingCapability.LINTER: CapabilityInfo(CodingCapability.LINTER, available=False),
            CodingCapability.CLI_AGENT: fake_cli,
        }
        plan = _plan(_modify("a.py"), _modify("b.py"), _modify("c.py"))
        sel = broker.select_capability(plan)
        self.assertEqual(sel.capability, CodingCapability.CLI_AGENT)
        self.assertEqual(sel.fallback, CodingCapability.PATCH_APPLICATOR)

    def test_mixed_create_modify_selects_shell(self) -> None:
        """CREATE + MODIFY without enough changes for CLI agent → shell."""
        plan = _plan(_create("src/new.py"), _modify("src/a.py"))
        sel = self.broker.select_capability(plan)
        # With CLI agent unavailable (likely in test env), falls to shell
        self.assertIn(sel.capability, {CodingCapability.SHELL, CodingCapability.CLI_AGENT})


# ===========================================================================
# Test: build_implementer
# ===========================================================================

class TestBuildImplementer(unittest.TestCase):

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp()
        self.ai = _make_ai_stub(self._tmp)
        # Set up refactoring engine stub to return a real-ish patch
        from core.coding.refactoring_engine import CodePatch, RollbackSnapshot
        patch_obj = CodePatch("src/a.py", "test patch", "old", "new", "modify")
        snap = RollbackSnapshot("src/a.py", "old", True)
        self.ai.refactoring.generate_patches.return_value = [patch_obj]
        self.ai.refactoring.apply_patches.return_value = [snap]
        self.broker = CodingToolBroker(self.ai)

    def tearDown(self) -> None:
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_empty_plan_returns_none(self) -> None:
        plan = _plan()
        impl = self.broker.build_implementer(plan)
        self.assertIsNone(impl)

    def test_modify_plan_returns_callable(self) -> None:
        plan = _plan(_modify("src/a.py"))
        impl = self.broker.build_implementer(plan)
        self.assertIsNotNone(impl)
        self.assertTrue(callable(impl))

    def test_implementer_returns_list_of_dicts(self) -> None:
        plan = _plan(_modify("src/a.py"))
        impl = self.broker.build_implementer(plan)
        self.assertIsNotNone(impl)
        records = impl(plan)
        self.assertIsInstance(records, list)
        self.assertGreater(len(records), 0)
        for record in records:
            self.assertIsInstance(record, dict)

    def test_implementer_records_have_file_and_tool(self) -> None:
        plan = _plan(_modify("src/a.py"))
        impl = self.broker.build_implementer(plan)
        records = impl(plan)
        for record in records:
            self.assertIn("file", record)
            self.assertIn("tool", record)

    def test_implementer_records_tool_name(self) -> None:
        plan = _plan(_modify("src/a.py"))
        impl = self.broker.build_implementer(plan)
        records = impl(plan)
        # Should be patch_applicator or shell
        for record in records:
            self.assertIn(record["tool"], [
                CodingCapability.PATCH_APPLICATOR.value,
                CodingCapability.SHELL.value,
                CodingCapability.CLI_AGENT.value,
            ])

    def test_implementer_survives_refactoring_exception(self) -> None:
        """If RefactoringEngine raises, the implementer records an error dict, not an exception."""
        self.ai.refactoring.generate_patches.side_effect = RuntimeError("engine broken")
        plan = _plan(_modify("src/a.py"))
        impl = self.broker.build_implementer(plan)
        self.assertIsNotNone(impl)
        records = impl(plan)
        self.assertIsInstance(records, list)
        self.assertGreater(len(records), 0)
        # Must have captured the error
        self.assertTrue(any("error" in r for r in records))

    def test_shell_implementer_for_mixed_types(self) -> None:
        """Mixed create+modify with CLI agent unavailable falls through to shell."""
        plan = _plan(_create("src/new.py"), _modify("src/a.py"))
        impl = self.broker.build_implementer(plan)
        self.assertIsNotNone(impl)
        records = impl(plan)
        self.assertIsInstance(records, list)


# ===========================================================================
# Test: capability_summary
# ===========================================================================

class TestCapabilitySummary(unittest.TestCase):

    def setUp(self) -> None:
        self.ai = _make_ai_stub()
        self.broker = CodingToolBroker(self.ai)

    def test_summary_has_tools_key(self) -> None:
        s = self.broker.capability_summary()
        self.assertIn("tools", s)

    def test_summary_has_all_capability_keys(self) -> None:
        s = self.broker.capability_summary()
        for cap in CodingCapability:
            if cap == CodingCapability.NONE:
                continue
            self.assertIn(cap.value, s["tools"])

    def test_summary_has_environment_key(self) -> None:
        s = self.broker.capability_summary()
        self.assertIn("environment", s)
        self.assertIn("python", s["environment"])


# ===========================================================================
# Test: _change_to_shell_cmd helper
# ===========================================================================

class TestChangeToShellCmd(unittest.TestCase):

    def test_create_cmd(self) -> None:
        cmd = _change_to_shell_cmd(_create("src/new.py"))
        self.assertIn("src/new.py", cmd)

    def test_delete_cmd(self) -> None:
        cmd = _change_to_shell_cmd(_delete("src/old.py"))
        self.assertIn("rm", cmd)
        self.assertIn("src/old.py", cmd)

    def test_rename_cmd(self) -> None:
        cmd = _change_to_shell_cmd(_rename("src/a.py", "src/b.py"))
        self.assertIn("mv", cmd)
        self.assertIn("src/a.py", cmd)
        self.assertIn("src/b.py", cmd)

    def test_modify_cmd(self) -> None:
        cmd = _change_to_shell_cmd(_modify("src/c.py"))
        self.assertIn("src/c.py", cmd)


# ===========================================================================
# Test: CodingAI integration — broker is present and wired
# ===========================================================================

class TestCodingAIBrokerIntegration(unittest.TestCase):

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp()
        # Write a minimal Python file so indexer has something to work with
        src = Path(self._tmp) / "src"
        src.mkdir()
        (src / "module.py").write_text("def hello():\n    pass\n", encoding="utf-8")

    def tearDown(self) -> None:
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_coding_ai_has_tool_broker(self) -> None:
        from core.coding import CodingAI
        ai = CodingAI(self._tmp)
        self.assertIsNotNone(ai.tool_broker)
        self.assertIsInstance(ai.tool_broker, CodingToolBroker)

    def test_broker_knows_about_coding_ai_repo(self) -> None:
        from core.coding import CodingAI
        ai = CodingAI(self._tmp)
        caps = ai.tool_broker.enumerate_available_tools()
        self.assertIn(CodingCapability.PATCH_APPLICATOR, caps)

    def test_execute_without_implementer_uses_broker(self) -> None:
        """When no implementer is injected, execute() uses the broker and
        appends a tool_selection action."""
        from core.coding import CodingAI, CodingConstraints, ChangeType, FileChange
        ai = CodingAI(self._tmp)
        result = ai.execute(
            "Review module.py",
            constraints=CodingConstraints(commands=[]),
            changes=[FileChange(ChangeType.MODIFY, "src/module.py", "review")],
        )
        action_kinds = {a["kind"] for a in result.to_dict()["actions"]}
        # broker should have added a tool_selection action
        self.assertIn("tool_selection", action_kinds)

    def test_injected_implementer_still_works_unchanged(self) -> None:
        """Injecting an external implementer must work exactly as before the broker was added."""
        from core.coding import CodingAI, CodingConstraints, ChangeType, FileChange
        ai = CodingAI(self._tmp)
        called = {"n": 0}

        def my_implementer(plan):
            called["n"] += 1
            return [{"file": "src/module.py", "change": "custom impl"}]

        result = ai.execute(
            "Review module.py",
            constraints=CodingConstraints(commands=[]),
            changes=[FileChange(ChangeType.MODIFY, "src/module.py", "review")],
            implementer=my_implementer,
        )
        self.assertEqual(called["n"], 1, "External implementer must be called exactly once")
        # No tool_selection action when external implementer is provided
        action_kinds = [a["kind"] for a in result.to_dict()["actions"]]
        self.assertNotIn("tool_selection", action_kinds)

    def test_no_implementer_no_changes_empty_plan_gives_unknown(self) -> None:
        """Empty changes + no implementer + no commands = UNKNOWN."""
        from core.coding import CodingAI, CodingConstraints, CodingStatus
        ai = CodingAI(self._tmp)
        result = ai.execute(
            "Inspect codebase",
            constraints=CodingConstraints(commands=[]),
            changes=[],
        )
        self.assertEqual(result.status, CodingStatus.UNKNOWN)


if __name__ == "__main__":
    unittest.main(verbosity=2)
