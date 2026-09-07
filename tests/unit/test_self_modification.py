"""Self-Modification Engine tests — Phase 18.0.

Covers:
  - Models: ModificationPlan, ModificationRecord, ModificationTarget
  - Planner: proposal→plan mapping, opportunity→plan mapping
  - Safety: pre-checks (confidence, improvement, file existence, function existence),
            post-checks (test regression, error increase, time increase)
  - Store: SQLite CRUD, listing, filtering
  - Executor: full lifecycle (plan→apply→test→promote/rollback)
  - Recipes: add_retry_loop, increase_timeout, promote_property
"""

import os
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from core.self_modification.executor import SelfModificationExecutor
from core.self_modification.models import (
    ModificationMetrics,
    ModificationPlan,
    ModificationRecipe,
    ModificationRecord,
    ModificationStatus,
    ModificationTarget,
)
from core.self_modification.planner import SelfModificationPlanner
from core.self_modification.recipes import (
    apply_recipe,
    get_registered_recipes,
    register_recipe,
)
from core.self_modification.safety import (
    SelfModificationSafety,
    PreCheckResult,
    PostCheckResult,
)
from core.self_modification.store import ModificationStore


# ── Helpers ───────────────────────────────────────────────────────────


def _make_plan(
    recipe: ModificationRecipe = ModificationRecipe.PROMOTE_PROPERTY,
    confidence: float = 0.8,
    improvement: float = 0.2,
    target_file: str = "",
    target_fn: str = "",
    system: str = "test_system",
) -> ModificationPlan:
    return ModificationPlan(
        plan_id="test_plan",
        proposal_id="test_proposal",
        recipe=recipe,
        target=ModificationTarget(
            system_name=system,
            target_file=target_file,
            target_function=target_fn,
        ),
        rationale="Test modification",
        expected_improvement=improvement,
        confidence=confidence,
    )


# ── Model Tests ───────────────────────────────────────────────────────


class TestModels(unittest.TestCase):
    """Modification models — creation, to_dict, status transitions."""

    def test_01_modification_plan_minimal(self):
        plan = _make_plan()
        self.assertEqual(plan.plan_id, "test_plan")
        self.assertEqual(plan.recipe, ModificationRecipe.PROMOTE_PROPERTY)
        self.assertEqual(plan.status, ModificationStatus.PLANNED)

    def test_02_modification_plan_to_dict(self):
        plan = _make_plan()
        d = plan.to_dict()
        self.assertIn("plan_id", d)
        self.assertIn("recipe", d)
        self.assertIn("confidence", d)
        self.assertEqual(d["recipe"], "promote_property")

    def test_03_modification_record_minimal(self):
        now = datetime.now(timezone.utc).isoformat()
        rec = ModificationRecord(
            record_id="rec_001",
            plan_id="plan_001",
            proposal_id="prop_001",
            recipe="add_retry_loop",
            target_system="browser_automation",
            target_file="core/tools/browser_tools.py",
            status=ModificationStatus.PLANNED,
            created_at=now,
        )
        self.assertEqual(rec.record_id, "rec_001")
        self.assertFalse(rec.success())
        self.assertFalse(rec.was_rolled_back())

    def test_04_modification_record_promoted(self):
        rec = ModificationRecord(
            record_id="r1", plan_id="p1", proposal_id="pr1",
            recipe="test", target_system="s", target_file="f",
            status=ModificationStatus.PROMOTED,
            created_at="now",
        )
        self.assertTrue(rec.success())
        self.assertFalse(rec.was_rolled_back())

    def test_05_modification_record_rolled_back(self):
        rec = ModificationRecord(
            record_id="r1", plan_id="p1", proposal_id="pr1",
            recipe="test", target_system="s", target_file="f",
            status=ModificationStatus.ROLLED_BACK,
            created_at="now",
        )
        self.assertFalse(rec.success())
        self.assertTrue(rec.was_rolled_back())

    def test_06_modification_target_extra_params(self):
        t = ModificationTarget(
            system_name="browser",
            target_file="test.py",
            target_function="hdl",
            extra_params={"retry_count": 5},
        )
        self.assertEqual(t.extra_params["retry_count"], 5)

    def test_07_modification_metrics_defaults(self):
        m = ModificationMetrics()
        self.assertEqual(m.test_pass_rate, 0.0)
        self.assertEqual(m.error_count, 0)

    def test_08_all_recipes_enumerated(self):
        values = [r.value for r in ModificationRecipe]
        self.assertIn("add_retry_loop", values)
        self.assertIn("add_verification_step", values)
        self.assertIn("increase_timeout", values)
        self.assertIn("enable_failure_memory", values)
        self.assertIn("add_calibration_hook", values)
        self.assertIn("promote_property", values)
        self.assertEqual(len(values), 6)


# ── Planner Tests ─────────────────────────────────────────────────────


class TestSelfModificationPlanner(unittest.TestCase):
    """Planner — proposal→plan mapping, opportunity→plan mapping."""

    def setUp(self):
        self.planner = SelfModificationPlanner()

    def test_10_plan_from_proposal_add_retry(self):
        plan = self.planner.plan_from_proposal(
            proposal_id="p1",
            target_system="browser_automation",
            proposal_type="add_retry",
            rationale="browser fails often",
            expected_improvement=0.3,
            confidence=0.8,
        )
        self.assertIsNotNone(plan)
        self.assertEqual(plan.recipe, ModificationRecipe.ADD_RETRY_LOOP)
        self.assertEqual(plan.target.system_name, "browser_automation")
        self.assertEqual(plan.target.target_file, "core/tools/browser_tools.py")

    def test_11_plan_from_proposal_increase_timeout(self):
        plan = self.planner.plan_from_proposal(
            proposal_id="p2",
            target_system="browser_automation",
            proposal_type="increase_timeout",
            rationale="timeouts too short",
            expected_improvement=0.15,
            confidence=0.7,
        )
        self.assertIsNotNone(plan)
        self.assertEqual(plan.recipe, ModificationRecipe.INCREASE_TIMEOUT)

    def test_12_plan_from_proposal_promote_property(self):
        plan = self.planner.plan_from_proposal(
            proposal_id="p3",
            target_system="automated_build",
            proposal_type="promote_property",
            rationale="should be retry_capable",
        )
        self.assertIsNotNone(plan)
        self.assertEqual(plan.recipe, ModificationRecipe.PROMOTE_PROPERTY)
        # promote_property has no target file
        self.assertEqual(plan.target.target_file, "")

    def test_13_unknown_proposal_type_returns_none(self):
        plan = self.planner.plan_from_proposal(
            proposal_id="p4",
            target_system="browser",
            proposal_type="nonexistent_recipe",
            rationale="test",
        )
        self.assertIsNone(plan)

    def test_14_unsupported_target_returns_none(self):
        plan = self.planner.plan_from_proposal(
            proposal_id="p5",
            target_system="unsupported_system",
            proposal_type="add_retry",
            rationale="test",
        )
        self.assertIsNone(plan)

    def test_15_list_available_recipes(self):
        recipes = self.planner.list_available_recipes()
        self.assertGreater(len(recipes), 0)
        recipe_names = [r["recipe"] for r in recipes]
        self.assertIn("add_retry_loop", recipe_names)
        self.assertIn("increase_timeout", recipe_names)
        for r in recipes:
            self.assertIn("description", r)
            self.assertIn("supported_targets", r)

    def test_16_plan_for_opportunity_bottleneck(self):
        opp = MagicMock()
        opp.target_system = "browser_automation"
        opp.source = MagicMock()
        opp.source.value = "bottleneck"
        opp.rationale = "browser fails often"
        opp.opportunity_score = 0.75
        opp.confidence = 0.8
        opp.id = "opp_001"

        plan = self.planner.plan_for_opportunity(opp)
        self.assertIsNotNone(plan)
        self.assertEqual(plan.recipe, ModificationRecipe.ADD_RETRY_LOOP)

    def test_17_plan_for_opportunity_ceiling_strategy(self):
        opp = MagicMock()
        opp.target_system = "strategic_reasoning"
        opp.source = MagicMock()
        opp.source.value = "ceiling"
        opp.rationale = "strategy needs calibration"
        opp.opportunity_score = 0.6
        opp.confidence = 0.7
        opp.id = "opp_002"

        plan = self.planner.plan_for_opportunity(opp)
        self.assertIsNotNone(plan)
        self.assertEqual(plan.recipe, ModificationRecipe.ADD_CALIBRATION_HOOK)


# ── Safety Tests ──────────────────────────────────────────────────────


class TestSelfModificationSafety(unittest.TestCase):
    """Safety gates — pre and post checks."""

    def setUp(self):
        self.safety = SelfModificationSafety(
            min_confidence=0.60,
            min_improvement=0.05,
            max_test_regression=0.05,
            max_error_increase=2,
            max_time_increase=1.5,
        )

    # ── Pre-checks ─────────────────────────────────────────────────

    def test_20_pre_check_confidence_passes(self):
        plan = _make_plan(confidence=0.8, improvement=0.2)
        result = self.safety.check_pre(plan)
        self.assertTrue(result.passed)

    def test_21_pre_check_confidence_fails(self):
        plan = _make_plan(confidence=0.4, improvement=0.2)
        result = self.safety.check_pre(plan)
        self.assertFalse(result.passed)
        self.assertIn("confidence", result.reason.lower())

    def test_22_pre_check_improvement_fails(self):
        plan = _make_plan(confidence=0.8, improvement=0.01)
        result = self.safety.check_pre(plan)
        self.assertFalse(result.passed)
        self.assertIn("improvement", result.reason.lower())

    def test_23_pre_check_file_not_found(self):
        plan = _make_plan(
            target_file="nonexistent_file.py",
            confidence=0.8,
            improvement=0.2,
        )
        result = self.safety.check_pre(plan)
        self.assertFalse(result.passed)
        self.assertIn("not found", result.reason.lower())

    def test_24_pre_check_file_exists_passes(self):
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write("def my_function():\n    pass\n")
            f.flush()
            tmp_path = f.name

        plan = _make_plan(
            target_file=tmp_path,
            target_fn="my_function",
            confidence=0.8,
            improvement=0.2,
        )
        result = self.safety.check_pre(plan)
        self.assertTrue(result.passed, msg=result.reason)
        os.unlink(tmp_path)

    def test_25_pre_check_function_not_found(self):
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write("def other_function():\n    pass\n")
            f.flush()
            tmp_path = f.name

        plan = _make_plan(
            target_file=tmp_path,
            target_fn="my_function",
            confidence=0.8,
            improvement=0.2,
        )
        result = self.safety.check_pre(plan)
        self.assertFalse(result.passed)
        self.assertIn("not found", result.reason.lower())
        os.unlink(tmp_path)

    # ── Post-checks ────────────────────────────────────────────────

    def test_30_post_check_no_regression(self):
        before = ModificationMetrics(test_pass_rate=0.90, error_count=1, execution_time_seconds=10.0)
        after = ModificationMetrics(test_pass_rate=0.92, error_count=1, execution_time_seconds=9.5)
        result = self.safety.check_post(before, after)
        self.assertTrue(result.passed)

    def test_31_post_check_test_regression_fails(self):
        before = ModificationMetrics(test_pass_rate=0.90, error_count=1)
        after = ModificationMetrics(test_pass_rate=0.80, error_count=1)
        result = self.safety.check_post(before, after)
        self.assertFalse(result.passed)
        self.assertIn("test pass rate", result.reason.lower())

    def test_32_post_check_error_increase_fails(self):
        before = ModificationMetrics(test_pass_rate=0.90, error_count=1)
        after = ModificationMetrics(test_pass_rate=0.90, error_count=5)
        result = self.safety.check_post(before, after)
        self.assertFalse(result.passed)
        self.assertIn("error count", result.reason.lower())

    def test_33_post_check_time_regression_fails(self):
        before = ModificationMetrics(test_pass_rate=0.90, error_count=1, execution_time_seconds=10.0)
        after = ModificationMetrics(test_pass_rate=0.90, error_count=1, execution_time_seconds=30.0)
        result = self.safety.check_post(before, after)
        self.assertFalse(result.passed)
        self.assertIn("execution time", result.reason.lower())

    def test_34_post_check_mixed_regressions(self):
        before = ModificationMetrics(test_pass_rate=0.95, error_count=0, execution_time_seconds=5.0)
        after = ModificationMetrics(test_pass_rate=0.85, error_count=3, execution_time_seconds=10.0)
        result = self.safety.check_post(before, after)
        self.assertFalse(result.passed)

    def test_35_post_check_perfect_metrics(self):
        before = ModificationMetrics(test_pass_rate=1.0, error_count=0, execution_time_seconds=5.0)
        after = ModificationMetrics(test_pass_rate=1.0, error_count=0, execution_time_seconds=5.0)
        result = self.safety.check_post(before, after)
        self.assertTrue(result.passed)


# ── Store Tests ───────────────────────────────────────────────────────


class TestModificationStore(unittest.TestCase):
    """SQLite store — CRUD, listing, filtering."""

    def setUp(self):
        self.tmp = tempfile.mktemp(suffix=".db")
        self.store = ModificationStore(db_path=self.tmp)

    def tearDown(self):
        os.unlink(self.tmp)

    def _make_rec(self, rid: str, status: ModificationStatus = ModificationStatus.PLANNED):
        return ModificationRecord(
            record_id=rid,
            plan_id="p1",
            proposal_id="pr1",
            recipe="test",
            target_system="sys_x",
            target_file="f.py",
            status=status,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    def test_40_save_and_get(self):
        rec = self._make_rec("rec_001")
        self.store.save(rec)
        loaded = self.store.get("rec_001")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.record_id, "rec_001")
        self.assertEqual(loaded.status, ModificationStatus.PLANNED)

    def test_41_get_missing(self):
        self.assertIsNone(self.store.get("nonexistent"))

    def test_42_update_existing(self):
        rec = self._make_rec("u1")
        self.store.save(rec)
        rec.status = ModificationStatus.PROMOTED
        self.store.save(rec)
        loaded = self.store.get("u1")
        self.assertEqual(loaded.status, ModificationStatus.PROMOTED)

    def test_43_list_by_status(self):
        for i in range(3):
            self.store.save(self._make_rec(f"p_{i}", ModificationStatus.PROMOTED))
        for i in range(2):
            self.store.save(self._make_rec(f"r_{i}", ModificationStatus.ROLLED_BACK))

        promoted = self.store.list_by_status(ModificationStatus.PROMOTED, limit=10)
        rolled = self.store.list_by_status(ModificationStatus.ROLLED_BACK, limit=10)
        self.assertEqual(len(promoted), 3)
        self.assertEqual(len(rolled), 2)

    def test_44_list_all(self):
        for i in range(5):
            self.store.save(self._make_rec(f"rec_{i}"))
        all_recs = self.store.list_by_status(limit=10)
        self.assertEqual(len(all_recs), 5)

    def test_45_list_by_system(self):
        for i in range(3):
            r = self._make_rec(f"s_{i}")
            r.target_system = "sys_a"
            self.store.save(r)
        for i in range(2):
            r = self._make_rec(f"t_{i}")
            r.target_system = "sys_b"
            self.store.save(r)

        sys_a = self.store.list_by_system("sys_a", limit=10)
        sys_b = self.store.list_by_system("sys_b", limit=10)
        self.assertEqual(len(sys_a), 3)
        self.assertEqual(len(sys_b), 2)

    def test_46_count_by_status(self):
        self.store.save(self._make_rec("c1", ModificationStatus.PLANNED))
        self.store.save(self._make_rec("c2", ModificationStatus.PROMOTED))
        self.store.save(self._make_rec("c3", ModificationStatus.PROMOTED))
        counts = self.store.count_by_status()
        self.assertEqual(counts.get("planned", 0), 1)
        self.assertEqual(counts.get("promoted", 0), 2)

    def test_47_delete(self):
        self.store.save(self._make_rec("del"))
        self.assertTrue(self.store.delete("del"))
        self.assertIsNone(self.store.get("del"))
        self.assertFalse(self.store.delete("del"))

    def test_48_count(self):
        self.assertEqual(self.store.count(), 0)
        self.store.save(self._make_rec("cnt1"))
        self.assertEqual(self.store.count(), 1)
        self.store.save(self._make_rec("cnt2"))
        self.assertEqual(self.store.count(), 2)


# ── Executor Tests ────────────────────────────────────────────────────


class TestSelfModificationExecutor(unittest.TestCase):
    """Executor — full lifecycle with patches, rollback, promotion."""

    def setUp(self):
        self.tmp_db = tempfile.mktemp(suffix=".db")
        self.store = ModificationStore(db_path=self.tmp_db)
        self.safety = SelfModificationSafety(
            min_confidence=0.1,  # lenient for testing
            min_improvement=0.01,
        )

    def tearDown(self):
        os.unlink(self.tmp_db)

    def test_50_execute_promote_property_no_file(self):
        """Property promotion requires no file — should promote immediately."""
        plan = _make_plan(
            recipe=ModificationRecipe.PROMOTE_PROPERTY,
            confidence=0.9,
            improvement=0.3,
        )
        executor = SelfModificationExecutor(store=self.store, safety=self.safety)
        record = executor.execute(plan)
        self.assertEqual(record.status, ModificationStatus.PROMOTED, msg=record.error_message)
        self.assertEqual(record.patch_count, 0)

    def test_51_execute_low_confidence_fails_pre_check(self):
        plan = _make_plan(confidence=0.01, improvement=0.3)
        executor = SelfModificationExecutor(store=self.store, safety=self.safety)
        record = executor.execute(plan)
        self.assertEqual(record.status, ModificationStatus.FAILED)

    def test_52_execute_low_improvement_fails_pre_check(self):
        plan = _make_plan(confidence=0.9, improvement=0.001)
        executor = SelfModificationExecutor(store=self.store, safety=self.safety)
        record = executor.execute(plan)
        self.assertEqual(record.status, ModificationStatus.FAILED)

    def test_53_execute_missing_file_rolls_back(self):
        """Recipe targeting a nonexistent file should fail pre-check or rollback."""
        plan = _make_plan(
            recipe=ModificationRecipe.INCREASE_TIMEOUT,
            target_file="nonexistent_file_xyz.py",
            confidence=0.9,
            improvement=0.3,
        )
        executor = SelfModificationExecutor(store=self.store, safety=self.safety)
        record = executor.execute(plan)
        # Should fail pre-check because file doesn't exist
        self.assertIn(record.status, [ModificationStatus.FAILED, ModificationStatus.ROLLED_BACK])

    def test_54_execute_with_test_runner(self):
        """Executor uses test_runner to collect before/after metrics."""
        plan = _make_plan(
            recipe=ModificationRecipe.PROMOTE_PROPERTY,
            confidence=0.9,
            improvement=0.3,
        )

        def fake_test_runner():
            return {"pass_rate": 0.95, "error_count": 1, "duration": 5.0, "coverage": 0.8}

        executor = SelfModificationExecutor(
            store=self.store,
            safety=self.safety,
            test_runner=fake_test_runner,
        )
        record = executor.execute(plan)
        self.assertEqual(record.status, ModificationStatus.PROMOTED)
        self.assertIn("test_pass_rate", record.before_metrics)

    def test_55_execute_stores_record_in_db(self):
        plan = _make_plan(
            recipe=ModificationRecipe.PROMOTE_PROPERTY,
            confidence=0.9,
            improvement=0.3,
        )
        executor = SelfModificationExecutor(store=self.store, safety=self.safety)
        record = executor.execute(plan)
        self.assertIsNotNone(self.store.get(record.record_id))
        self.assertGreater(self.store.count(), 0)


# ── Recipe Tests ──────────────────────────────────────────────────────


class TestRecipes(unittest.TestCase):
    """Recipe transformations — patch generation."""

    def test_60_all_recipes_registered(self):
        recipes = get_registered_recipes()
        self.assertIn("add_retry_loop", recipes)
        self.assertIn("add_verification_step", recipes)
        self.assertIn("increase_timeout", recipes)
        self.assertIn("enable_failure_memory", recipes)
        self.assertIn("add_calibration_hook", recipes)
        self.assertIn("promote_property", recipes)
        self.assertEqual(len(recipes), 6)

    def test_61_apply_unknown_recipe_raises(self):
        target = ModificationTarget(
            system_name="test", target_file="test.py",
        )
        with self.assertRaises(ValueError):
            apply_recipe(ModificationRecipe.ADD_RETRY_LOOP, target)

    def test_62_promote_property_returns_empty_patches(self):
        target = ModificationTarget(
            system_name="test",
            target_file="",
            target_function="",
        )
        patches = apply_recipe(ModificationRecipe.PROMOTE_PROPERTY, target)
        self.assertEqual(patches, [])

    def test_63_increase_timeout_on_file_with_timeout(self):
        """increase_timeout produces patches when TIMEOUT constants exist."""
        with tempfile.NamedTemporaryFile(
            suffix=".py", mode="w", delete=False
        ) as f:
            f.write("TIMEOUT = 30\n")
            f.write("def run(timeout=30):\n")
            f.write("    pass\n")
            tmp_path = f.name

        target = ModificationTarget(
            system_name="test",
            target_file=tmp_path,
            target_function="",
            extra_params={"multiplier": 2.0},
        )
        patches = apply_recipe(ModificationRecipe.INCREASE_TIMEOUT, target)
        self.assertGreater(len(patches), 0)

        # Verify the patch changes TIMEOUT = 30 → TIMEOUT = 60
        for patch in patches:
            if "TIMEOUT" in patch.get("description", ""):
                self.assertIn("60", patch["new_content"])
                self.assertNotIn("TIMEOUT = 30", patch["new_content"])
                break
        else:
            self.fail("No TIMEOUT-related patch found")

        os.unlink(tmp_path)

    def test_64_increase_timeout_on_file_without_timeout(self):
        """increase_timeout returns no patches when no timeout exists."""
        with tempfile.NamedTemporaryFile(
            suffix=".py", mode="w", delete=False
        ) as f:
            f.write("x = 42\n")
            f.write("def foo():\n")
            f.write("    return x\n")
            tmp_path = f.name

        target = ModificationTarget(
            system_name="test",
            target_file=tmp_path,
            target_function="",
            extra_params={"multiplier": 2.0},
        )
        patches = apply_recipe(ModificationRecipe.INCREASE_TIMEOUT, target)
        self.assertEqual(len(patches), 0)

        os.unlink(tmp_path)
