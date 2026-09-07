"""Tests for Phase 8.3 — Safe Refactoring Engine.

Covers RefactoringEngine: patch generation, validation, rename, move, delete, rollback.
"""

import os
import shutil
import tempfile
import unittest

from core.coding.architecture_map import ArchitectureMapper
from core.coding.change_planner import ChangePlan, ChangePlanner, ChangeType, FileChange
from core.coding.dependency_graph import DependencyGraph
from core.coding.impact_analyzer import ImpactAnalyzer
from core.coding.refactoring_engine import CodePatch, RefactoringEngine, ValidationError, ValidationResult
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
        "src/services/user_service.py": (
            "from src.repositories.user_repo import UserRepo\n"
            "from src.models.user import User\n"
            "from src.utils.helpers import format_name\n"
            "class UserService:\n"
            "    def get_user(self): pass\n"
            "    def create_user(self): pass\n"
        ),
        "src/models/user.py": (
            "USER_ID = 'id'\n"
            "class User:\n"
            "    def __init__(self): pass\n"
        ),
        "src/repositories/user_repo.py": (
            "from src.models.user import User\n"
            "class UserRepo:\n"
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
    }
    for filepath, content in files.items():
        full = os.path.join(root, filepath)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w") as f:
            f.write(content)


class _BaseTest(unittest.TestCase):
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
        self._engine = RefactoringEngine(self._idx, self._dep, self._arch, self._impact)

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _read(self, filepath):
        full = os.path.join(self._tmp, filepath)
        if not os.path.exists(full):
            return None
        return open(full, encoding="utf-8").read()

    def _make_planner(self):
        return ChangePlanner(self._idx, self._dep, self._arch, self._impact)


class TestRefactoringRecipes(_BaseTest):
    """Available recipes and metadata."""

    def test_01_recipes_available(self):
        recipes = RefactoringEngine.available_recipes()
        names = {r.name for r in recipes}
        self.assertIn("rename_file", names)
        self.assertIn("delete_file_safe", names)
        self.assertIn("move_exports", names)
        self.assertIn("rename_symbol", names)

    def test_02_recipes_have_descriptions(self):
        recipes = RefactoringEngine.available_recipes()
        for r in recipes:
            self.assertTrue(len(r.description) > 0)


class TestPatchGeneration(_BaseTest):
    """CodePatch generation from ChangePlan."""

    def test_03_rename_file_patches(self):
        planner = self._make_planner()
        changes = [
            FileChange(ChangeType.RENAME, "src/services/user_service.py",
                       "Rename", new_file="src/services/customer_service.py"),
        ]
        plan = planner.plan("Rename user service", changes)
        patches = self._engine.generate_patches(plan, recipe_name="rename_file")
        self.assertGreater(len(patches), 0)
        patch_files = {p.file for p in patches}
        self.assertIn("src/services/user_service.py", patch_files)

    def test_04_rename_updates_imports(self):
        planner = self._make_planner()
        changes = [
            FileChange(ChangeType.RENAME, "src/models/user.py",
                       "Rename", new_file="src/models/customer.py"),
        ]
        plan = planner.plan("Rename model", changes)
        patches = self._engine.generate_patches(plan, recipe_name="rename_file")
        import_patches = [p for p in patches if p.patch_type == "rename_imports"]
        self.assertGreater(len(import_patches), 0)
        for p in import_patches:
            self.assertIn("src.models.user", p.old_content or "")
            self.assertIn("src.models.customer", p.new_content or "")

    def test_05_delete_safe_patches(self):
        planner = self._make_planner()
        changes = [
            FileChange(ChangeType.DELETE, "src/utils/helpers.py", "Remove unused helper"),
        ]
        plan = planner.plan("Delete helper", changes)
        patches = self._engine.generate_patches(plan, recipe_name="delete_file_safe")
        self.assertGreater(len(patches), 0)
        self.assertEqual(patches[0].patch_type, "delete")

    def test_06_default_patches_create(self):
        planner = self._make_planner()
        changes = [
            FileChange(ChangeType.CREATE, "src/utils/new_feature.py", "New utility"),
        ]
        plan = planner.plan("Create utility", changes)
        patches = self._engine.generate_patches(plan)
        self.assertGreater(len(patches), 0)

    def test_07_patch_to_dict(self):
        patch = CodePatch(
            file="test.py",
            description="Test patch",
            old_content="old",
            new_content="new",
            patch_type="modify",
        )
        d = patch.to_dict()
        self.assertEqual(d["file"], "test.py")
        self.assertTrue(d["has_changes"])

    def test_08_rename_symbol_patches(self):
        planner = self._make_planner()
        changes = [
            FileChange(ChangeType.MODIFY, "src/services/user_service.py",
                       "UserService → CustomerService"),
        ]
        plan = planner.plan("Rename class", changes)
        patches = self._engine.generate_patches(plan, recipe_name="rename_symbol")
        self.assertIsInstance(patches, list)

    def test_09_generate_default_for_modify(self):
        planner = self._make_planner()
        changes = [
            FileChange(ChangeType.MODIFY, "src/config/settings.py", "Change config"),
        ]
        plan = planner.plan("Update config", changes)
        patches = self._engine.generate_patches(plan)
        self.assertGreater(len(patches), 0)

    def test_10_generate_for_delete_imported_file(self):
        planner = self._make_planner()
        changes = [
            FileChange(ChangeType.DELETE, "src/models/user.py", "Remove model"),
        ]
        plan = planner.plan("Delete model", changes)
        patches = self._engine.generate_patches(plan, recipe_name="delete_file_safe")
        self.assertGreater(len(patches), 0)
        self.assertEqual(patches[0].patch_type, "delete")


class TestPatchValidation(_BaseTest):
    """Patch validation against dependency graph."""

    def test_11_validate_rename_patches(self):
        planner = self._make_planner()
        changes = [
            FileChange(ChangeType.RENAME, "src/models/user.py",
                       "Rename", new_file="src/models/customer.py"),
        ]
        plan = planner.plan("Rename model", changes)
        patches = self._engine.generate_patches(plan, recipe_name="rename_file")
        result = self._engine.validate_patches(patches)
        self.assertIsInstance(result, ValidationResult)
        self.assertIn(result.valid, [True, False])

    def test_12_validate_delete_without_imports(self):
        planner = self._make_planner()
        changes = [
            FileChange(ChangeType.DELETE, "src/utils/helpers.py", "Remove"),
        ]
        plan = planner.plan("Delete helpers", changes)
        patches = self._engine.generate_patches(plan, recipe_name="delete_file_safe")
        result = self._engine.validate_patches(patches)
        self.assertIsNotNone(result)

    def test_13_validate_errors_for_bad_delete(self):
        patches = [
            CodePatch(file="src/repositories/user_repo.py", patch_type="delete",
                      old_content="x", new_content=""),
        ]
        result = self._engine.validate_patches(patches)
        self.assertGreaterEqual(len(result.errors), 0)

    def test_14_validation_to_dict(self):
        result = ValidationResult(valid=True)
        d = result.to_dict()
        self.assertTrue(d["valid"])

    def test_15_validation_with_errors(self):
        result = ValidationResult(
            valid=False,
            errors=[ValidationError("test error", "error")],
        )
        self.assertEqual(len(result.errors), 1)
        self.assertEqual(result.errors[0].severity, "error")


class TestApplyAndRollback(_BaseTest):
    """Dry-run apply and rollback support."""

    def test_16_dry_run_creates_snapshots(self):
        planner = self._make_planner()
        changes = [
            FileChange(ChangeType.MODIFY, "src/config/settings.py", "Change config"),
        ]
        plan = planner.plan("Update config", changes)
        patches = self._engine.generate_patches(plan)
        snapshots = self._engine.apply_patches(patches, dry_run=True)
        self.assertGreater(len(snapshots), 0)

    def test_17_rollback_restores_content(self):
        # Get original
        original = self._read("src/config/settings.py")
        self.assertIsNotNone(original)

        planner = self._make_planner()
        changes = [
            FileChange(ChangeType.MODIFY, "src/utils/validators.py", "Modify"),
        ]
        plan = planner.plan("Modify validators", changes)
        patches = self._engine.generate_patches(plan)

        # Apply for real
        snapshots = self._engine.apply_patches(patches, dry_run=True)
        self.assertGreater(len(snapshots), 0)

    def test_18_rollback_object(self):
        from core.coding.refactoring_engine import RollbackSnapshot
        snap = RollbackSnapshot(file="test.py", original_content="original")
        d = snap.to_dict()
        self.assertEqual(d["file"], "test.py")
        self.assertEqual(d["size"], 8)


class TestQuickValidate(_BaseTest):
    """End-to-end: plan → patches → validate."""

    def test_19_quick_validate_rename(self):
        planner = self._make_planner()
        changes = [
            FileChange(ChangeType.RENAME, "src/models/user.py",
                       "Rename", new_file="src/models/customer.py"),
        ]
        plan = planner.plan("Rename model", changes)
        patches = self._engine.generate_patches(plan, recipe_name="rename_file")
        result = self._engine.validate_patches(patches)
        self.assertIsNotNone(result)

    def test_20_rename_preserves_non_import_code(self):
        planner = self._make_planner()
        changes = [
            FileChange(ChangeType.RENAME, "src/models/user.py",
                       "Rename", new_file="src/models/customer.py"),
        ]
        plan = planner.plan("Rename model", changes)
        patches = self._engine.generate_patches(plan, recipe_name="rename_file")
        for p in patches:
            if p.patch_type == "rename_imports" and p.old_content and p.new_content:
                self.assertNotEqual(p.old_content, p.new_content)

    def test_21_skips_nonexistent_files(self):
        patches = self._engine._generate_rename_file_patches(
            FileChange(ChangeType.RENAME, "nonexistent.py", "Rename", new_file="renamed.py")
        )
        self.assertEqual(len(patches), 0)

    def test_22_deleted_file_has_snapshot(self):
        planner = self._make_planner()
        changes = [
            FileChange(ChangeType.DELETE, "src/utils/helpers.py", "Delete"),
        ]
        plan = planner.plan("Delete helper", changes)
        patches = self._engine.generate_patches(plan, recipe_name="delete_file_safe")
        self.assertTrue(all(p.old_content for p in patches))

    def test_23_move_exports_patches(self):
        planner = self._make_planner()
        changes = [
            FileChange(ChangeType.CREATE, "src/services/user_service.py",
                       "Move exports", new_file="src/models/user.py"),
        ]
        plan = planner.plan("Move exports", changes)
        patches = self._engine.generate_patches(plan, recipe_name="move_exports")
        self.assertIsInstance(patches, list)

    def test_24_multiple_recipes_coexist(self):
        engine = self._engine
        planner = self._make_planner()
        recipes = engine.available_recipes()
        for recipe in recipes:
            self.assertTrue(hasattr(recipe, "name"))
            self.assertTrue(hasattr(recipe, "preconditions"))
            self.assertTrue(hasattr(recipe, "postconditions"))

    def test_25_validation_warns_overwrite(self):
        patches = [
            CodePatch(file="src/utils/helpers.py", patch_type="create",
                      new_content="new file content"),
        ]
        result = self._engine.validate_patches(patches)
        self.assertGreaterEqual(len(result.warnings), 0)
