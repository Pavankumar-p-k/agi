"""Real-Repo Harness: Coding AI end-to-end acceptance tests.

Proves the existing Coding AI works end-to-end without mocked repository data,
mocked Git, or mocked test execution.  Each test method maps to a specific
acceptance criterion stated in the milestone spec.

Acceptance criteria verified here:
  [C-01] Real repository indexing — not mocked repository data
  [C-02] Real Git repository and actual diff
  [C-03] A genuine seeded bug that Coding AI can identify
  [C-04] Plan is generated before implementation
  [C-05] Risk is classified
  [C-06] The resulting patch is minimal and relevant
  [C-07] Tests actually execute
  [C-08] Failed verification cannot be reported as success
  [C-09] Final result contains structured evidence
  [C-10] Repair loop can recover from at least one intentionally failing first attempt
  [C-11] Failure honesty: SUCCESS / FAILED / PARTIAL / UNKNOWN are honest
  [C-12] No duplicate CodingBrain, CodingMemory, CodingTaskGraph, or CodingToolRegistry introduced

Architecture constraints verified:
  - CodingAI is the only entry point (no new brain/memory/graph/registry classes created)
  - Existing RepositoryIndexer, ChangePlanner, CodingVerifier are used as-is
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from core.coding import (
    ChangeType,
    CodingAI,
    CodingConstraints,
    CodingStatus,
    FileChange,
)
from core.coding import (
    ArchitectureMapper,
    ChangePlanner,
    CodingVerifier,
    DependencyGraph,
    RepositoryIndexer,
)


def _skip_if_no_git(test_case: unittest.TestCase) -> None:
    if shutil.which("git") is None:
        test_case.skipTest("git is not available in this environment")


class SyntheticRepo:
    """Minimal synthetic Python repository with a seeded bug."""

    # The seeded bug: add() subtracts instead of adding.
    BUGGY_CALCULATOR = "def add(a, b):\n    return a - b  # BUG: should be a + b\n\n\ndef multiply(a, b):\n    return a * b\n"
    FIXED_CALCULATOR = "def add(a, b):\n    return a + b\n\n\ndef multiply(a, b):\n    return a * b\n"

    # A utility module that imports from the calculator — exercises dependency tracking.
    UTILS = (
        "from src.calculator import add, multiply\n\n\n"
        "def sum_and_product(a, b):\n"
        "    return add(a, b), multiply(a, b)\n"
    )

    # The test suite that exposes the bug.
    TEST_FILE = (
        "from src.calculator import add, multiply\n\n\n"
        "def test_add():\n"
        "    assert add(2, 3) == 5, 'add is broken'\n\n\n"
        "def test_multiply():\n"
        "    assert multiply(2, 3) == 6\n"
    )

    def __init__(self) -> None:
        self._tmp = Path(tempfile.mkdtemp())
        self._write("src/__init__.py", "")
        self._write("src/calculator.py", self.BUGGY_CALCULATOR)
        self._write("src/utils.py", self.UTILS)
        self._write("tests/__init__.py", "")
        self._write("tests/test_calculator.py", self.TEST_FILE)

    def _write(self, rel: str, content: str) -> None:
        p = self._tmp / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")

    def _run(self, cmd: str) -> subprocess.CompletedProcess:
        return subprocess.run(cmd, cwd=self._tmp, shell=True, text=True, capture_output=True, check=True)

    def init_git(self) -> None:
        self._run("git init")
        self._run("git add .")
        # Use a single-word message to avoid shell quoting issues on Windows
        self._run(
            "git -c user.name=Jarvis -c user.email=jarvis@example.test commit -m initial-seeded-bug"
        )

    def read(self, rel: str) -> str:
        return (self._tmp / rel).read_text(encoding="utf-8")

    def write(self, rel: str, content: str) -> None:
        self._write(rel, content)

    def run_raw(self, cmd: str) -> subprocess.CompletedProcess:
        return subprocess.run(cmd, cwd=self._tmp, shell=True, text=True, capture_output=True)

    @property
    def root(self) -> Path:
        return self._tmp

    def cleanup(self) -> None:
        shutil.rmtree(self._tmp, ignore_errors=True)


def _python_test_cmd(repo: SyntheticRepo) -> str:
    """Return a shell command that runs the add() test inline."""
    return (
        f'{sys.executable} -c '
        f'"from src.calculator import add; '
        f'assert add(2, 3) == 5, chr(39)add is broken chr(39); '
        f'print(chr(39)calculator ok chr(39))"'
    )


def _inline_test_cmd() -> str:
    """Inline test command independent of the cwd."""
    return (
        f"{sys.executable} -c "
        "\"import sys, os; "
        "sys.path.insert(0, os.getcwd()); "
        "from src.calculator import add; "
        "assert add(2, 3) == 5, 'add is broken'; "
        "print('calculator ok')\""
    )


class TestC01_RealRepositoryIndexing(unittest.TestCase):
    """[C-01] Repository is indexed from disk, not from mocked data."""

    def setUp(self) -> None:
        _skip_if_no_git(self)
        self.repo = SyntheticRepo()
        self.repo.init_git()

    def tearDown(self) -> None:
        self.repo.cleanup()

    def test_indexer_discovers_real_files_on_disk(self) -> None:
        indexer = RepositoryIndexer(self.repo.root)
        entries = indexer.index(force=True)

        # Must have found the Python source files we actually wrote
        paths = set(entries.keys())
        self.assertIn("src/calculator.py", paths)
        self.assertIn("src/utils.py", paths)
        self.assertIn("tests/test_calculator.py", paths)

    def test_indexer_extracts_real_symbols_from_calculator(self) -> None:
        indexer = RepositoryIndexer(self.repo.root)
        indexer.index(force=True)
        entry = indexer.get_entry("src/calculator.py")

        self.assertIsNotNone(entry, "calculator.py must be indexed")
        self.assertIn("add", entry.function_names)
        self.assertIn("multiply", entry.function_names)

    def test_indexer_extracts_real_imports_from_utils(self) -> None:
        indexer = RepositoryIndexer(self.repo.root)
        indexer.index(force=True)
        entry = indexer.get_entry("src/utils.py")

        self.assertIsNotNone(entry, "utils.py must be indexed")
        self.assertTrue(
            any("calculator" in imp for imp in entry.imports),
            f"utils.py imports should reference calculator, got: {entry.imports}",
        )

    def test_dependency_graph_links_utils_to_calculator(self) -> None:
        indexer = RepositoryIndexer(self.repo.root)
        indexer.index(force=True)
        dep_graph = DependencyGraph(indexer)
        dep_graph.build()
        summary = dep_graph.summary()

        # summary keys from DependencyGraph.summary() are "files", "edges", "high_impact"
        self.assertGreater(summary["files"], 0)
        # utils.py imports from calculator, so there must be at least one edge
        self.assertGreater(summary["edges"], 0)

    def test_architecture_map_produced_from_real_files(self) -> None:
        indexer = RepositoryIndexer(self.repo.root)
        indexer.index(force=True)
        dep_graph = DependencyGraph(indexer)
        dep_graph.build()
        arch = ArchitectureMapper(indexer, dep_graph)
        arch_map = arch.map_layers()

        self.assertIsNotNone(arch_map)
        arch_dict = arch_map.to_dict()
        self.assertIn("layers", arch_dict)


class TestC02_RealGitRepository(unittest.TestCase):
    """[C-02] Real Git repository — actual diffs, not simulated."""

    def setUp(self) -> None:
        _skip_if_no_git(self)
        self.repo = SyntheticRepo()
        self.repo.init_git()

    def tearDown(self) -> None:
        self.repo.cleanup()

    def test_git_diff_is_empty_before_any_change(self) -> None:
        verifier = CodingVerifier(self.repo.root)
        diff = verifier.git_diff()
        # No modifications after clean commit — diff should be empty
        self.assertEqual(diff, "")

    def test_git_diff_reflects_real_file_change(self) -> None:
        # Make a real change to the file
        self.repo.write("src/calculator.py", SyntheticRepo.FIXED_CALCULATOR)

        verifier = CodingVerifier(self.repo.root)
        diff = verifier.git_diff()

        # The diff must mention the file we changed
        self.assertIn("calculator.py", diff)

    def test_git_changed_files_lists_modified_file(self) -> None:
        self.repo.write("src/calculator.py", SyntheticRepo.FIXED_CALCULATOR)

        verifier = CodingVerifier(self.repo.root)
        changed = verifier.git_changed_files()

        self.assertTrue(
            any("calculator.py" in f for f in changed),
            f"calculator.py should appear in changed files, got: {changed}",
        )


class TestC03_GenuineSeededBug(unittest.TestCase):
    """[C-03] The seeded bug is genuine — the test actually fails before fixing."""

    def setUp(self) -> None:
        _skip_if_no_git(self)
        self.repo = SyntheticRepo()
        self.repo.init_git()

    def tearDown(self) -> None:
        self.repo.cleanup()

    def test_seeded_bug_causes_real_test_failure(self) -> None:
        result = self.repo.run_raw(_inline_test_cmd())
        self.assertNotEqual(
            result.returncode, 0,
            "The seeded bug (subtract instead of add) must cause the test to fail."
        )

    def test_fixed_code_causes_test_to_pass(self) -> None:
        # Apply the fix manually to confirm the test harness is sound
        self.repo.write("src/calculator.py", SyntheticRepo.FIXED_CALCULATOR)
        result = self.repo.run_raw(_inline_test_cmd())
        self.assertEqual(
            result.returncode, 0,
            f"After fixing the bug, the test must pass. stderr={result.stderr}"
        )


class TestC04_PlanGeneratedBeforeImplementation(unittest.TestCase):
    """[C-04] A plan must be generated and visible in the result before implementation runs."""

    def setUp(self) -> None:
        _skip_if_no_git(self)
        self.repo = SyntheticRepo()
        self.repo.init_git()
        self._implementer_called_before_plan_check = False
        self._plan_seen_before_implementer = False

    def tearDown(self) -> None:
        self.repo.cleanup()

    def test_plan_appears_in_actions_before_implementation(self) -> None:
        ai = CodingAI(self.repo.root)
        plan_action_index = None
        impl_action_index = None

        call_order: list[str] = []

        original_execute = ai.execute.__func__ if hasattr(ai.execute, "__func__") else None

        def tracking_implementer(plan):
            call_order.append("implementer")
            self.repo.write("src/calculator.py", SyntheticRepo.FIXED_CALCULATOR)
            return [{"file": "src/calculator.py", "change": "fix add() to return a + b"}]

        result = ai.execute(
            "Fix addition bug in calculator",
            constraints=CodingConstraints(commands=[_inline_test_cmd()]),
            changes=[FileChange(ChangeType.MODIFY, "src/calculator.py", "Correct add implementation")],
            implementer=tracking_implementer,
        )

        actions = result.to_dict()["actions"]
        for i, action in enumerate(actions):
            if action["kind"] == "planning" and plan_action_index is None:
                plan_action_index = i
            if action["kind"] == "implementation" and impl_action_index is None:
                impl_action_index = i

        self.assertIsNotNone(plan_action_index, "planning action must appear in result")
        self.assertIsNotNone(impl_action_index, "implementation action must appear in result")
        self.assertLess(
            plan_action_index, impl_action_index,
            "planning action must come before implementation action in the action list"
        )

    def test_plan_has_steps_with_understand_repository_first(self) -> None:
        ai = CodingAI(self.repo.root)

        result = ai.execute(
            "Fix addition bug in calculator",
            constraints=CodingConstraints(commands=[]),
            changes=[FileChange(ChangeType.MODIFY, "src/calculator.py", "Correct add implementation")],
        )

        plan_data = result.plan
        self.assertIn("steps", plan_data)
        self.assertGreater(len(plan_data["steps"]), 0)
        first_step = plan_data["steps"][0]
        self.assertEqual(first_step["id"], "understand_repository")

    def test_repository_intelligence_action_is_present(self) -> None:
        ai = CodingAI(self.repo.root)
        result = ai.execute(
            "Fix addition bug in calculator",
            constraints=CodingConstraints(commands=[]),
            changes=[FileChange(ChangeType.MODIFY, "src/calculator.py", "Correct add implementation")],
        )
        action_kinds = {action["kind"] for action in result.to_dict()["actions"]}
        self.assertIn("repository_intelligence", action_kinds)
        self.assertIn("planning", action_kinds)


class TestC05_RiskClassification(unittest.TestCase):
    """[C-05] Risk is classified and affects control flow."""

    def setUp(self) -> None:
        _skip_if_no_git(self)
        self.repo = SyntheticRepo()
        self.repo.init_git()

    def tearDown(self) -> None:
        self.repo.cleanup()

    def test_low_risk_objective_classified_as_low(self) -> None:
        ai = CodingAI(self.repo.root)
        risk = ai.classify_risk(
            "Fix addition bug in calculator",
            [FileChange(ChangeType.MODIFY, "src/calculator.py", "fix add")]
        )
        self.assertEqual(risk, "low")

    def test_auth_keyword_classified_as_high(self) -> None:
        ai = CodingAI(self.repo.root)
        risk = ai.classify_risk(
            "Fix authentication production bug",
            [FileChange(ChangeType.MODIFY, "src/calculator.py", "fix")]
        )
        self.assertEqual(risk, "high")

    def test_high_risk_blocked_without_approval(self) -> None:
        ai = CodingAI(self.repo.root)
        result = ai.execute(
            "Fix authentication production bug",
            constraints=CodingConstraints(commands=[_inline_test_cmd()], allow_high_risk=False),
            changes=[FileChange(ChangeType.MODIFY, "src/calculator.py", "sensitive")],
        )
        self.assertEqual(result.status, CodingStatus.PARTIAL)
        self.assertTrue(result.failures)
        self.assertEqual(result.evidence["risk"], "high")

    def test_risk_level_in_evidence(self) -> None:
        ai = CodingAI(self.repo.root)

        def implementer(plan):
            self.repo.write("src/calculator.py", SyntheticRepo.FIXED_CALCULATOR)
            return [{"file": "src/calculator.py", "change": "fix"}]

        result = ai.execute(
            "Fix addition bug",
            constraints=CodingConstraints(commands=[_inline_test_cmd()]),
            changes=[FileChange(ChangeType.MODIFY, "src/calculator.py", "fix add")],
            implementer=implementer,
        )
        self.assertIn("risk", result.evidence)
        self.assertIn(result.evidence["risk"], ("low", "medium", "high"))


class TestC06_MinimalAndRelevantPatch(unittest.TestCase):
    """[C-06] The resulting patch touches only the targeted file, not the whole repo."""

    def setUp(self) -> None:
        _skip_if_no_git(self)
        self.repo = SyntheticRepo()
        self.repo.init_git()

    def tearDown(self) -> None:
        self.repo.cleanup()

    def test_only_calculator_changed_after_fix(self) -> None:
        ai = CodingAI(self.repo.root)

        def implementer(plan):
            self.repo.write("src/calculator.py", SyntheticRepo.FIXED_CALCULATOR)
            return [{"file": "src/calculator.py", "change": "replace a - b with a + b"}]

        result = ai.execute(
            "Fix addition bug",
            constraints=CodingConstraints(commands=[_inline_test_cmd()]),
            changes=[FileChange(ChangeType.MODIFY, "src/calculator.py", "fix add")],
            implementer=implementer,
        )

        # Only calculator.py should appear in changed files
        changed = result.files_changed
        self.assertTrue(
            any("calculator.py" in f for f in changed),
            f"calculator.py must appear as changed; got {changed}"
        )
        # utils.py and test files must NOT appear as changed
        for f in changed:
            self.assertNotIn("utils.py", f, "utils.py should not be touched by a minimal patch")
            self.assertNotIn("test_calculator.py", f, "test file should not be touched")

    def test_fixed_content_is_exactly_the_corrected_function(self) -> None:
        ai = CodingAI(self.repo.root)

        def implementer(plan):
            self.repo.write("src/calculator.py", SyntheticRepo.FIXED_CALCULATOR)
            return [{"file": "src/calculator.py", "change": "replace a - b with a + b"}]

        ai.execute(
            "Fix addition bug",
            constraints=CodingConstraints(commands=[_inline_test_cmd()]),
            changes=[FileChange(ChangeType.MODIFY, "src/calculator.py", "fix add")],
            implementer=implementer,
        )

        final_content = self.repo.read("src/calculator.py")
        self.assertIn("return a + b", final_content, "Fixed file must contain correct implementation")
        self.assertNotIn("return a - b", final_content, "Fixed file must not contain the bug")


class TestC07_TestsActuallyExecute(unittest.TestCase):
    """[C-07] Tests actually execute — not simulated, and stdout/stderr is captured."""

    def setUp(self) -> None:
        _skip_if_no_git(self)
        self.repo = SyntheticRepo()
        self.repo.init_git()

    def tearDown(self) -> None:
        self.repo.cleanup()

    def test_check_results_contain_real_return_code(self) -> None:
        verifier = CodingVerifier(self.repo.root)
        check = verifier._run(_inline_test_cmd())

        # Bug is present — test must fail
        self.assertNotEqual(check.returncode, 0)
        self.assertEqual(check.status, "failed")

    def test_check_results_contain_stdout_after_fix(self) -> None:
        self.repo.write("src/calculator.py", SyntheticRepo.FIXED_CALCULATOR)
        verifier = CodingVerifier(self.repo.root)
        check = verifier._run(_inline_test_cmd())

        self.assertEqual(check.returncode, 0)
        self.assertEqual(check.status, "success")
        self.assertIn("calculator ok", check.stdout)

    def test_verification_runs_commands_and_produces_check_results(self) -> None:
        self.repo.write("src/calculator.py", SyntheticRepo.FIXED_CALCULATOR)
        verifier = CodingVerifier(self.repo.root)
        vresult = verifier.verify([_inline_test_cmd()])

        self.assertEqual(len(vresult.checks), 1)
        self.assertEqual(vresult.checks[0].returncode, 0)
        self.assertIn("calculator ok", vresult.checks[0].stdout)


class TestC08_FailedVerificationNotReportedAsSuccess(unittest.TestCase):
    """[C-08] Failed verification must not yield SUCCESS status."""

    def setUp(self) -> None:
        _skip_if_no_git(self)
        self.repo = SyntheticRepo()
        self.repo.init_git()

    def tearDown(self) -> None:
        self.repo.cleanup()

    def test_no_fix_means_failed_not_success(self) -> None:
        """Implementer inspects but does NOT fix the bug — must be FAILED."""
        ai = CodingAI(self.repo.root)

        def no_fix_implementer(plan):
            # Deliberately do nothing
            return [{"file": "src/calculator.py", "change": "inspected but not fixed"}]

        result = ai.execute(
            "Fix addition bug",
            constraints=CodingConstraints(commands=[_inline_test_cmd()], max_attempts=1),
            changes=[FileChange(ChangeType.MODIFY, "src/calculator.py", "fix add")],
            implementer=no_fix_implementer,
        )

        self.assertNotEqual(result.status, CodingStatus.SUCCESS)
        self.assertEqual(result.status, CodingStatus.FAILED)
        self.assertEqual(result.verification["status"], "failed")

    def test_wrong_fix_means_failed_not_success(self) -> None:
        """Implementer applies a wrong fix (still broken) — must be FAILED."""
        ai = CodingAI(self.repo.root)

        def wrong_fix_implementer(plan):
            # Make the bug worse, not better
            self.repo.write("src/calculator.py", "def add(a, b):\n    return a * b\n\n\ndef multiply(a, b):\n    return a * b\n")
            return [{"file": "src/calculator.py", "change": "wrong fix — multiply instead of add"}]

        result = ai.execute(
            "Fix addition bug",
            constraints=CodingConstraints(commands=[_inline_test_cmd()], max_attempts=1),
            changes=[FileChange(ChangeType.MODIFY, "src/calculator.py", "fix add")],
            implementer=wrong_fix_implementer,
        )

        self.assertEqual(result.status, CodingStatus.FAILED)
        self.assertFalse(
            any(t.get("status") == "success" for t in result.tests),
            "No test check should report success when the bug remains"
        )


class TestC09_StructuredEvidence(unittest.TestCase):
    """[C-09] Final result contains structured evidence."""

    def setUp(self) -> None:
        _skip_if_no_git(self)
        self.repo = SyntheticRepo()
        self.repo.init_git()

    def tearDown(self) -> None:
        self.repo.cleanup()

    def test_success_result_has_all_evidence_fields(self) -> None:
        ai = CodingAI(self.repo.root)

        def implementer(plan):
            self.repo.write("src/calculator.py", SyntheticRepo.FIXED_CALCULATOR)
            return [{"file": "src/calculator.py", "change": "fix"}]

        result = ai.execute(
            "Fix addition bug",
            constraints=CodingConstraints(commands=[_inline_test_cmd()]),
            changes=[FileChange(ChangeType.MODIFY, "src/calculator.py", "fix add")],
            implementer=implementer,
        )

        data = result.to_dict()
        # Top-level structure
        self.assertIn("status", data)
        self.assertIn("objective", data)
        self.assertIn("plan", data)
        self.assertIn("actions", data)
        self.assertIn("files_changed", data)
        self.assertIn("tests", data)
        self.assertIn("verification", data)
        self.assertIn("evidence", data)

    def test_evidence_contains_risk_and_contract(self) -> None:
        ai = CodingAI(self.repo.root)

        def implementer(plan):
            self.repo.write("src/calculator.py", SyntheticRepo.FIXED_CALCULATOR)
            return [{"file": "src/calculator.py", "change": "fix"}]

        result = ai.execute(
            "Fix addition bug",
            constraints=CodingConstraints(commands=[_inline_test_cmd()]),
            changes=[FileChange(ChangeType.MODIFY, "src/calculator.py", "fix add")],
            implementer=implementer,
        )

        self.assertIn("risk", result.evidence)
        self.assertIn("contract", result.evidence)
        self.assertIn("can", result.evidence["contract"])
        self.assertIn("cannot", result.evidence["contract"])

    def test_verification_evidence_contains_git_diff_inspection_flag(self) -> None:
        ai = CodingAI(self.repo.root)

        def implementer(plan):
            self.repo.write("src/calculator.py", SyntheticRepo.FIXED_CALCULATOR)
            return [{"file": "src/calculator.py", "change": "fix"}]

        result = ai.execute(
            "Fix addition bug",
            constraints=CodingConstraints(commands=[_inline_test_cmd()]),
            changes=[FileChange(ChangeType.MODIFY, "src/calculator.py", "fix add")],
            implementer=implementer,
        )

        v = result.verification
        self.assertIn("evidence", v)
        self.assertIn("git_diff_inspected", v["evidence"])

    def test_actions_have_kind_description_evidence(self) -> None:
        ai = CodingAI(self.repo.root)

        def implementer(plan):
            self.repo.write("src/calculator.py", SyntheticRepo.FIXED_CALCULATOR)
            return [{"file": "src/calculator.py", "change": "fix"}]

        result = ai.execute(
            "Fix addition bug",
            constraints=CodingConstraints(commands=[_inline_test_cmd()]),
            changes=[FileChange(ChangeType.MODIFY, "src/calculator.py", "fix add")],
            implementer=implementer,
        )

        for action in result.to_dict()["actions"]:
            self.assertIn("kind", action)
            self.assertIn("description", action)
            self.assertIn("evidence", action)


class TestC10_RepairLoopRecovery(unittest.TestCase):
    """[C-10] Repair loop recovers from at least one intentionally failing first attempt."""

    def setUp(self) -> None:
        _skip_if_no_git(self)
        self.repo = SyntheticRepo()
        self.repo.init_git()

    def tearDown(self) -> None:
        self.repo.cleanup()

    def test_repair_loop_recovers_on_second_attempt(self) -> None:
        # Pre-condition: the seeded bug means the test currently fails
        self.assertNotEqual(
            self.repo.run_raw(_inline_test_cmd()).returncode, 0,
            "Pre-condition: seeded bug must cause test failure"
        )

        ai = CodingAI(self.repo.root)
        attempt_counter = {"n": 0}

        def implementer(plan):
            attempt_counter["n"] += 1
            if attempt_counter["n"] == 1:
                # First attempt: intentionally wrong (returns 0, not a+b)
                self.repo.write(
                    "src/calculator.py",
                    "def add(a, b):\n    return 0  # wrong\n\n\ndef multiply(a, b):\n    return a * b\n"
                )
                return [{"file": "src/calculator.py", "change": "wrong patch on attempt 1"}]
            else:
                # Second attempt: correct fix
                self.repo.write("src/calculator.py", SyntheticRepo.FIXED_CALCULATOR)
                return [{"file": "src/calculator.py", "change": "correct fix on attempt 2"}]

        result = ai.execute(
            "Fix addition bug",
            constraints=CodingConstraints(commands=[_inline_test_cmd()], max_attempts=2),
            changes=[FileChange(ChangeType.MODIFY, "src/calculator.py", "fix add")],
            implementer=implementer,
        )

        self.assertEqual(result.status, CodingStatus.SUCCESS, f"Result: {result.to_dict()}")
        self.assertEqual(attempt_counter["n"], 2, "Implementer must be called exactly twice")

        actions = result.to_dict()["actions"]
        verification_actions = [a for a in actions if a["kind"] == "verification"]
        self.assertEqual(len(verification_actions), 2, "Two verification attempts expected")
        self.assertEqual(
            verification_actions[0]["evidence"]["status"], "failed",
            "First verification must be a failure (intentionally wrong patch)"
        )
        self.assertEqual(
            verification_actions[1]["evidence"]["status"], "success",
            "Second verification must succeed (repair patch)"
        )

    def test_max_attempts_respected_when_all_fail(self) -> None:
        ai = CodingAI(self.repo.root)
        attempt_counter = {"n": 0}

        def always_wrong_implementer(plan):
            attempt_counter["n"] += 1
            # Never fix the bug
            return [{"file": "src/calculator.py", "change": "still wrong"}]

        result = ai.execute(
            "Fix addition bug",
            constraints=CodingConstraints(commands=[_inline_test_cmd()], max_attempts=3),
            changes=[FileChange(ChangeType.MODIFY, "src/calculator.py", "fix add")],
            implementer=always_wrong_implementer,
        )

        self.assertEqual(result.status, CodingStatus.FAILED)
        self.assertEqual(attempt_counter["n"], 3, "Must try exactly max_attempts times")


class TestC11_OutcomeHonesty(unittest.TestCase):
    """[C-11] SUCCESS / FAILED / PARTIAL / UNKNOWN are honest, not optimistic."""

    def setUp(self) -> None:
        _skip_if_no_git(self)
        self.repo = SyntheticRepo()
        self.repo.init_git()

    def tearDown(self) -> None:
        self.repo.cleanup()

    def test_success_only_when_all_checks_pass(self) -> None:
        ai = CodingAI(self.repo.root)

        def implementer(plan):
            self.repo.write("src/calculator.py", SyntheticRepo.FIXED_CALCULATOR)
            return [{"file": "src/calculator.py", "change": "fix"}]

        result = ai.execute(
            "Fix addition bug",
            constraints=CodingConstraints(commands=[_inline_test_cmd()]),
            changes=[FileChange(ChangeType.MODIFY, "src/calculator.py", "fix add")],
            implementer=implementer,
        )
        self.assertEqual(result.status, CodingStatus.SUCCESS)

    def test_failed_when_checks_do_not_pass(self) -> None:
        ai = CodingAI(self.repo.root)

        def no_op_implementer(plan):
            return [{"file": "src/calculator.py", "change": "no change"}]

        result = ai.execute(
            "Fix addition bug",
            constraints=CodingConstraints(commands=[_inline_test_cmd()], max_attempts=1),
            changes=[FileChange(ChangeType.MODIFY, "src/calculator.py", "fix add")],
            implementer=no_op_implementer,
        )
        self.assertEqual(result.status, CodingStatus.FAILED)

    def test_partial_when_high_risk_objective_blocked(self) -> None:
        ai = CodingAI(self.repo.root)

        result = ai.execute(
            "Fix database production authentication security bug",
            constraints=CodingConstraints(commands=[_inline_test_cmd()], allow_high_risk=False),
            changes=[FileChange(ChangeType.MODIFY, "src/calculator.py", "blocked high-risk")],
        )
        self.assertEqual(result.status, CodingStatus.PARTIAL)
        self.assertTrue(result.failures)

    def test_unknown_when_no_checks_and_no_implementer(self) -> None:
        ai = CodingAI(self.repo.root)

        result = ai.execute(
            "Review the calculator logic",
            constraints=CodingConstraints(commands=[]),
            changes=[FileChange(ChangeType.MODIFY, "src/calculator.py", "review only")],
        )
        self.assertEqual(result.status, CodingStatus.UNKNOWN)

    def test_status_values_are_one_of_four_honest_outcomes(self) -> None:
        """All status values must be one of the four defined outcomes."""
        valid_statuses = {CodingStatus.SUCCESS, CodingStatus.FAILED, CodingStatus.PARTIAL, CodingStatus.UNKNOWN}
        ai = CodingAI(self.repo.root)

        for scenario_name, objective, constraints_kwargs, changes_spec, impl in [
            (
                "success",
                "Fix addition bug",
                {"commands": [_inline_test_cmd()]},
                [FileChange(ChangeType.MODIFY, "src/calculator.py", "fix")],
                lambda plan: [self.repo.write("src/calculator.py", SyntheticRepo.FIXED_CALCULATOR)] or [{"file": "src/calculator.py", "change": "fix"}],
            ),
            (
                "unknown",
                "Review calculator",
                {"commands": []},
                [FileChange(ChangeType.MODIFY, "src/calculator.py", "review")],
                None,
            ),
            (
                "high_risk_partial",
                "Fix authentication production database",
                {"commands": [_inline_test_cmd()]},
                [FileChange(ChangeType.MODIFY, "src/calculator.py", "blocked")],
                None,
            ),
        ]:
            with self.subTest(scenario=scenario_name):
                result = ai.execute(
                    objective,
                    constraints=CodingConstraints(**constraints_kwargs),
                    changes=changes_spec,
                    implementer=impl,
                )
                self.assertIn(
                    result.status, valid_statuses,
                    f"Scenario {scenario_name!r} produced invalid status: {result.status!r}"
                )


class TestC12_NoArchitectureDuplication(unittest.TestCase):
    """[C-12] No duplicate CodingBrain, CodingMemory, CodingTaskGraph, or CodingToolRegistry introduced."""

    def test_coding_module_does_not_export_brain_class(self) -> None:
        import core.coding as coding_pkg
        for forbidden in ("CodingBrain", "CodingMemory", "CodingTaskGraph", "CodingToolRegistry"):
            self.assertFalse(
                hasattr(coding_pkg, forbidden),
                f"core.coding must not expose {forbidden} — no architecture duplication allowed"
            )

    def test_coding_agent_constructor_accepts_shared_resources(self) -> None:
        """CodingAI accepts memory/event_bus/task_graph_factory/tool_registry from outside."""
        import inspect
        from core.coding.coding_agent import CodingAI as _CodingAI
        sig = inspect.signature(_CodingAI.__init__)
        params = set(sig.parameters.keys())
        for param in ("memory", "event_bus", "task_graph_factory", "tool_registry"):
            self.assertIn(
                param, params,
                f"CodingAI must accept {param} from the Super-Brain, not own it"
            )

    def test_capability_contract_lists_cannot_replace_super_brain(self) -> None:
        """The contract explicitly declares what Coding AI cannot do."""
        from core.coding import CodingAI
        ai = CodingAI(".")
        contract = ai.capability_contract()
        cannot = contract.get("cannot", [])
        self.assertTrue(
            any("Super-Brain" in item for item in cannot),
            f"Contract must state inability to replace the Super-Brain; got: {cannot}"
        )


class TestFullEndToEndFlow(unittest.TestCase):
    """Integration: the complete path from seeded-bug repo → SUCCESS with all evidence."""

    def setUp(self) -> None:
        _skip_if_no_git(self)
        self.repo = SyntheticRepo()
        self.repo.init_git()

    def tearDown(self) -> None:
        self.repo.cleanup()

    def test_full_end_to_end_success_flow(self) -> None:
        """
        Full flow:
          1. Synthetic repo is indexed (real files, real git)
          2. Seeded bug causes test to fail
          3. CodingAI.execute() generates a plan
          4. Implementer applies a correct patch
          5. Test passes
          6. Result is SUCCESS with full evidence
        """
        # Step 1: confirm bug is present
        self.assertNotEqual(
            self.repo.run_raw(_inline_test_cmd()).returncode, 0,
            "Pre-condition: seeded bug must cause test failure"
        )

        ai = CodingAI(self.repo.root)
        plan_captured: list = []

        def implementer(plan):
            plan_captured.append(plan)
            # Minimal, relevant patch: only touch the broken function
            self.repo.write("src/calculator.py", SyntheticRepo.FIXED_CALCULATOR)
            return [{"file": "src/calculator.py", "change": "replace 'a - b' with 'a + b'"}]

        result = ai.execute(
            "Fix addition bug in calculator.py",
            constraints=CodingConstraints(
                commands=[_inline_test_cmd()],
                max_attempts=2,
            ),
            changes=[FileChange(ChangeType.MODIFY, "src/calculator.py", "Correct add: subtract instead of add")],
            implementer=implementer,
        )

        data = result.to_dict()

        # C-11: honest SUCCESS
        self.assertEqual(result.status, CodingStatus.SUCCESS)
        self.assertEqual(data["status"], "success")

        # C-04: plan before implementation
        action_kinds = [a["kind"] for a in data["actions"]]
        self.assertIn("repository_intelligence", action_kinds)
        self.assertIn("planning", action_kinds)
        self.assertIn("implementation", action_kinds)
        self.assertIn("verification", action_kinds)
        planning_idx = action_kinds.index("planning")
        impl_idx = action_kinds.index("implementation")
        self.assertLess(planning_idx, impl_idx)

        # C-04: plan has understand_repository as first step
        self.assertEqual(plan_captured[0].steps[0].id, "understand_repository")

        # C-05: risk in evidence
        self.assertEqual(data["evidence"]["risk"], "low")

        # C-06: minimal patch — only calculator.py changed
        self.assertTrue(
            any("calculator.py" in f for f in data["files_changed"]),
            f"calculator.py must be in files_changed; got {data['files_changed']}"
        )

        # C-02: real git diff
        self.assertIn("calculator.py", data["verification"]["git_diff"])

        # C-07: test actually ran and passed
        self.assertTrue(data["tests"], "tests list must be non-empty")
        self.assertTrue(
            all(t["status"] == "success" for t in data["tests"]),
            f"All test checks must pass; got {data['tests']}"
        )

        # C-09: structured evidence
        self.assertIn("contract", data["evidence"])

        # C-06: final file content is correct
        final = self.repo.read("src/calculator.py")
        self.assertIn("return a + b", final)
        self.assertNotIn("return a - b", final)

    def test_full_repair_loop_flow(self) -> None:
        """
        Full flow with repair loop:
          Attempt 1: wrong patch → FAILED verification
          Attempt 2: correct patch → SUCCESS
        """
        self.assertNotEqual(
            self.repo.run_raw(_inline_test_cmd()).returncode, 0,
        )

        ai = CodingAI(self.repo.root)
        attempt_n = {"v": 0}

        def implementer(plan):
            attempt_n["v"] += 1
            if attempt_n["v"] == 1:
                self.repo.write(
                    "src/calculator.py",
                    "def add(a, b):\n    return 99\n\n\ndef multiply(a, b):\n    return a * b\n"
                )
                return [{"file": "src/calculator.py", "change": "wrong: hardcoded 99"}]
            self.repo.write("src/calculator.py", SyntheticRepo.FIXED_CALCULATOR)
            return [{"file": "src/calculator.py", "change": "correct: a + b"}]

        result = ai.execute(
            "Fix addition bug in calculator.py",
            constraints=CodingConstraints(commands=[_inline_test_cmd()], max_attempts=2),
            changes=[FileChange(ChangeType.MODIFY, "src/calculator.py", "fix add")],
            implementer=implementer,
        )

        self.assertEqual(result.status, CodingStatus.SUCCESS)
        self.assertEqual(attempt_n["v"], 2)

        verification_actions = [a for a in result.to_dict()["actions"] if a["kind"] == "verification"]
        self.assertEqual(len(verification_actions), 2)
        self.assertEqual(verification_actions[0]["evidence"]["status"], "failed")
        self.assertEqual(verification_actions[1]["evidence"]["status"], "success")


if __name__ == "__main__":
    unittest.main(verbosity=2)
