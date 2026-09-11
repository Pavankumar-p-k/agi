import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from core.coding import ChangeType, CodingAI, CodingConstraints, CodingStatus, FileChange


class TestCodingAIRealRepoHarness(unittest.TestCase):
    def setUp(self):
        if shutil.which("git") is None:
            self.skipTest("git is required for the real-repo Coding AI harness")
        self._tmp = Path(tempfile.mkdtemp())
        self._write("src/calculator.py", "def add(a, b):\n    return a - b\n")
        self._write(
            "tests/check_calculator.py",
            "from src.calculator import add\n\n"
            "assert add(2, 3) == 5\n"
            "print('calculator behavior verified')\n",
        )
        self._run("git init")
        self._run("git add .")
        self._run("git -c user.name=Jarvis -c user.email=jarvis@example.test commit -m initial")

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _write(self, relative_path: str, content: str) -> None:
        path = self._tmp / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def _read(self, relative_path: str) -> str:
        return (self._tmp / relative_path).read_text(encoding="utf-8")

    def _run(self, command: str) -> subprocess.CompletedProcess:
        return subprocess.run(command, cwd=self._tmp, shell=True, text=True, capture_output=True, check=True)

    def _test_command(self) -> str:
        return f'{sys.executable} -c "from src.calculator import add; assert add(2, 3) == 5; print(\'calculator behavior verified\')"'

    def _run_check(self) -> subprocess.CompletedProcess:
        return subprocess.run(self._test_command(), cwd=self._tmp, shell=True, text=True, capture_output=True)

    def test_success_path_uses_real_repo_git_diff_tests_and_evidence(self):
        self.assertNotEqual(self._run_check().returncode, 0)
        ai = CodingAI(self._tmp)

        def implementer(plan):
            self.assertTrue(plan.steps)
            self.assertEqual(plan.steps[0].id, "understand_repository")
            path = self._tmp / "src/calculator.py"
            original = path.read_text(encoding="utf-8")
            path.write_text(original.replace("return a - b", "return a + b"), encoding="utf-8")
            return [{"file": "src/calculator.py", "change": "replace subtraction with addition"}]

        result = ai.execute(
            "Fix addition bug",
            constraints=CodingConstraints(commands=[self._test_command()]),
            changes=[FileChange(ChangeType.MODIFY, "src/calculator.py", "Correct add implementation")],
            implementer=implementer,
        )
        data = result.to_dict()

        self.assertEqual(result.status, CodingStatus.SUCCESS)
        self.assertEqual(data["verification"]["status"], "success")
        self.assertTrue(data["tests"])
        self.assertIn("src/calculator.py", data["files_changed"])
        self.assertIn("calculator.py", data["verification"]["git_diff"])
        self.assertEqual(self._read("src/calculator.py"), "def add(a, b):\n    return a + b\n")
        self.assertEqual(data["evidence"]["risk"], "low")
        self.assertTrue(any(action["kind"] == "planning" for action in data["actions"]))
        self.assertTrue(any(action["kind"] == "repository_intelligence" for action in data["actions"]))

    def test_failed_verification_cannot_be_reported_as_success(self):
        self.assertNotEqual(self._run_check().returncode, 0)
        ai = CodingAI(self._tmp)

        def implementer(plan):
            return [{"file": "src/calculator.py", "change": "inspected but did not fix"}]

        result = ai.execute(
            "Fix addition bug",
            constraints=CodingConstraints(commands=[self._test_command()], max_attempts=1),
            changes=[FileChange(ChangeType.MODIFY, "src/calculator.py", "Correct add implementation")],
            implementer=implementer,
        )

        self.assertEqual(result.status, CodingStatus.FAILED)
        self.assertEqual(result.verification["status"], "failed")
        self.assertTrue(result.failures)

    def test_unknown_when_no_implementation_or_checks_establish_outcome(self):
        ai = CodingAI(self._tmp)

        result = ai.execute(
            "Review addition behavior",
            constraints=CodingConstraints(commands=[]),
            changes=[FileChange(ChangeType.MODIFY, "src/calculator.py", "Review add implementation")],
        )

        self.assertEqual(result.status, CodingStatus.UNKNOWN)
        self.assertEqual(result.verification["status"], "unknown")

    def test_partial_when_high_risk_requires_approval(self):
        ai = CodingAI(self._tmp)

        result = ai.execute(
            "Fix authentication production bug",
            constraints=CodingConstraints(commands=[self._test_command()]),
            changes=[FileChange(ChangeType.MODIFY, "src/calculator.py", "Sensitive objective should pause")],
        )

        self.assertEqual(result.status, CodingStatus.PARTIAL)
        self.assertTrue(result.failures)
        self.assertEqual(result.evidence["risk"], "high")

    def test_repair_loop_recovers_after_intentionally_wrong_first_patch(self):
        self.assertNotEqual(self._run_check().returncode, 0)
        ai = CodingAI(self._tmp)
        attempts = {"count": 0}

        def implementer(plan):
            attempts["count"] += 1
            path = self._tmp / "src/calculator.py"
            if attempts["count"] == 1:
                path.write_text("def add(a, b):\n    return 0\n", encoding="utf-8")
                return [{"file": "src/calculator.py", "change": "intentional wrong first patch"}]
            path.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
            return [{"file": "src/calculator.py", "change": "repair add implementation"}]

        result = ai.execute(
            "Fix addition bug",
            constraints=CodingConstraints(commands=[self._test_command()], max_attempts=2),
            changes=[FileChange(ChangeType.MODIFY, "src/calculator.py", "Correct add implementation")],
            implementer=implementer,
        )
        verification_actions = [action for action in result.to_dict()["actions"] if action["kind"] == "verification"]

        self.assertEqual(result.status, CodingStatus.SUCCESS)
        self.assertEqual(attempts["count"], 2)
        self.assertEqual(len(verification_actions), 2)
        self.assertEqual(verification_actions[0]["evidence"]["status"], "failed")
        self.assertEqual(verification_actions[1]["evidence"]["status"], "success")
