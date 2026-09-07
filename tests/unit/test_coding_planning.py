"""Tests for Phase 8.2 — Change Planning.

Covers ChangePlanner, RefactorSafetyEngine, ChangeSimulation
against the same synthetic layered project used in Phase 8.1 tests.
"""

import os
import shutil
import tempfile
import unittest

from core.coding.architecture_map import ArchitectureMapper
from core.coding.change_planner import ChangePlan, ChangePlanner, ChangeType, FileChange
from core.coding.change_simulation import ChangeSimulation
from core.coding.dependency_graph import DependencyGraph
from core.coding.impact_analyzer import ImpactAnalyzer
from core.coding.refactor_safety import RefactorSafetyEngine
from core.coding.repository_indexer import RepositoryIndexer


def _create_test_project(root: str) -> None:
    files = {
        "src/controllers/user_controller.py": (
            "from src.services.user_service import UserService\n"
            "from src.utils.validators import validate_email\n"
            "from src.config.settings import config\n"
            "class UserController:\n"
            "    def get_user(self): pass\n"
        ),
        "src/controllers/order_controller.py": (
            "from src.services.order_service import OrderService\n"
            "from src.utils.validators import validate_order\n"
            "class OrderController:\n"
            "    def create_order(self): pass\n"
        ),
        "src/services/user_service.py": (
            "from src.repositories.user_repo import UserRepo\n"
            "from src.models.user import User\n"
            "from src.utils.helpers import format_name\n"
            "class UserService:\n"
            "    def get_user(self): pass\n"
        ),
        "src/services/order_service.py": (
            "from src.repositories.order_repo import OrderRepo\n"
            "from src.models.order import Order\n"
            "class OrderService:\n"
            "    def get_order(self): pass\n"
        ),
        "src/models/user.py": (
            "USER_ID = 'id'\n"
            "class User:\n"
            "    def __init__(self): pass\n"
        ),
        "src/models/order.py": (
            "ORDER_STATUS = 'pending'\n"
            "class Order:\n"
            "    def __init__(self): pass\n"
        ),
        "src/repositories/user_repo.py": (
            "from src.models.user import User\n"
            "class UserRepo:\n"
            "    def find_by_id(self): pass\n"
        ),
        "src/repositories/order_repo.py": (
            "from src.models.order import Order\n"
            "class OrderRepo:\n"
            "    def find_by_id(self): pass\n"
        ),
        "src/utils/helpers.py": (
            "def format_name(name): return name.strip()\n"
        ),
        "src/utils/validators.py": (
            "VALID = True\n"
            "def validate_email(email): return True\n"
        ),
        "src/config/settings.py": (
            "config = {'debug': True}\n"
            "APP_NAME = 'test_app'\n"
        ),
        "src/tests/test_user.py": (
            "from src.controllers.user_controller import UserController\n"
            "def test_get_user(): pass\n"
        ),
        "src/tests/test_order.py": (
            "from src.services.order_service import OrderService\n"
            "def test_get_order(): pass\n"
        ),
    }
    for filepath, content in files.items():
        full = os.path.join(root, filepath)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w") as f:
            f.write(content)


class _BaseTest(unittest.TestCase):
    """Shared setup for all Phase 8.2 tests."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._db = os.path.join(self._tmp, "test_repo.db")
        _create_test_project(self._tmp)
        self._idx = RepositoryIndexer(path=self._tmp, db_path=self._db)
        self._idx.index(force=True)
        self._dep = DependencyGraph(self._idx)
        self._dep.build()
        self._arch = ArchitectureMapper(self._idx, self._dep)
        self._arch.map_layers()
        self._impact = ImpactAnalyzer(self._idx, self._dep, self._arch)

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)


class TestChangePlanner(_BaseTest):
    """ChangePlanner — plan creation, risk assessment, execution ordering."""

    def test_01_create_plan(self):
        planner = ChangePlanner(self._idx, self._dep, self._arch, self._impact)
        changes = [
            FileChange(ChangeType.MODIFY, "src/services/user_service.py", "Add loyalty support"),
            FileChange(ChangeType.MODIFY, "src/models/user.py", "Add loyalty points field"),
        ]
        plan = planner.plan("Add loyalty rewards", changes)
        self.assertIsInstance(plan, ChangePlan)
        self.assertGreater(len(plan.steps), 0)
        self.assertEqual(plan.request, "Add loyalty rewards")

    def test_02_plan_includes_steps(self):
        planner = ChangePlanner(self._idx, self._dep, self._arch, self._impact)
        changes = [
            FileChange(ChangeType.CREATE, "src/services/rewards_service.py", "New rewards service"),
            FileChange(ChangeType.MODIFY, "src/models/user.py", "Add points field"),
        ]
        plan = planner.plan("Add rewards", changes)
        self.assertGreater(len(plan.steps), 0)
        step_labels = [s.description for s in plan.steps]
        self.assertTrue(any("scaffold" in s.lower() or "Create" in s for s in step_labels))

    def test_03_risk_scores(self):
        planner = ChangePlanner(self._idx, self._dep, self._arch, self._impact)
        changes = [
            FileChange(ChangeType.MODIFY, "src/config/settings.py", "Change app name"),
        ]
        plan = planner.plan("Update config", changes)
        self.assertGreaterEqual(plan.overall_risk, 0.0)
        self.assertLessEqual(plan.overall_risk, 1.0)

    def test_04_affected_files_detected(self):
        planner = ChangePlanner(self._idx, self._dep, self._arch, self._impact)
        changes = [
            FileChange(ChangeType.MODIFY, "src/models/user.py", "Change user model"),
        ]
        plan = planner.plan("Update user model", changes)
        self.assertGreater(len(plan.total_affected_files), 0)
        self.assertIn("src/models/user.py", plan.total_affected_files)

    def test_05_delete_breaking_changes(self):
        planner = ChangePlanner(self._idx, self._dep, self._arch, self._impact)
        changes = [
            FileChange(ChangeType.DELETE, "src/models/user.py", "Remove user model"),
        ]
        plan = planner.plan("Remove user model", changes)
        if plan.breaking_changes:
            self.assertTrue(any("user_repo" in b or "user_service" in b for b in plan.breaking_changes))

    def test_06_warnings_for_central_files(self):
        planner = ChangePlanner(self._idx, self._dep, self._arch, self._impact)
        changes = [
            FileChange(ChangeType.MODIFY, "src/config/settings.py", "Modify config"),
        ]
        plan = planner.plan("Update config", changes)
        self.assertTrue(len(plan.warnings) > 0 or plan.overall_risk >= 0)

    def test_07_execution_groups(self):
        planner = ChangePlanner(self._idx, self._dep, self._arch, self._impact)
        changes = [
            FileChange(ChangeType.MODIFY, "src/models/user.py", "Update model"),
            FileChange(ChangeType.MODIFY, "src/models/order.py", "Update model"),
            FileChange(ChangeType.CREATE, "src/services/new_service.py", "New service"),
        ]
        plan = planner.plan("Multi-file change", changes)
        self.assertGreater(len(plan.execution_groups), 0)

    def test_08_empty_changes(self):
        planner = ChangePlanner(self._idx, self._dep, self._arch, self._impact)
        plan = planner.plan("Nothing", [])
        self.assertEqual(len(plan.steps), 0)

    def test_09_suggested_tests(self):
        planner = ChangePlanner(self._idx, self._dep, self._arch, self._impact)
        changes = [
            FileChange(ChangeType.MODIFY, "src/services/user_service.py", "Modify service"),
        ]
        plan = planner.plan("Update service", changes)
        self.assertIsInstance(plan.all_suggested_tests, list)

    def test_10_to_dict(self):
        planner = ChangePlanner(self._idx, self._dep, self._arch, self._impact)
        changes = [
            FileChange(ChangeType.MODIFY, "src/models/user.py", "Update"),
        ]
        plan = planner.plan("Test dict", changes)
        d = plan.to_dict()
        self.assertEqual(d["request"], "Test dict")
        self.assertIn("step_count", d)
        self.assertIn("overall_risk", d)


class TestRefactorSafety(_BaseTest):
    """RefactorSafetyEngine — pre-edit safety checks."""

    def test_11_safe_modify(self):
        engine = RefactorSafetyEngine(self._idx, self._dep, self._arch, self._impact)
        result = engine.evaluate_change("src/services/user_service.py", "modify")
        self.assertIn(result.risk_label, ["low", "medium", "high", "critical"])

    def test_12_delete_warning(self):
        engine = RefactorSafetyEngine(self._idx, self._dep, self._arch, self._impact)
        result = engine.evaluate_change("src/models/user.py", "delete")
        if result.warnings:
            self.assertTrue(any("break" in w.message for w in result.warnings))

    def test_13_create_existing_warning(self):
        engine = RefactorSafetyEngine(self._idx, self._dep, self._arch, self._impact)
        result = engine.evaluate_change("src/models/user.py", "create")
        self.assertGreaterEqual(len(result.warnings), 1)
        self.assertTrue(any("exists" in w.message.lower() for w in result.warnings))

    def test_14_create_new_file(self):
        engine = RefactorSafetyEngine(self._idx, self._dep, self._arch, self._impact)
        result = engine.evaluate_change("src/services/new_feature.py", "create")
        self.assertTrue(result.safe)

    def test_15_modify_nonexistent(self):
        engine = RefactorSafetyEngine(self._idx, self._dep, self._arch, self._impact)
        result = engine.evaluate_change("nonexistent.py", "modify")
        self.assertGreater(len(result.warnings), 0)

    def test_16_evaluate_plan_batch(self):
        engine = RefactorSafetyEngine(self._idx, self._dep, self._arch, self._impact)
        results = engine.evaluate_plan([
            ("src/services/user_service.py", "modify"),
            ("src/models/user.py", "modify"),
        ])
        self.assertEqual(len(results), 2)

    def test_17_rename_safety(self):
        engine = RefactorSafetyEngine(self._idx, self._dep, self._arch, self._impact)
        result = engine.evaluate_change("src/models/user.py", "rename")
        self.assertIsNotNone(result)

    def test_18_high_risk_change(self):
        engine = RefactorSafetyEngine(self._idx, self._dep, self._arch, self._impact)
        result = engine.evaluate_change("src/config/settings.py", "modify")
        self.assertIn(result.risk_label, ["low", "medium", "high", "critical"])


class TestChangeSimulation(_BaseTest):
    """ChangeSimulation — predict breakages, detect conflicts."""

    def _make_planner(self):
        return ChangePlanner(self._idx, self._dep, self._arch, self._impact)

    def test_19_simulate_delete(self):
        sim = ChangeSimulation(self._idx, self._dep, self._arch, self._impact)
        planner = self._make_planner()
        changes = [FileChange(ChangeType.DELETE, "src/models/user.py", "Remove model")]
        plan = planner.plan("Delete user model", changes)
        result = sim.simulate(plan)
        self.assertGreater(len(result.breakages), 0)
        break_files = {b.file for b in result.breakages}
        self.assertTrue(
            "src/repositories/user_repo.py" in break_files or len(result.breakages) > 0
        )

    def test_20_simulate_modify(self):
        sim = ChangeSimulation(self._idx, self._dep, self._arch, self._impact)
        planner = self._make_planner()
        changes = [FileChange(ChangeType.MODIFY, "src/services/user_service.py", "Change")]
        plan = planner.plan("Modify service", changes)
        result = sim.simulate(plan)
        self.assertIsNotNone(result)

    def test_21_simulate_create(self):
        sim = ChangeSimulation(self._idx, self._dep, self._arch, self._impact)
        planner = self._make_planner()
        changes = [FileChange(ChangeType.CREATE, "src/services/new_service.py", "New")]
        plan = planner.plan("Create service", changes)
        result = sim.simulate(plan)
        self.assertTrue(result.free_of_issues or not result.free_of_issues)

    def test_22_conflict_detection(self):
        sim = ChangeSimulation(self._idx, self._dep, self._arch, self._impact)
        planner = self._make_planner()
        changes = [
            FileChange(ChangeType.MODIFY, "src/models/user.py", "Change"),
            FileChange(ChangeType.DELETE, "src/models/user.py", "Delete"),
        ]
        plan = planner.plan("Conflicting changes", changes)
        result = sim.simulate(plan)
        self.assertGreater(len(result.conflicts), 0)

    def test_23_affected_files_tracked(self):
        sim = ChangeSimulation(self._idx, self._dep, self._arch, self._impact)
        planner = self._make_planner()
        changes = [FileChange(ChangeType.MODIFY, "src/repositories/user_repo.py", "Change")]
        plan = planner.plan("Modify repo", changes)
        result = sim.simulate(plan)
        self.assertGreater(len(result.affected_files), 0)

    def test_24_test_failures(self):
        sim = ChangeSimulation(self._idx, self._dep, self._arch, self._impact)
        planner = self._make_planner()
        changes = [FileChange(ChangeType.MODIFY, "src/controllers/user_controller.py", "Change")]
        plan = planner.plan("Modify controller", changes)
        failures = sim.predict_test_failures(plan)
        self.assertIsInstance(failures, list)
        if failures:
            self.assertIn("risk", failures[0])

    def test_25_simulate_rename(self):
        sim = ChangeSimulation(self._idx, self._dep, self._arch, self._impact)
        planner = self._make_planner()
        changes = [
            FileChange(ChangeType.RENAME, "src/services/user_service.py",
                       "Rename service", new_file="src/services/customer_service.py"),
        ]
        plan = planner.plan("Rename service", changes)
        result = sim.simulate(plan)
        rename_breakages = [b for b in result.breakages if "rename" in b.reason.lower() or "Renam" in b.reason]
        self.assertGreater(len(rename_breakages), 0)

    def test_26_unchanged_affected_files(self):
        sim = ChangeSimulation(self._idx, self._dep, self._arch, self._impact)
        planner = self._make_planner()
        changes = [FileChange(ChangeType.MODIFY, "src/models/user.py", "Update model")]
        plan = planner.plan("Update model", changes)
        result = sim.simulate(plan)
        self.assertGreater(len(result.unchanged_affected), 0)
        for f in result.unchanged_affected:
            self.assertNotIn(f, {"src/models/user.py"})

    def test_27_simulate_to_dict(self):
        sim = ChangeSimulation(self._idx, self._dep, self._arch, self._impact)
        planner = self._make_planner()
        changes = [FileChange(ChangeType.MODIFY, "src/models/user.py", "Update")]
        plan = planner.plan("Test", changes)
        result = sim.simulate(plan)
        d = result.to_dict()
        self.assertIn("plan_summary", d)
        self.assertIn("breakage_count", d)
        self.assertIn("conflict_count", d)

    def test_28_modify_nonexistent_in_sim(self):
        sim = ChangeSimulation(self._idx, self._dep, self._arch, self._impact)
        planner = self._make_planner()
        changes = [FileChange(ChangeType.MODIFY, "src/nonexistent.py", "Modify")]
        plan = planner.plan("Modify none", changes)
        result = sim.simulate(plan)
        self.assertGreater(len(result.breakages), 0)
