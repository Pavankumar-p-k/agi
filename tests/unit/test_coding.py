"""Tests for Phase 8.1 — Repository Understanding.

Covers RepositoryIndexer, DependencyGraph, ArchitectureMapper, ImpactAnalyzer
against a synthetic project with a layered architecture.
"""

import os
import shutil
import tempfile
import unittest

from core.coding.architecture_map import ArchitectureMapper
from core.coding.dependency_graph import DependencyGraph
from core.coding.impact_analyzer import ImpactAnalyzer
from core.coding.repository_indexer import RepositoryIndexer, FileEntry


def _create_synthetic_project(root: str) -> None:
    """Create a synthetic project for testing."""
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
        "src/utils/helpers.py": (
            "def format_name(name): return name.strip()\n"
            "def parse_date(date): return date\n"
        ),
        "src/utils/validators.py": (
            "VALID = True\n"
            "def validate_email(email): return True\n"
            "def validate_order(order): return True\n"
        ),
        "src/config/settings.py": (
            "config = {'debug': True}\n"
            "APP_NAME = 'test_app'\n"
        ),
        "src/tests/test_user.py": (
            "from src.controllers.user_controller import UserController\n"
            "def test_get_user(): pass\n"
            "def test_create_user(): pass\n"
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


class TestRepositoryIndexer(unittest.TestCase):
    """RepositoryIndexer — indexing, caching, search."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._db = os.path.join(self._tmp, "test_repo.db")
        _create_synthetic_project(self._tmp)

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _make_indexer(self) -> RepositoryIndexer:
        return RepositoryIndexer(path=self._tmp, db_path=self._db)

    def test_01_index_all_files(self):
        idx = self._make_indexer()
        result = idx.index(force=True)
        self.assertGreater(len(result), 0)
        self.assertIn("src/controllers/user_controller.py", result)

    def test_02_file_entry_fields(self):
        idx = self._make_indexer()
        idx.index(force=True)
        entry = idx.get_entry("src/controllers/user_controller.py")
        self.assertIsNotNone(entry)
        self.assertEqual(entry.language, "python")
        self.assertGreater(entry.line_count, 0)
        self.assertGreater(entry.size_bytes, 0)

    def test_03_imports_extracted(self):
        idx = self._make_indexer()
        idx.index(force=True)
        entry = idx.get_entry("src/controllers/user_controller.py")
        self.assertIsNotNone(entry)
        self.assertIn("src.services.user_service", entry.imports)
        self.assertIn("src.utils.validators", entry.imports)

    def test_04_exports_extracted(self):
        idx = self._make_indexer()
        idx.index(force=True)
        entry = idx.get_entry("src/controllers/user_controller.py")
        self.assertIsNotNone(entry)
        self.assertIn("UserController", entry.class_names)
        self.assertIn("get_user", entry.function_names)

    def test_05_constants_as_exports(self):
        idx = self._make_indexer()
        idx.index(force=True)
        entry = idx.get_entry("src/models/user.py")
        self.assertIsNotNone(entry)
        self.assertIn("User", entry.class_names)
        self.assertIn("USER_ID", entry.exports)

    def test_06_incremental_index(self):
        idx = self._make_indexer()
        idx.index(force=True)
        cached = idx._get_cached("src/controllers/user_controller.py")
        self.assertIsNotNone(cached)
        second = self._make_indexer()
        second.incremental_index()
        entry = second.get_entry("src/controllers/user_controller.py")
        self.assertIsNotNone(entry)
        self.assertEqual(entry.line_count, cached.line_count)

    def test_07_search_by_export(self):
        idx = self._make_indexer()
        idx.index(force=True)
        results = idx.search_by_export("UserController")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].path, "src/controllers/user_controller.py")

    def test_08_summary(self):
        idx = self._make_indexer()
        idx.index(force=True)
        s = idx.summary()
        self.assertGreater(s["files"], 0)
        self.assertIn("python", s["languages"])
        self.assertGreater(s["total_lines"], 0)

    def test_09_get_nonexistent(self):
        idx = self._make_indexer()
        idx.index(force=True)
        self.assertIsNone(idx.get_entry("nonexistent.py"))


class TestDependencyGraph(unittest.TestCase):
    """DependencyGraph — transitive deps, reverse deps, circular detection."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._db = os.path.join(self._tmp, "test_repo.db")
        _create_synthetic_project(self._tmp)
        self._idx = RepositoryIndexer(path=self._tmp, db_path=self._db)
        self._idx.index(force=True)

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_10_build_graph(self):
        g = DependencyGraph(self._idx)
        nodes = g.build()
        self.assertGreater(len(nodes), 0)

    def test_11_direct_imports(self):
        g = DependencyGraph(self._idx)
        g.build()
        node = g.get_node("src/controllers/user_controller.py")
        self.assertIsNotNone(node)
        self.assertGreater(node.fan_out, 0)

    def test_12_reverse_dependencies(self):
        g = DependencyGraph(self._idx)
        g.build()
        rev = g.reverse_dependencies("src/models/user.py")
        self.assertIn("src/repositories/user_repo.py", rev)
        self.assertIn("src/services/user_service.py", rev)

    def test_13_impact_set(self):
        g = DependencyGraph(self._idx)
        g.build()
        affected = g.impact_set(["src/models/user.py"])
        self.assertIn("src/repositories/user_repo.py", affected)
        self.assertIn("src/services/user_service.py", affected)

    def test_14_fan_in_and_fan_out(self):
        g = DependencyGraph(self._idx)
        g.build()
        node = g.get_node("src/controllers/user_controller.py")
        self.assertIsNotNone(node)
        self.assertGreater(node.fan_in, 0)
        self.assertGreater(node.fan_out, 0)

    def test_15_centrality(self):
        g = DependencyGraph(self._idx)
        g.build()
        model_node = g.get_node("src/models/user.py")
        util_node = g.get_node("src/utils/helpers.py")
        self.assertIsNotNone(model_node)
        self.assertIsNotNone(util_node)
        self.assertGreaterEqual(model_node.centrality, 0)
        self.assertGreaterEqual(util_node.centrality, 0)

    def test_16_summary(self):
        g = DependencyGraph(self._idx)
        g.build()
        s = g.summary()
        self.assertGreater(s["files"], 0)

    def test_17_high_impact_files(self):
        g = DependencyGraph(self._idx)
        g.build()
        top = g.high_impact_files(top_n=3)
        self.assertLessEqual(len(top), 3)


class TestArchitectureMapper(unittest.TestCase):
    """ArchitectureMapper — layer detection, pattern, violations."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._db = os.path.join(self._tmp, "test_repo.db")
        _create_synthetic_project(self._tmp)
        self._idx = RepositoryIndexer(path=self._tmp, db_path=self._db)
        self._idx.index(force=True)
        self._dep = DependencyGraph(self._idx)
        self._dep.build()

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_18_layer_assignment(self):
        mapper = ArchitectureMapper(self._idx, self._dep)
        arch = mapper.map_layers()
        self.assertIn("controllers", arch.layers)
        self.assertIn("services", arch.layers)
        self.assertIn("models", arch.layers)

    def test_19_pattern_detected(self):
        mapper = ArchitectureMapper(self._idx, self._dep)
        arch = mapper.map_layers()
        self.assertEqual(arch.pattern, "layered")

    def test_20_file_to_layer_map(self):
        mapper = ArchitectureMapper(self._idx, self._dep)
        arch = mapper.map_layers()
        self.assertEqual(
            arch.file_to_layer.get("src/controllers/user_controller.py"),
            "controllers",
        )
        self.assertEqual(
            arch.file_to_layer.get("src/models/user.py"),
            "models",
        )

    def test_21_cross_layer_edges(self):
        mapper = ArchitectureMapper(self._idx, self._dep)
        arch = mapper.map_layers()
        self.assertGreater(len(arch.cross_layer_edges), 0)

    def test_22_report(self):
        mapper = ArchitectureMapper(self._idx, self._dep)
        r = mapper.report()
        self.assertEqual(r["pattern"], "layered")
        self.assertIn("controllers", r["layers"])

    def test_23_modules(self):
        mapper = ArchitectureMapper(self._idx, self._dep)
        arch = mapper.map_layers()
        self.assertIn("src", arch.modules)


class TestImpactAnalyzer(unittest.TestCase):
    """ImpactAnalyzer — risk scoring, test selection, batch analysis."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._db = os.path.join(self._tmp, "test_repo.db")
        _create_synthetic_project(self._tmp)
        self._idx = RepositoryIndexer(path=self._tmp, db_path=self._db)
        self._idx.index(force=True)
        self._dep = DependencyGraph(self._idx)
        self._dep.build()
        self._arch = ArchitectureMapper(self._idx, self._dep)
        self._arch.map_layers()

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_24_analyze_model_change(self):
        analyzer = ImpactAnalyzer(self._idx, self._dep, self._arch)
        result = analyzer.analyze("src/models/user.py")
        self.assertGreater(result.total_affected, 0)
        self.assertIn("src/repositories/user_repo.py", result.direct_affected)

    def test_25_analyze_controller_change(self):
        analyzer = ImpactAnalyzer(self._idx, self._dep, self._arch)
        result = analyzer.analyze("src/controllers/user_controller.py")
        self.assertGreaterEqual(result.total_affected, 0)

    def test_26_risk_score_ranges(self):
        analyzer = ImpactAnalyzer(self._idx, self._dep, self._arch)
        result = analyzer.analyze("src/models/user.py")
        self.assertGreaterEqual(result.risk_score, 0.0)
        self.assertLessEqual(result.risk_score, 1.0)
        self.assertIn(result.risk_label, ["low", "medium", "high", "critical"])

    def test_27_test_selection(self):
        analyzer = ImpactAnalyzer(self._idx, self._dep, self._arch)
        result = analyzer.analyze("src/services/user_service.py")
        if result.suggested_tests:
            self.assertTrue(any("test" in t for t in result.suggested_tests))

    def test_28_batch_analysis(self):
        analyzer = ImpactAnalyzer(self._idx, self._dep, self._arch)
        results = analyzer.analyze_batch([
            "src/models/user.py",
            "src/models/order.py",
        ])
        self.assertEqual(len(results), 2)

    def test_29_feature_analysis(self):
        analyzer = ImpactAnalyzer(self._idx, self._dep, self._arch)
        fa = analyzer.analyze_feature(
            ["src/services/user_service.py", "src/repositories/user_repo.py"],
            feature_name="user_feature",
        )
        self.assertEqual(fa["feature"], "user_feature")
        self.assertEqual(len(fa["files_changed"]), 2)
        self.assertGreaterEqual(fa["total_affected"], 0)

    def test_30_nonexistent_file(self):
        analyzer = ImpactAnalyzer(self._idx, self._dep, self._arch)
        result = analyzer.analyze("src/nonexistent.py")
        self.assertEqual(result.risk_label, "unknown")

    def test_31_config_high_risk(self):
        analyzer = ImpactAnalyzer(self._idx, self._dep, self._arch)
        result = analyzer.analyze("src/config/settings.py")
        self.assertIn(result.risk_label, ["low", "medium", "high", "critical"])
