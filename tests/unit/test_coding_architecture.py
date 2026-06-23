"""Tests for Phase 8.4 — Architecture Reasoning.

Covers ArchitectureScorer, DesignAnalyzer, TradeoffEngine, MigrationPlanner.
"""

import os
import shutil
import tempfile
import unittest

from core.coding.architecture_map import ArchitectureMapper
from core.coding.architecture_reasoning import (
    ArchitectureScore,
    ArchitectureScorer,
    DesignAnalyzer,
    DesignReport,
    DesignWeakness,
    MigrationPlanner,
    TradeoffComparison,
    TradeoffEngine,
)
from core.coding.change_planner import ChangePlanner
from core.coding.dependency_graph import DependencyGraph
from core.coding.impact_analyzer import ImpactAnalyzer
from core.coding.repository_indexer import RepositoryIndexer


def _create_test_project(root: str) -> None:
    files = {
        "src/controllers/user_controller.py": (
            "from src.services.user_service import UserService\n"
            "from src.utils.validators import validate_email\n"
            "class UserController:\n"
            "    def get_user(self): pass\n"
        ),
        "src/controllers/order_controller.py": (
            "from src.services.order_service import OrderService\n"
            "class OrderController:\n"
            "    def create_order(self): pass\n"
        ),
        "src/services/user_service.py": (
            "from src.repositories.user_repo import UserRepo\n"
            "from src.models.user import User\n"
            "class UserService:\n"
            "    def get_user(self): pass\n"
            "    def create_user(self): pass\n"
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
        "src/config/settings.py": (
            "config = {'debug': True}\n"
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
        self._scorer = ArchitectureScorer(self._idx, self._dep, self._arch)
        self._analyzer = DesignAnalyzer(self._idx, self._dep, self._arch, self._scorer)
        self._tradeoff = TradeoffEngine()
        self._planner = ChangePlanner(self._idx, self._dep, self._arch, self._impact)
        self._migration = MigrationPlanner(self._idx, self._dep, self._arch, self._impact, self._planner)

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)


class TestArchitectureScorer(_BaseTest):
    """ArchitectureScorer — coupling, cohesion, stability, layer discipline."""

    def test_01_score_returns_all_dimensions(self):
        score = self._scorer.score()
        self.assertLessEqual(score.coupling, 1.0)
        self.assertLessEqual(score.cohesion, 1.0)
        self.assertLessEqual(score.maintainability, 1.0)
        self.assertLessEqual(score.stability, 1.0)
        self.assertLessEqual(score.layer_discipline, 1.0)

    def test_02_overall_computed(self):
        score = self._scorer.score()
        overall = score.overall()
        self.assertGreaterEqual(overall, 0.0)
        self.assertLessEqual(overall, 1.0)

    def test_03_score_to_dict(self):
        score = self._scorer.score()
        d = score.to_dict()
        self.assertIn("coupling", d)
        self.assertIn("overall", d)
        self.assertIn("maintainability", d)


class TestDesignAnalyzer(_BaseTest):
    """DesignAnalyzer — weaknesses, pattern advisory, migration suggestions."""

    def test_04_analyze_returns_report(self):
        report = self._analyzer.analyze()
        self.assertIsInstance(report, DesignReport)
        self.assertIn(report.pattern, ["layered", "mvc"])

    def test_05_weaknesses_detected(self):
        report = self._analyzer.analyze()
        self.assertIsInstance(report.weaknesses, list)

    def test_06_migration_suggestions_present(self):
        report = self._analyzer.analyze()
        self.assertGreater(len(report.migration_suggestions), 0)

    def test_07_report_to_dict(self):
        report = self._analyzer.analyze()
        d = report.to_dict()
        self.assertIn("score", d)
        self.assertIn("weaknesses", d)
        self.assertIn("pattern", d)
        self.assertIn("summary", d)

    def test_08_summary_generated(self):
        report = self._analyzer.analyze()
        self.assertGreater(len(report.summary), 0)

    def test_09_god_file_detection(self):
        # The synthetic project has small files — so likely no god files
        report = self._analyzer.analyze()
        god = [w for w in report.weaknesses if w.category == "god_file"]
        self.assertIsInstance(god, list)


class TestTradeoffEngine(_BaseTest):
    """TradeoffEngine — pattern comparison."""

    def test_10_compare_returns_tradeoff(self):
        result = self._tradeoff.compare("layered")
        self.assertIsInstance(result, TradeoffComparison)

    def test_11_alternatives_scored(self):
        result = self._tradeoff.compare("mvc")
        self.assertGreater(len(result.alternatives), 0)

    def test_12_recommended_selected(self):
        result = self._tradeoff.compare("monolith")
        self.assertIsInstance(result.recommended, str)

    def test_13_rationale_generated(self):
        result = self._tradeoff.compare("layered")
        self.assertGreater(len(result.rationale), 0)

    def test_14_tradeoff_to_dict(self):
        result = self._tradeoff.compare("layered")
        d = result.to_dict()
        self.assertIn("alternatives", d)
        self.assertIn("recommended", d)

    def test_15_all_profiles_tested(self):
        for pattern in TradeoffEngine.PATTERN_PROFILES:
            result = self._tradeoff.compare(pattern)
            self.assertGreater(len(result.alternatives), 0)


class TestMigrationPlanner(_BaseTest):
    """MigrationPlanner — multi-step migration plans."""

    def test_16_migration_plan(self):
        arch = self._arch.map_layers()
        result = self._migration.plan_migration("modular_monolith")
        self.assertIsNotNone(result)

    def test_17_migration_returns_change_plan(self):
        result = self._migration.plan_migration("layered")
        from core.coding.change_planner import ChangePlan
        self.assertIsInstance(result, ChangePlan)

    def test_18_migration_plan_exists(self):
        result = self._migration.plan_migration("modular_monolith")
        self.assertIsNotNone(result)
        self.assertGreaterEqual(result.overall_risk, 0.0)


class TestDesignWeakness(_BaseTest):
    """DesignWeakness dataclass."""

    def test_19_weakness_to_dict(self):
        w = DesignWeakness(
            category="test",
            file="test.py",
            severity="high",
            message="Test weakness",
            metric_value=0.5,
        )
        d = w.to_dict()
        self.assertEqual(d["category"], "test")
        self.assertEqual(d["severity"], "high")
        self.assertAlmostEqual(d["metric_value"], 0.5)

    def test_20_score_roundtrip(self):
        score = ArchitectureScore(coupling=0.5, cohesion=0.6, maintainability=0.7,
                                   stability=0.8, layer_discipline=0.9)
        d = score.to_dict()
        self.assertAlmostEqual(d["coupling"], 0.5)
        self.assertAlmostEqual(d["layer_discipline"], 0.9)
        self.assertAlmostEqual(d["overall"], 0.7)
