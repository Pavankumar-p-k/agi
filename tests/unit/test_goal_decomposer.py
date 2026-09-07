"""GoalDecomposer — multi-feature parallel decomposition tests."""

import unittest
from core.planner.decomposer import GoalDecomposer, _find_features, _normalize_feature_name


class TestFindFeatures(unittest.TestCase):
    """Tests for the _find_features helper."""

    def test_with_list(self):
        """'with X, Y, Z' extracts X, Y, Z."""
        result = _find_features("build coffee shop app with payments, loyalty, analytics")
        self.assertEqual(result, ["payments", "loyalty", "analytics"])

    def test_with_and(self):
        """'with X and Y' extracts X, Y."""
        result = _find_features("build app with payments and loyalty")
        self.assertEqual(result, ["payments", "loyalty"])

    def test_with_list_and(self):
        """'with X, Y, and Z' extracts X, Y, Z."""
        result = _find_features("build app with payments, loyalty, and analytics")
        self.assertEqual(result, ["payments", "loyalty", "analytics"])

    def test_including_list(self):
        """'including X, Y, Z' extracts features."""
        result = _find_features("build app including payments, loyalty, analytics")
        self.assertEqual(result, ["payments", "loyalty", "analytics"])

    def test_featuring_list(self):
        """'featuring X, Y, Z' extracts features."""
        result = _find_features("build app featuring dark mode, push notifications")
        self.assertEqual(result, ["dark mode", "push notifications"])

    def test_with_colon(self):
        """'with: X, Y' extracts features."""
        result = _find_features("build app with: payments, loyalty")
        self.assertEqual(result, ["payments", "loyalty"])

    def test_for_colon(self):
        """'for: X, Y' extracts features."""
        result = _find_features("build app for: ios, android")
        self.assertEqual(result, ["ios", "android"])

    def test_no_features(self):
        """Plain goal with no feature list returns empty."""
        result = _find_features("build coffee shop app")
        self.assertEqual(result, [])

    def test_with_email_does_not_leak(self):
        """Features stopped before 'email' keyword."""
        result = _find_features("build app with payments, analytics and email the apk")
        self.assertEqual(result, ["payments", "analytics"])

    def test_with_build_does_not_leak(self):
        """Features stopped before 'build' keyword."""
        result = _find_features("build app with payments and build the apk")
        self.assertEqual(result, ["payments"])

    def test_multi_word_feature(self):
        """Multi-word feature names preserved."""
        result = _find_features("build app with admin dashboard, user profiles")
        self.assertEqual(result, ["admin dashboard", "user profiles"])


class TestNormalizeFeatureName(unittest.TestCase):
    """Tests for feature name normalization."""

    def test_single_word(self):
        self.assertEqual(_normalize_feature_name("payments"), "payments")

    def test_multi_word(self):
        self.assertEqual(_normalize_feature_name("admin dashboard"), "admin_dashboard")

    def test_mixed_case(self):
        self.assertEqual(_normalize_feature_name("Admin Dashboard"), "admin_dashboard")

    def test_special_chars(self):
        self.assertEqual(_normalize_feature_name("push notifications v2!"), "push_notifications_v2")


class TestGoalDecomposerParallelFeatures(unittest.TestCase):
    """Tests the GoalDecomposer for multi-feature parallel decomposition."""

    def setUp(self):
        self.decomposer = GoalDecomposer()

    def test_with_features_creates_per_feature_subgoals(self):
        """'with X, Y, Z' creates 3 build subgoals, no redundant primary."""
        tree = self.decomposer.decompose(
            "Build coffee shop app with payments, loyalty, analytics"
        )
        leaves = tree.flatten()
        # Should have 3 feature subgoals
        build_leaves = [l for l in leaves if l.step_name == "build"]
        self.assertEqual(len(build_leaves), 3)
        descriptions = [l.description for l in build_leaves]
        self.assertIn("Implement: payments", descriptions)
        self.assertIn("Implement: loyalty", descriptions)
        self.assertIn("Implement: analytics", descriptions)
        # Each should have a normalized feature parameter
        params = [l.parameters.get("feature") for l in build_leaves]
        self.assertIn("payments", params)
        self.assertIn("loyalty", params)
        self.assertIn("analytics", params)

    def test_no_features_single_primary(self):
        """Plain goal without features creates single primary build."""
        tree = self.decomposer.decompose("Build coffee shop app")
        leaves = tree.flatten()
        build_leaves = [l for l in leaves if l.step_name == "build"]
        self.assertEqual(len(build_leaves), 1)

    def test_sentence_list_components(self):
        """Sentence-list goals create per-component subgoals."""
        tree = self.decomposer.decompose(
            "Build coffee shop platform. Payments module. Loyalty system. Analytics dashboard."
        )
        leaves = tree.flatten()
        build_leaves = [l for l in leaves if l.step_name == "build"]
        # At least 3 component build subgoals
        self.assertGreaterEqual(len(build_leaves), 3)

    def test_including_creates_features(self):
        """'including X, Y, Z' creates per-feature subgoals."""
        tree = self.decomposer.decompose(
            "Build app including payments, loyalty, analytics"
        )
        leaves = tree.flatten()
        build_leaves = [l for l in leaves if l.step_name == "build"]
        self.assertEqual(len(build_leaves), 3)

    def test_with_list_and_standalone_email(self):
        """Features + standalone email creates build subgoals + email."""
        tree = self.decomposer.decompose(
            "Build app with payments, loyalty and email the results"
        )
        leaves = tree.flatten()
        build_leaves = [l for l in leaves if l.step_name == "build"]
        email_leaves = [l for l in leaves if l.step_name == "email"]
        self.assertEqual(len(build_leaves), 2)
        self.assertEqual(len(email_leaves), 1)

    def test_multi_word_feature_preserved(self):
        """Multi-word feature names preserved in parameters."""
        tree = self.decomposer.decompose(
            "Build app with admin dashboard, user profiles"
        )
        leaves = tree.flatten()
        build_leaves = [l for l in leaves if l.step_name == "build"]
        params = [l.parameters.get("feature") for l in build_leaves]
        self.assertIn("admin_dashboard", params)
        self.assertIn("user_profiles", params)

    def test_requirements_section_features(self):
        """'Requirements: X, Y, Z' creates per-component build subgoals."""
        tree = self.decomposer.decompose(
            "Build coffee shop platform. Requirements: payments, loyalty, analytics."
        )
        leaves = tree.flatten()
        build_leaves = [l for l in leaves if l.step_name == "build"]
        # Should create build subgoals for listed requirements
        self.assertGreaterEqual(len(build_leaves), 3)


class TestGoalDecomposerPhaseStructure(unittest.TestCase):
    """Tests phase-structured goals still decompose correctly."""

    def setUp(self):
        self.decomposer = GoalDecomposer()

    def test_research_build_email_phases(self):
        """Multi-phase goal creates research + build + email subgoals."""
        tree = self.decomposer.decompose("Research coffee trends, then build app, then email report")
        leaves = tree.flatten()
        step_names = [l.step_name for l in leaves]
        self.assertIn("research", step_names)
        self.assertIn("build", step_names)
        self.assertIn("email", step_names)

    def test_research_with_features(self):
        """Research + build with features includes build subgoals for each feature."""
        tree = self.decomposer.decompose(
            "Research competitors, then build app with payments, loyalty"
        )
        leaves = tree.flatten()
        build_leaves = [l for l in leaves if l.step_name == "build"]
        self.assertGreaterEqual(len(build_leaves), 2)
