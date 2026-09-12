"""Acceptance tests for CodingToolBroker — real repo, real tools.

Proves that:
  [B-01] Broker discovers real tools in the environment (git, python)
  [B-02] Broker selects patch_applicator for MODIFY plans
  [B-03] Broker builds a working implementer that CodingAI.execute() can use
  [B-04] Broker's implementer is wired into execute() via the tool_selection action
  [B-05] External implementer still overrides the broker (backward-compat)
  [B-06] Broker + patch_applicator + test verification produces honest outcome
  [B-07] Broker selects NONE for empty plan → UNKNOWN result
  [B-08] Architecture: no CodingBrain/CodingMemory/CodingTaskGraph/CodingToolRegistry added
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from core.coding import (
    CapabilityInfo,
    ChangeType,
    CodingAI,
    CodingCapability,
    CodingConstraints,
    CodingStatus,
    CodingToolBroker,
    FileChange,
    ToolSelection,
)


def _skip_if_no_git(tc: unittest.TestCase) -> None:
    if shutil.which("git") is None:
        tc.skipTest("git not available")


def _py(code: str) -> str:
    return (
        f"{sys.executable} -c "
        f"\"import sys, os; sys.path.insert(0, os.getcwd()); {code}\""
    )


class _Repo:
    def __init__(self) -> None:
        self._tmp = Path(tempfile.mkdtemp())

    def write(self, rel: str, content: str) -> None:
        p = self._tmp / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")

    def read(self, rel: str) -> str:
        return (self._tmp / rel).read_text(encoding="utf-8")

    def git_init(self) -> None:
        subprocess.run("git init", cwd=self._tmp, shell=True, capture_output=True, check=True)
        subprocess.run("git add .", cwd=self._tmp, shell=True, capture_output=True, check=True)
        subprocess.run(
            "git -c user.name=Jarvis -c user.email=jarvis@example.test commit -m initial",
            cwd=self._tmp, shell=True, capture_output=True, check=True,
        )

    @property
    def root(self) -> Path:
        return self._tmp

    def cleanup(self) -> None:
        shutil.rmtree(self._tmp, ignore_errors=True)


class TestB01_BrokerDiscoverRealTools(unittest.TestCase):
    """[B-01] Broker discovers real tools: python always present, git if on PATH."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp()
        (Path(self._tmp) / "src").mkdir()
        (Path(self._tmp) / "src" / "m.py").write_text("x = 1\n", encoding="utf-8")
        self.ai = CodingAI(self._tmp)

    def tearDown(self) -> None:
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_patch_applicator_always_available(self) -> None:
        caps = self.ai.tool_broker.enumerate_available_tools()
        self.assertTrue(caps[CodingCapability.PATCH_APPLICATOR].available)
        self.assertIsNotNone(caps[CodingCapability.PATCH_APPLICATOR].binary)

    def test_shell_always_available(self) -> None:
        caps = self.ai.tool_broker.enumerate_available_tools()
        self.assertTrue(caps[CodingCapability.SHELL].available)

    def test_test_runner_always_available(self) -> None:
        caps = self.ai.tool_broker.enumerate_available_tools()
        self.assertTrue(caps[CodingCapability.TEST_RUNNER].available)

    def test_git_matches_system_path(self) -> None:
        caps = self.ai.tool_broker.enumerate_available_tools()
        expected = shutil.which("git") is not None
        self.assertEqual(caps[CodingCapability.GIT].available, expected)
        if expected:
            self.assertIsNotNone(caps[CodingCapability.GIT].binary)

    def test_capability_info_serialisable(self) -> None:
        caps = self.ai.tool_broker.enumerate_available_tools()
        for info in caps.values():
            d = info.to_dict()
            self.assertIsInstance(d, dict)
            self.assertIn("available", d)
            self.assertIn("capability", d)


class TestB02_BrokerSelectsCapability(unittest.TestCase):
    """[B-02] Broker selects the right capability for the plan type."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp()
        self.ai = CodingAI(self._tmp)

    def tearDown(self) -> None:
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_modify_plan_selects_patch_applicator_or_cli_agent(self) -> None:
        plan = self.ai.planner.plan(
            "fix module",
            [FileChange(ChangeType.MODIFY, "src/m.py", "fix")],
        )
        sel = self.ai.tool_broker.select_capability(plan)
        self.assertIn(sel.capability, {CodingCapability.PATCH_APPLICATOR, CodingCapability.CLI_AGENT})

    def test_delete_plan_selects_patch_applicator(self) -> None:
        plan = self.ai.planner.plan(
            "remove old module",
            [FileChange(ChangeType.DELETE, "src/old.py", "remove")],
        )
        sel = self.ai.tool_broker.select_capability(plan)
        self.assertEqual(sel.capability, CodingCapability.PATCH_APPLICATOR)

    def test_selection_has_rationale(self) -> None:
        plan = self.ai.planner.plan(
            "fix module",
            [FileChange(ChangeType.MODIFY, "src/m.py", "fix")],
        )
        sel = self.ai.tool_broker.select_capability(plan)
        self.assertIsInstance(sel.rationale, str)
        self.assertTrue(len(sel.rationale) > 0)

    def test_empty_plan_selects_none(self) -> None:
        from core.coding.change_planner import ChangePlan
        plan = ChangePlan(request="nothing", changes=[])
        sel = self.ai.tool_broker.select_capability(plan)
        self.assertEqual(sel.capability, CodingCapability.NONE)


class TestB03_BrokerBuildsImplementer(unittest.TestCase):
    """[B-03] Broker builds a callable implementer for real plans."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp()
        p = Path(self._tmp) / "src"
        p.mkdir()
        (p / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
        self.ai = CodingAI(self._tmp)
        self.ai.indexer.index(force=True)

    def tearDown(self) -> None:
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_modify_plan_returns_callable(self) -> None:
        plan = self.ai.planner.plan(
            "inspect calc",
            [FileChange(ChangeType.MODIFY, "src/calc.py", "inspect")],
        )
        impl = self.ai.tool_broker.build_implementer(plan)
        self.assertIsNotNone(impl)
        self.assertTrue(callable(impl))

    def test_implementer_returns_list_of_dicts(self) -> None:
        plan = self.ai.planner.plan(
            "inspect calc",
            [FileChange(ChangeType.MODIFY, "src/calc.py", "inspect")],
        )
        impl = self.ai.tool_broker.build_implementer(plan)
        records = impl(plan)
        self.assertIsInstance(records, list)
        self.assertGreater(len(records), 0)
        for r in records:
            self.assertIsInstance(r, dict)
            self.assertIn("tool", r)

    def test_empty_plan_returns_none(self) -> None:
        from core.coding.change_planner import ChangePlan
        plan = ChangePlan(request="nothing", changes=[])
        impl = self.ai.tool_broker.build_implementer(plan)
        self.assertIsNone(impl)


class TestB04_BrokerWiredIntoExecute(unittest.TestCase):
    """[B-04] Broker's tool_selection action appears in execute() result actions."""

    def setUp(self) -> None:
        _skip_if_no_git(self)
        self.repo = _Repo()
        self.repo.write("src/__init__.py", "")
        self.repo.write("src/calc.py", "def add(a, b):\n    return a + b\n")
        self.repo.git_init()

    def tearDown(self) -> None:
        self.repo.cleanup()

    def test_tool_selection_action_present_without_implementer(self) -> None:
        ai = CodingAI(self.repo.root)
        result = ai.execute(
            "Inspect calc",
            constraints=CodingConstraints(commands=[]),
            changes=[FileChange(ChangeType.MODIFY, "src/calc.py", "inspect")],
        )
        kinds = [a["kind"] for a in result.to_dict()["actions"]]
        self.assertIn("tool_selection", kinds)

    def test_tool_selection_action_has_evidence(self) -> None:
        ai = CodingAI(self.repo.root)
        result = ai.execute(
            "Inspect calc",
            constraints=CodingConstraints(commands=[]),
            changes=[FileChange(ChangeType.MODIFY, "src/calc.py", "inspect")],
        )
        sel_actions = [a for a in result.to_dict()["actions"] if a["kind"] == "tool_selection"]
        self.assertEqual(len(sel_actions), 1)
        evidence = sel_actions[0]["evidence"]
        self.assertIn("capability", evidence)
        self.assertIn("rationale", evidence)

    def test_tool_selection_before_implementation(self) -> None:
        ai = CodingAI(self.repo.root)
        result = ai.execute(
            "Inspect calc",
            constraints=CodingConstraints(commands=[]),
            changes=[FileChange(ChangeType.MODIFY, "src/calc.py", "inspect")],
        )
        kinds = [a["kind"] for a in result.to_dict()["actions"]]
        if "tool_selection" in kinds and "implementation" in kinds:
            self.assertLess(kinds.index("tool_selection"), kinds.index("implementation"))


class TestB05_ExternalImplementerOverridesBroker(unittest.TestCase):
    """[B-05] Injecting an external implementer bypasses the broker completely."""

    def setUp(self) -> None:
        _skip_if_no_git(self)
        self.repo = _Repo()
        self.repo.write("src/__init__.py", "")
        self.repo.write("src/calc.py", "def add(a, b):\n    return a - b\n")
        self.repo.git_init()

    def tearDown(self) -> None:
        self.repo.cleanup()

    def test_external_implementer_is_called_not_broker(self) -> None:
        ai = CodingAI(self.repo.root)
        called = {"n": 0}

        def my_impl(plan):
            called["n"] += 1
            return [{"file": "src/calc.py", "change": "custom"}]

        ai.execute(
            "Inspect calc",
            constraints=CodingConstraints(commands=[]),
            changes=[FileChange(ChangeType.MODIFY, "src/calc.py", "inspect")],
            implementer=my_impl,
        )
        self.assertEqual(called["n"], 1)

    def test_no_tool_selection_action_with_external_implementer(self) -> None:
        ai = CodingAI(self.repo.root)

        result = ai.execute(
            "Inspect calc",
            constraints=CodingConstraints(commands=[]),
            changes=[FileChange(ChangeType.MODIFY, "src/calc.py", "inspect")],
            implementer=lambda plan: [{"file": "src/calc.py", "change": "custom"}],
        )
        kinds = [a["kind"] for a in result.to_dict()["actions"]]
        self.assertNotIn("tool_selection", kinds,
            "tool_selection must not appear when external implementer is provided")


class TestB06_BrokerImplementerProducesHonestOutcome(unittest.TestCase):
    """[B-06] Broker implementer + verification → honest result (FAILED when test fails)."""

    def setUp(self) -> None:
        _skip_if_no_git(self)
        self.repo = _Repo()
        self.repo.write("src/__init__.py", "")
        self.repo.write("src/calc.py", "def add(a, b):\n    return a - b  # BUG\n")
        self.repo.git_init()

    def tearDown(self) -> None:
        self.repo.cleanup()

    def _test_cmd(self) -> str:
        return _py(
            "from src.calc import add; "
            "assert add(2, 3) == 5, f'got {add(2,3)}'; "
            "print('ok')"
        )

    def test_broker_implementer_with_failing_test_gives_failed_not_success(self) -> None:
        """Broker's patch_applicator implementer applies dry_run stubs — test still fails."""
        ai = CodingAI(self.repo.root)
        # No external implementer → broker handles it
        result = ai.execute(
            "Fix add function",
            constraints=CodingConstraints(
                commands=[self._test_cmd()],
                max_attempts=1,
            ),
            changes=[FileChange(ChangeType.MODIFY, "src/calc.py", "fix add")],
        )
        # The broker implementer does dry_run only (doesn't actually fix code)
        # → verification fails → FAILED
        self.assertEqual(result.status, CodingStatus.FAILED)
        self.assertNotEqual(result.status, CodingStatus.SUCCESS)

    def test_external_implementer_fixes_and_succeeds(self) -> None:
        """External implementer applies a real fix → SUCCESS."""
        ai = CodingAI(self.repo.root)

        def fix(plan):
            self.repo.write("src/calc.py", "def add(a, b):\n    return a + b\n")
            return [{"file": "src/calc.py", "change": "fix add"}]

        result = ai.execute(
            "Fix add function",
            constraints=CodingConstraints(commands=[self._test_cmd()]),
            changes=[FileChange(ChangeType.MODIFY, "src/calc.py", "fix add")],
            implementer=fix,
        )
        self.assertEqual(result.status, CodingStatus.SUCCESS)


class TestB07_EmptyPlanUnknown(unittest.TestCase):
    """[B-07] Empty plan → broker returns None → execute gives UNKNOWN."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp()

    def tearDown(self) -> None:
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_empty_changes_no_implementer_gives_unknown(self) -> None:
        ai = CodingAI(self._tmp)
        result = ai.execute(
            "Review codebase",
            constraints=CodingConstraints(commands=[]),
            changes=[],
        )
        self.assertEqual(result.status, CodingStatus.UNKNOWN)


class TestB08_ArchitectureInvariant(unittest.TestCase):
    """[B-08] No new brain/memory/graph/registry added by the broker."""

    def test_tool_broker_is_not_a_brain(self) -> None:
        self.assertNotIn("Brain", CodingToolBroker.__name__)
        self.assertNotIn("Memory", CodingToolBroker.__name__)

    def test_coding_module_still_has_no_forbidden_exports(self) -> None:
        import core.coding as pkg
        for forbidden in ("CodingBrain", "CodingMemory", "CodingTaskGraph", "CodingToolRegistry"):
            self.assertFalse(
                hasattr(pkg, forbidden),
                f"core.coding must not expose {forbidden}"
            )

    def test_coding_module_exports_broker_classes(self) -> None:
        import core.coding as pkg
        self.assertTrue(hasattr(pkg, "CodingToolBroker"))
        self.assertTrue(hasattr(pkg, "CodingCapability"))
        self.assertTrue(hasattr(pkg, "CapabilityInfo"))
        self.assertTrue(hasattr(pkg, "ToolSelection"))

    def test_broker_does_not_own_memory(self) -> None:
        """Broker has no memory attribute — it delegates to the owning AI."""
        import inspect
        src = inspect.getsource(CodingToolBroker)
        self.assertNotIn("self.memory", src)
        self.assertNotIn("self.brain", src)
        self.assertNotIn("self.task_graph", src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
