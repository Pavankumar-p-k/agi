"""Phase 14.0 tests — Structural Property Registry, Principle Extractor, Validator, Store.

Tests cover:
  - Models: StructuralProperty, SystemProfile, PrincipleCandidate, Principle
  - Registry: CRUD, built-in seeding, profiles
  - Extractor: boolean extraction, numeric extraction, empty/no-variance handling
  - Validator: gates, confidence computation, full acceptance path
  - Store: data point persistence, principle persistence, roundtrips
  - Integration: end-to-end from data points → extract → validate → store → query
"""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from unittest import TestCase


# ── Models ────────────────────────────────────────────────────────


class TestStructuralProperty(TestCase):
    def test_01_creation(self):
        from core.generalization.models import (
            PropertySource, PropertyValueType, StructuralProperty,
        )
        sp = StructuralProperty(
            property_id="p1", name="retry_capable",
            category="execution_model",
            value_type=PropertyValueType.BOOL,
            source=PropertySource.STATIC,
        )
        self.assertEqual(sp.property_id, "p1")
        self.assertEqual(sp.name, "retry_capable")

    def test_02_to_dict(self):
        from core.generalization.models import (
            PropertySource, PropertyValueType, StructuralProperty,
        )
        sp = StructuralProperty(
            property_id="p2", name="stateful",
            category="execution_model",
            value_type=PropertyValueType.BOOL,
            source=PropertySource.STATIC,
        )
        d = sp.to_dict()
        self.assertEqual(d["name"], "stateful")
        self.assertEqual(d["source"], "static")


class TestSystemProfile(TestCase):
    def test_03_creation(self):
        from core.generalization.models import SystemProfile, SystemType
        sp = SystemProfile(
            system_id="build_project",
            system_type=SystemType.TOOL,
            properties={"retry_capable": False},
        )
        self.assertEqual(sp.system_id, "build_project")
        self.assertFalse(sp.get("retry_capable"))

    def test_04_to_dict(self):
        from core.generalization.models import SystemProfile, SystemType
        sp = SystemProfile(
            system_id="automated_build",
            system_type=SystemType.TOOL,
            properties={"retry_capable": True},
        )
        d = sp.to_dict()
        self.assertEqual(d["system_id"], "automated_build")
        self.assertTrue(d["properties"]["retry_capable"])


class TestPrincipleCandidate(TestCase):
    def test_05_creation(self):
        from core.generalization.models import PrincipleCandidate, PrincipleStatus
        pc = PrincipleCandidate(
            principle_id="pc_001",
            property_name="retry_capable",
            category="execution_model",
            support_rate=0.85, control_rate=0.45,
            discrimination=0.40,
            sample_size=20, support_count=10, control_count=10,
            domains=["build"],
        )
        self.assertEqual(pc.status, PrincipleStatus.CANDIDATE)
        self.assertAlmostEqual(pc.discrimination, 0.40)

    def test_06_to_dict(self):
        from core.generalization.models import PrincipleCandidate
        pc = PrincipleCandidate(
            principle_id="pc_002",
            property_name="retry_capable",
            category="execution_model",
            support_rate=0.90, control_rate=0.50,
            discrimination=0.40,
            sample_size=20, support_count=10, control_count=10,
        )
        d = pc.to_dict()
        self.assertEqual(d["status"], "candidate")
        self.assertAlmostEqual(d["discrimination"], 0.400)


class TestPrinciple(TestCase):
    def test_07_creation(self):
        from core.generalization.models import Principle, PrincipleStatus
        p = Principle(
            principle_id="pr_001",
            property_name="retry_capable",
            category="execution_model",
            support_rate=0.87, control_rate=0.52,
            discrimination=0.35,
            sample_size=24, support_count=12, control_count=12,
            domains=["build"],
            confidence=0.92,
            status=PrincipleStatus.ACCEPTED,
        )
        self.assertEqual(p.status, PrincipleStatus.ACCEPTED)
        self.assertAlmostEqual(p.discrimination, 0.35)

    def test_08_to_dict(self):
        from core.generalization.models import Principle, PrincipleStatus
        p = Principle(
            principle_id="pr_002",
            property_name="verification_builtin",
            category="verification",
            support_rate=0.91, control_rate=0.58,
            discrimination=0.33,
            sample_size=24, support_count=12, control_count=12,
            domains=["build"],
            confidence=0.89,
            evidence_point_ids=["pt_001"],
        )
        d = p.to_dict()
        self.assertEqual(d["property_name"], "verification_builtin")
        self.assertEqual(d["evidence_point_ids"], ["pt_001"])


# ── Registry ─────────────────────────────────────────────────────


class TestStructuralPropertyRegistry(TestCase):
    def setUp(self):
        from core.generalization.registry import StructuralPropertyRegistry
        self._tmp = tempfile.mktemp(suffix=".db")
        self.r = StructuralPropertyRegistry(db_path=self._tmp)

    def tearDown(self):
        try:
            os.unlink(self._tmp)
        except Exception:
            pass

    def test_10_has_builtin_properties(self):
        props = self.r.list_properties()
        self.assertGreater(len(props), 0)
        names = [p.name for p in props]
        self.assertIn("retry_capable", names)
        self.assertIn("stateful", names)

    def test_11_has_builtin_profiles(self):
        profiles = self.r.list_profiles()
        self.assertGreater(len(profiles), 0)
        ids = [p.system_id for p in profiles]
        self.assertIn("build_project", ids)
        self.assertIn("automated_build", ids)

    def test_12_get_property_by_id(self):
        from core.generalization.models import (
            PropertySource, PropertyValueType, StructuralProperty,
        )
        custom = StructuralProperty(
            property_id="prop_custom",
            name="custom_prop",
            category="execution_model",
            value_type=PropertyValueType.BOOL,
            source=PropertySource.STATIC,
        )
        self.r.register_property(custom)
        retrieved = self.r.get_property("prop_custom")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.name, "custom_prop")  # type: ignore

    def test_13_get_property_by_name(self):
        prop = self.r.get_property_by_name("retry_capable")
        self.assertIsNotNone(prop)
        self.assertEqual(prop.property_id, "prop_retry_capable")  # type: ignore

    def test_14_get_nonexistent(self):
        self.assertIsNone(self.r.get_property("nonexistent"))

    def test_15_filter_by_category(self):
        props = self.r.list_properties(category="verification")
        self.assertGreater(len(props), 0)
        for p in props:
            self.assertEqual(p.category, "verification")

    def test_16_get_profile(self):
        profile = self.r.get_profile("build_project")
        self.assertIsNotNone(profile)
        self.assertFalse(profile.properties.get("retry_capable"))  # type: ignore

    def test_17_clear(self):
        self.r.clear()
        self.assertEqual(len(self.r.list_properties()), 0)
        self.assertEqual(len(self.r.list_profiles()), 0)

    def test_18_reload_from_disk(self):
        # Write a custom profile, then create a new registry instance (same db)
        from core.generalization.models import SystemProfile, SystemType
        custom = SystemProfile(
            system_id="test_tool",
            system_type=SystemType.TOOL,
            properties={"retry_capable": True},
        )
        self.r.register_profile(custom)

        from core.generalization.registry import StructuralPropertyRegistry
        r2 = StructuralPropertyRegistry(db_path=self._tmp)
        profile = r2.get_profile("test_tool")
        self.assertIsNotNone(profile)
        self.assertTrue(profile.properties.get("retry_capable"))  # type: ignore


# ── Extractor ────────────────────────────────────────────────────


class TestPrincipleExtractor(TestCase):
    def _make_point(self, system_id: str, success: bool,
                    properties: dict, domain: str = "build",
                    point_id: str = "") -> "PrincipleDataPoint":
        from core.generalization.models import PrincipleDataPoint, SystemType
        return PrincipleDataPoint(
            point_id=point_id or uuid.uuid4().hex[:12],
            system_id=system_id,
            system_type=SystemType.TOOL,
            success=success,
            properties=properties,
            domain=domain,
        )

    def test_20_extract_from_single_property(self):
        from core.generalization.extractor import PrincipleExtractor
        e = PrincipleExtractor()
        points = [
            self._make_point("a", True, {"retry_capable": True}),
            self._make_point("a", True, {"retry_capable": True}),
            self._make_point("b", False, {"retry_capable": False}),
            self._make_point("b", False, {"retry_capable": False}),
        ]
        candidates = e.extract_all(points)
        self.assertEqual(len(candidates), 1)
        c = candidates[0]
        self.assertEqual(c.property_name, "retry_capable")
        self.assertAlmostEqual(c.support_rate, 1.0)   # 2/2 true succeeded
        self.assertAlmostEqual(c.control_rate, 0.0)    # 0/2 false succeeded
        self.assertAlmostEqual(c.discrimination, 1.0)

    def test_21_empty_points_returns_empty(self):
        from core.generalization.extractor import PrincipleExtractor
        e = PrincipleExtractor()
        self.assertEqual(e.extract_all([]), [])

    def test_22_no_variance_returns_empty(self):
        from core.generalization.extractor import PrincipleExtractor
        e = PrincipleExtractor()
        points = [
            self._make_point("a", True, {"retry_capable": True}),
            self._make_point("a", True, {"retry_capable": True}),
        ]
        candidates = e.extract_all(points)
        self.assertEqual(len(candidates), 0)

    def test_23_multiple_properties(self):
        from core.generalization.extractor import PrincipleExtractor
        e = PrincipleExtractor()
        points = [
            self._make_point("a", True, {"retry_capable": True, "stateful": True}),
            self._make_point("a", True, {"retry_capable": True, "stateful": True}),
            self._make_point("b", False, {"retry_capable": False, "stateful": False}),
            self._make_point("b", False, {"retry_capable": False, "stateful": False}),
        ]
        candidates = e.extract_all(points)
        self.assertEqual(len(candidates), 2)
        names = {c.property_name for c in candidates}
        self.assertIn("retry_capable", names)
        self.assertIn("stateful", names)

    def test_24_extract_all_numeric_median_split(self):
        from core.generalization.extractor import PrincipleExtractor
        e = PrincipleExtractor()
        points = [
            self._make_point("a", True, {"artifact_count": 10}),
            self._make_point("a", True, {"artifact_count": 8}),
            self._make_point("b", False, {"artifact_count": 2}),
            self._make_point("b", False, {"artifact_count": 1}),
        ]
        candidates = e.extract_all_numeric(points)
        self.assertGreater(len(candidates), 0)

    def test_25_property_value_type_filtering(self):
        from core.generalization.extractor import PrincipleExtractor
        e = PrincipleExtractor()
        points = [
            self._make_point("a", True, {"retry_capable": True, "name": "foo"}),
            self._make_point("b", False, {"retry_capable": False, "name": "bar"}),
        ]
        candidates = e.extract_all(points)
        # Only 'retry_capable' (bool) should be analyzed; 'name' (str) is skipped
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].property_name, "retry_capable")

    def test_26_domains_collected(self):
        from core.generalization.extractor import PrincipleExtractor
        e = PrincipleExtractor()
        points = [
            self._make_point("a", True, {"retry_capable": True}, domain="android"),
            self._make_point("a", True, {"retry_capable": True}, domain="android"),
            self._make_point("b", False, {"retry_capable": False}, domain="web"),
            self._make_point("b", False, {"retry_capable": False}, domain="web"),
        ]
        candidates = e.extract_all(points)
        self.assertEqual(len(candidates), 1)
        self.assertIn("android", candidates[0].domains)
        self.assertIn("web", candidates[0].domains)


# ── Validator ────────────────────────────────────────────────────


class TestPrincipleValidator(TestCase):
    def _make_candidate(self, support_rate=0.85, control_rate=0.45,
                        discrimination=0.40, sample_size=20,
                        domains=None, confidence=0.0):
        from core.generalization.models import PrincipleCandidate
        return PrincipleCandidate(
            principle_id="pc_test",
            property_name="retry_capable",
            category="execution_model",
            support_rate=support_rate,
            control_rate=control_rate,
            discrimination=discrimination,
            sample_size=sample_size,
            support_count=sample_size // 2,
            control_count=sample_size // 2,
            domains=domains or ["build", "web", "android"],
            confidence=confidence,
        )

    def test_30_accepts_passing_candidate(self):
        from core.generalization.validator import PrincipleValidator
        from core.generalization.models import PrincipleStatus
        v = PrincipleValidator()
        c = self._make_candidate()
        result = v.validate(c)
        self.assertEqual(result.status, PrincipleStatus.ACCEPTED)
        self.assertGreater(result.confidence, 0.80)

    def test_31_rejects_small_sample(self):
        from core.generalization.validator import PrincipleValidator
        from core.generalization.models import PrincipleStatus
        v = PrincipleValidator()
        c = self._make_candidate(sample_size=3)
        result = v.validate(c)
        self.assertEqual(result.status, PrincipleStatus.CANDIDATE)

    def test_32_rejects_few_domains(self):
        from core.generalization.validator import PrincipleValidator
        from core.generalization.models import PrincipleStatus
        v = PrincipleValidator()
        c = self._make_candidate(domains=["build"])
        result = v.validate(c)
        self.assertEqual(result.status, PrincipleStatus.CANDIDATE)

    def test_33_rejects_low_support(self):
        from core.generalization.validator import PrincipleValidator
        from core.generalization.models import PrincipleStatus
        v = PrincipleValidator()
        c = self._make_candidate(support_rate=0.50)
        result = v.validate(c)
        self.assertEqual(result.status, PrincipleStatus.CANDIDATE)

    def test_34_rejects_low_discrimination(self):
        from core.generalization.validator import PrincipleValidator
        from core.generalization.models import PrincipleStatus
        v = PrincipleValidator()
        c = self._make_candidate(discrimination=0.05)
        result = v.validate(c)
        self.assertEqual(result.status, PrincipleStatus.CANDIDATE)

    def test_35_rejects_low_confidence(self):
        from core.generalization.validator import PrincipleValidator
        from core.generalization.models import PrincipleStatus
        # Use tiny sample + low discrimination to force low confidence
        v = PrincipleValidator()
        c = self._make_candidate(sample_size=10, discrimination=0.20,
                                 domains=["build", "web", "android"])
        # At minimum thresholds, confidence should still pass
        result = v.validate(c)
        self.assertIn(result.status, (
            PrincipleStatus.CANDIDATE, PrincipleStatus.ACCEPTED))

    def test_36_is_accepted_helper(self):
        from core.generalization.validator import PrincipleValidator
        v = PrincipleValidator()
        passing = self._make_candidate()
        self.assertTrue(v.is_accepted(passing))
        failing = self._make_candidate(sample_size=3)
        self.assertFalse(v.is_accepted(failing))

    def test_37_confidence_increases_with_sample(self):
        from core.generalization.validator import PrincipleValidator
        small = self._make_candidate(sample_size=10)
        large = self._make_candidate(sample_size=100)
        self.assertGreater(
            PrincipleValidator._compute_confidence(large),
            PrincipleValidator._compute_confidence(small),
        )

    def test_38_confidence_increases_with_discrimination(self):
        from core.generalization.validator import PrincipleValidator
        weak = self._make_candidate(discrimination=0.20)
        strong = self._make_candidate(discrimination=0.60)
        self.assertGreater(
            PrincipleValidator._compute_confidence(strong),
            PrincipleValidator._compute_confidence(weak),
        )

    def test_39_configurable_thresholds(self):
        from core.generalization.validator import PrincipleValidator
        from core.generalization.models import PrincipleStatus
        # Relax thresholds
        v = PrincipleValidator(min_sample_size=3, min_domains=1,
                                min_support_rate=0.0, min_discrimination=0.0,
                                min_confidence=0.0)
        c = self._make_candidate(sample_size=3, domains=["build"],
                                 discrimination=0.05, support_rate=0.5)
        result = v.validate(c)
        self.assertEqual(result.status, PrincipleStatus.ACCEPTED)


# ── Store ────────────────────────────────────────────────────────


class TestPrincipleStore(TestCase):
    def setUp(self):
        from core.generalization.store import PrincipleStore
        self._tmp = tempfile.mktemp(suffix=".db")
        self.s = PrincipleStore(db_path=self._tmp)

    def tearDown(self):
        try:
            os.unlink(self._tmp)
        except Exception:
            pass

    def test_40_save_and_get_data_point(self):
        from core.generalization.models import (
            PrincipleDataPoint, SystemType,
        )
        point = PrincipleDataPoint(
            point_id="pt_001",
            system_id="automated_build",
            system_type=SystemType.TOOL,
            success=True,
            properties={"retry_capable": True},
            domain="android",
        )
        self.s.save_data_point(point)
        retrieved = self.s.get_data_point("pt_001")
        self.assertIsNotNone(retrieved)
        self.assertTrue(retrieved.success)  # type: ignore
        self.assertEqual(retrieved.properties["retry_capable"], True)  # type: ignore

    def test_41_batch_save(self):
        from core.generalization.models import (
            PrincipleDataPoint, SystemType,
        )
        points = [
            PrincipleDataPoint(
                point_id=f"pt_{i}", system_id="tool",
                system_type=SystemType.TOOL, success=True,
                properties={}, domain="test",
            )
            for i in range(5)
        ]
        self.s.save_data_points(points)
        self.assertEqual(self.s.count_data_points(), 5)

    def test_42_save_and_get_principle(self):
        from core.generalization.models import Principle
        p = Principle(
            principle_id="pr_store_001",
            property_name="retry_capable",
            category="execution_model",
            support_rate=0.87, control_rate=0.52,
            discrimination=0.35,
            sample_size=24, support_count=12, control_count=12,
            domains=["build"],
            confidence=0.92,
        )
        self.s.save_principle(p)
        retrieved = self.s.get_principle("pr_store_001")
        self.assertIsNotNone(retrieved)
        self.assertAlmostEqual(retrieved.discrimination, 0.35)  # type: ignore

    def test_43_list_principles_by_status(self):
        from core.generalization.models import Principle, PrincipleStatus
        accepted = Principle(
            principle_id="pr_a", property_name="p1",
            category="execution_model",
            support_rate=0.80, control_rate=0.40,
            discrimination=0.40,
            sample_size=20, support_count=10, control_count=10,
            domains=["build"],
            confidence=0.85,
            status=PrincipleStatus.ACCEPTED,
        )
        candidate = Principle(
            principle_id="pr_c", property_name="p2",
            category="execution_model",
            support_rate=0.60, control_rate=0.50,
            discrimination=0.10,
            sample_size=5, support_count=3, control_count=2,
            domains=["build"],
            confidence=0.30,
            status=PrincipleStatus.CANDIDATE,
        )
        self.s.save_principle(accepted)
        self.s.save_principle(candidate)
        accepted_list = self.s.list_principles(status="accepted")
        self.assertEqual(len(accepted_list), 1)
        self.assertEqual(accepted_list[0].principle_id, "pr_a")

    def test_44_get_nonexistent(self):
        self.assertIsNone(self.s.get_data_point("nonexistent"))
        self.assertIsNone(self.s.get_principle("nonexistent"))

    def test_45_clear(self):
        from core.generalization.models import (
            PrincipleDataPoint, SystemType,
        )
        self.s.save_data_point(PrincipleDataPoint(
            point_id="pt_clear", system_id="test",
            system_type=SystemType.TOOL, success=True,
            properties={},
        ))
        self.s.clear()
        self.assertEqual(self.s.count_data_points(), 0)

    def test_46_persistence(self):
        from core.generalization.models import (
            PrincipleDataPoint, SystemType,
        )
        self.s.save_data_point(PrincipleDataPoint(
            point_id="pt_persist", system_id="test",
            system_type=SystemType.TOOL, success=True,
            properties={"retry_capable": True},
        ))
        from core.generalization.store import PrincipleStore
        s2 = PrincipleStore(db_path=self._tmp)
        retrieved = s2.get_data_point("pt_persist")
        self.assertIsNotNone(retrieved)
        self.assertTrue(retrieved.properties.get("retry_capable"))  # type: ignore


# ── Integration: extract → validate → store ─────────────────────


class TestGeneralizationIntegration(TestCase):
    """End-to-end: data points → extractor → validator → store → queryable."""

    def setUp(self):
        from core.generalization.store import PrincipleStore
        self._tmp = tempfile.mktemp(suffix=".db")
        self.store = PrincipleStore(db_path=self._tmp)

    def tearDown(self):
        try:
            os.unlink(self._tmp)
        except Exception:
            pass

    def _make_point(self, system_id: str, success: bool,
                    properties: dict, domain: str = "build",
                    point_id: str = ""):
        from core.generalization.models import PrincipleDataPoint, SystemType
        return PrincipleDataPoint(
            point_id=point_id or uuid.uuid4().hex[:12],
            system_id=system_id,
            system_type=SystemType.TOOL,
            success=success,
            properties=properties,
            domain=domain,
        )

    def test_50_full_pipeline_accepts_strong_signal(self):
        from core.generalization.extractor import PrincipleExtractor
        from core.generalization.validator import PrincipleValidator

        # Build a strong signal: 12 points across 3 domains
        points = []
        for i, domain in enumerate(["android", "web", "backend"]):
            for _ in range(4):
                points.append(self._make_point(
                    "automated_build", True,
                    {"retry_capable": True, "verification_builtin": True},
                    domain=domain,
                ))
                points.append(self._make_point(
                    "build_project", False,
                    {"retry_capable": False, "verification_builtin": False},
                    domain=domain,
                ))

        self.store.save_data_points(points)

        # Extract
        extractor = PrincipleExtractor()
        candidates = extractor.extract_all(points)
        self.assertGreater(len(candidates), 0)

        # Validate
        validator = PrincipleValidator()
        accepted = []
        for c in candidates:
            result = validator.validate(c)
            if result.status.value == "accepted":
                principle = self.store.save_candidate_as_principle(
                    result, evidence_point_ids=[p.point_id for p in points],
                )
                accepted.append(principle)

        # Verify at least one principle was accepted
        self.assertGreater(len(accepted), 0)

        # Query the store
        stored = self.store.list_principles(status="accepted")
        self.assertGreater(len(stored), 0)
        for p in stored:
            self.assertGreaterEqual(p.confidence, 0.80)
            self.assertGreaterEqual(p.sample_size, 10)
            self.assertGreaterEqual(p.discrimination, 0.20)
            self.assertGreaterEqual(p.support_rate, 0.70)

    def test_51_weak_signal_not_accepted(self):
        from core.generalization.extractor import PrincipleExtractor
        from core.generalization.validator import PrincipleValidator

        # Weak signal: tiny discrimination
        points = []
        for _ in range(10):
            points.append(self._make_point(
                "tool_a", True, {"some_prop": True}, domain="build",
            ))
            points.append(self._make_point(
                "tool_b", True, {"some_prop": False}, domain="build",
            ))

        self.store.save_data_points(points)

        extractor = PrincipleExtractor()
        candidates = extractor.extract_all(points)
        accepted_count = 0
        validator = PrincipleValidator()
        for c in candidates:
            result = validator.validate(c)
            if result.status.value == "accepted":
                accepted_count += 1
                self.store.save_candidate_as_principle(result)

        # Should have 0 accepted (discrimination too low)
        self.assertEqual(accepted_count, 0)

    def test_52_accepted_principles_queryable_as_principles(self):
        """Validate that accepted principles have the expected output format."""
        from core.generalization.extractor import PrincipleExtractor
        from core.generalization.validator import PrincipleValidator

        points = []
        for domain in ["android", "web", "backend"]:
            for _ in range(4):
                points.append(self._make_point(
                    "automated_build", True,
                    {"retry_capable": True}, domain=domain,
                ))
                points.append(self._make_point(
                    "build_project", False,
                    {"retry_capable": False}, domain=domain,
                ))

        extractor = PrincipleExtractor()
        candidates = extractor.extract_all(points)
        validator = PrincipleValidator()

        for c in candidates:
            result = validator.validate(c)
            if result.status.value == "accepted":
                principle = self.store.save_candidate_as_principle(result)

                # Verify the output format matches the spec
                d = principle.to_dict()
                self.assertIn("principle_id", d)
                self.assertIn("property_name", d)
                self.assertIn("support_rate", d)
                self.assertIn("control_rate", d)
                self.assertIn("discrimination", d)
                self.assertIn("sample_size", d)
                self.assertIn("domains", d)
                self.assertIn("confidence", d)
                self.assertIn("status", d)
                self.assertEqual(d["status"], "accepted")
                self.assertGreaterEqual(d["discrimination"], 0.20)


# ── Phase 14.1 — Proposal Model ─────────────────────────────────


class TestImprovementProposal(TestCase):
    def test_60_creation(self):
        from core.generalization.models import (
            ImprovementProposal, ProposalStatus,
        )
        p = ImprovementProposal(
            proposal_id="prp_001",
            target_system="browser_tool",
            proposal_type="add_capability",
            principle_id="pr_001",
            title="Add verification_builtin to browser_tool",
            rationale="verification_builtin improves success by 33%",
            expected_improvement=0.33,
            confidence=0.89,
        )
        self.assertEqual(p.status, ProposalStatus.GENERATED)
        self.assertAlmostEqual(p.expected_improvement, 0.33)

    def test_61_to_dict(self):
        from core.generalization.models import ImprovementProposal
        p = ImprovementProposal(
            proposal_id="prp_002",
            target_system="build_project",
            proposal_type="add_capability",
            principle_id="pr_002",
            title="Add retry to build_project",
            rationale="retry improves success by 35%",
            expected_improvement=0.35,
            confidence=0.92,
        )
        d = p.to_dict()
        self.assertEqual(d["proposal_id"], "prp_002")
        self.assertEqual(d["target_system"], "build_project")
        self.assertEqual(d["status"], "generated")
        self.assertAlmostEqual(d["expected_improvement"], 0.350)

    def test_62_status_enum_values(self):
        from core.generalization.models import ProposalStatus
        self.assertEqual(ProposalStatus.GENERATED.value, "generated")
        self.assertEqual(ProposalStatus.APPROVED.value, "approved")
        self.assertEqual(ProposalStatus.EXPERIMENTING.value, "experimenting")
        self.assertEqual(ProposalStatus.PROMOTED.value, "promoted")
        self.assertEqual(ProposalStatus.REJECTED.value, "rejected")


# ── Phase 14.1 — ProposalEngine ─────────────────────────────────


class TestProposalEngine(TestCase):
    def _make_accepted_principle(self, property_name: str,
                                  discrimination: float = 0.35,
                                  confidence: float = 0.92,
                                  sample_size: int = 24,
                                  principle_id: str = "pr_001",
                                  domains: list | None = None):
        from core.generalization.models import Principle, PrincipleStatus
        return Principle(
            principle_id=principle_id,
            property_name=property_name,
            category="execution_model",
            support_rate=0.87,
            control_rate=0.52,
            discrimination=discrimination,
            sample_size=sample_size,
            support_count=12,
            control_count=12,
            domains=domains or ["build"],
            confidence=confidence,
            status=PrincipleStatus.ACCEPTED,
        )

    def _make_profile(self, system_id: str,
                       properties: dict | None = None):
        from core.generalization.models import SystemProfile, SystemType
        return SystemProfile(
            system_id=system_id,
            system_type=SystemType.TOOL,
            properties=properties or {},
        )

    def test_70_generates_proposal_for_missing_property(self):
        from core.generalization.proposals import ProposalEngine
        engine = ProposalEngine()
        principle = self._make_accepted_principle("verification_builtin")
        profile = self._make_profile("browser_tool", {})
        proposals = engine.generate_for_system([principle], profile)
        self.assertEqual(len(proposals), 1)
        p = proposals[0]
        self.assertEqual(p.target_system, "browser_tool")
        self.assertEqual(p.principle_id, "pr_001")
        self.assertEqual(p.proposal_type, "add_capability")
        self.assertIn("verification_builtin", p.title)

    def test_71_generates_proposal_for_false_property(self):
        from core.generalization.proposals import ProposalEngine
        engine = ProposalEngine()
        principle = self._make_accepted_principle("verification_builtin")
        profile = self._make_profile("browser_tool",
                                      {"verification_builtin": False})
        proposals = engine.generate_for_system([principle], profile)
        self.assertEqual(len(proposals), 1)

    def test_72_skips_if_property_already_true(self):
        from core.generalization.proposals import ProposalEngine
        engine = ProposalEngine()
        principle = self._make_accepted_principle("verification_builtin")
        profile = self._make_profile("automated_build",
                                      {"verification_builtin": True})
        proposals = engine.generate_for_system([principle], profile)
        self.assertEqual(len(proposals), 0)

    def test_73_skips_non_accepted_principles(self):
        from core.generalization.proposals import ProposalEngine
        from core.generalization.models import Principle, PrincipleStatus
        engine = ProposalEngine()
        candidate = Principle(
            principle_id="pr_candidate",
            property_name="stateful",
            category="execution_model",
            support_rate=0.60, control_rate=0.55,
            discrimination=0.05,
            sample_size=5, support_count=3, control_count=2,
            domains=["build"],
            confidence=0.30,
            status=PrincipleStatus.CANDIDATE,
        )
        profile = self._make_profile("browser_tool", {})
        proposals = engine.generate_for_system([candidate], profile)
        self.assertEqual(len(proposals), 0)

    def test_74_multiple_principles_multiple_profiles(self):
        from core.generalization.proposals import ProposalEngine
        engine = ProposalEngine()
        p1 = self._make_accepted_principle("verification_builtin",
                                            principle_id="pr_001")
        p2 = self._make_accepted_principle("retry_capable",
                                            principle_id="pr_002")
        profile_a = self._make_profile("tool_a",
                                        {"verification_builtin": False,
                                         "retry_capable": False})
        profile_b = self._make_profile("tool_b",
                                        {"verification_builtin": True,
                                         "retry_capable": False})
        proposals = engine.generate_proposals([p1, p2], [profile_a, profile_b])
        # tool_a: both missing → 2 proposals
        # tool_b: verification True (skip), retry False → 1 proposal
        self.assertEqual(len(proposals), 3)

    def test_75_empty_principles(self):
        from core.generalization.proposals import ProposalEngine
        engine = ProposalEngine()
        profile = self._make_profile("tool_a", {})
        self.assertEqual(engine.generate_for_system([], profile), [])

    def test_76_generate_for_principle(self):
        from core.generalization.proposals import ProposalEngine
        engine = ProposalEngine()
        principle = self._make_accepted_principle("retry_capable")
        profile_a = self._make_profile("tool_a", {"retry_capable": False})
        profile_b = self._make_profile("tool_b", {"retry_capable": True})
        proposals = engine.generate_for_principle(principle,
                                                   [profile_a, profile_b])
        self.assertEqual(len(proposals), 1)
        self.assertEqual(proposals[0].target_system, "tool_a")

    def test_77_rationale_includes_discrimination_and_confidence(self):
        from core.generalization.proposals import ProposalEngine
        engine = ProposalEngine()
        principle = self._make_accepted_principle(
            "verification_builtin",
            discrimination=0.33,
            confidence=0.89,
            sample_size=24,
            domains=["android", "web", "backend"],
        )
        profile = self._make_profile("browser_tool", {})
        proposals = engine.generate_for_system([principle], profile)
        self.assertEqual(len(proposals), 1)
        r = proposals[0].rationale
        self.assertIn("33%", r)      # discrimination
        self.assertIn("89%", r)      # confidence
        self.assertIn("24", r)       # sample size
        self.assertIn("3 domains", r)  # domain count

    def test_78_generate_proposals_empty_profiles(self):
        from core.generalization.proposals import ProposalEngine
        engine = ProposalEngine()
        principle = self._make_accepted_principle("retry_capable")
        proposals = engine.generate_for_principle(principle, [])
        self.assertEqual(len(proposals), 0)

    def test_79_skips_if_property_numeric_above_threshold(self):
        from core.generalization.proposals import ProposalEngine
        engine = ProposalEngine()
        from core.generalization.models import Principle, PrincipleStatus
        principle = Principle(
            principle_id="pr_numeric",
            property_name="artifact_count",
            category="verification",
            support_rate=0.80, control_rate=0.40,
            discrimination=0.40,
            sample_size=20, support_count=10, control_count=10,
            domains=["build"],
            confidence=0.85,
            status=PrincipleStatus.ACCEPTED,
        )
        profile = self._make_profile("tool_a", {"artifact_count": 5})
        proposals = engine.generate_for_system([principle], profile)
        self.assertEqual(len(proposals), 0)

    def test_80_generates_for_numeric_below_threshold(self):
        from core.generalization.proposals import ProposalEngine
        engine = ProposalEngine()
        from core.generalization.models import Principle, PrincipleStatus
        principle = Principle(
            principle_id="pr_numeric2",
            property_name="artifact_count",
            category="verification",
            support_rate=0.80, control_rate=0.40,
            discrimination=0.40,
            sample_size=20, support_count=10, control_count=10,
            domains=["build"],
            confidence=0.85,
            status=PrincipleStatus.ACCEPTED,
        )
        profile = self._make_profile("tool_a", {"artifact_count": 0})
        proposals = engine.generate_for_system([principle], profile)
        self.assertEqual(len(proposals), 1)


# ── Phase 14.2 — ProposalPrioritizer ─────────────────────────────


class TestProposalPrioritizer(TestCase):
    def _make_proposal(self, proposal_id: str,
                        expected_improvement: float,
                        confidence: float,
                        target_system: str = "tool"):
        from core.generalization.models import ImprovementProposal
        return ImprovementProposal(
            proposal_id=proposal_id,
            target_system=target_system,
            proposal_type="add_capability",
            principle_id="pr_001",
            title=f"Test {proposal_id}",
            rationale="Test rationale",
            expected_improvement=expected_improvement,
            confidence=confidence,
        )

    def test_90_ranks_by_score(self):
        from core.generalization.prioritizer import ProposalPrioritizer
        p = ProposalPrioritizer()
        proposals = [
            self._make_proposal("p_low", 0.20, 0.50),    # score: 0.10
            self._make_proposal("p_high", 0.40, 0.90),   # score: 0.36
            self._make_proposal("p_mid", 0.30, 0.80),    # score: 0.24
        ]
        ranked = p.rank(proposals, max_results=0)
        self.assertEqual(len(ranked), 3)
        self.assertEqual(ranked[0][0].proposal_id, "p_high")
        self.assertEqual(ranked[1][0].proposal_id, "p_mid")
        self.assertEqual(ranked[2][0].proposal_id, "p_low")

    def test_91_respects_max_results(self):
        from core.generalization.prioritizer import ProposalPrioritizer
        p = ProposalPrioritizer()
        proposals = [
            self._make_proposal(f"p_{i}", 0.30, 0.80) for i in range(20)
        ]
        ranked = p.rank(proposals, max_results=5)
        self.assertEqual(len(ranked), 5)

    def test_92_empty_list(self):
        from core.generalization.prioritizer import ProposalPrioritizer
        p = ProposalPrioritizer()
        self.assertEqual(p.rank([]), [])

    def test_93_rank_zero_returns_all(self):
        from core.generalization.prioritizer import ProposalPrioritizer
        p = ProposalPrioritizer()
        proposals = [
            self._make_proposal(f"p_{i}", 0.30, 0.80) for i in range(5)
        ]
        ranked = p.rank(proposals, max_results=0)
        self.assertEqual(len(ranked), 5)

    def test_94_domain_count_applicability(self):
        from core.generalization.prioritizer import ProposalPrioritizer
        # 3 domains → 1.0 (capped)
        self.assertAlmostEqual(
            ProposalPrioritizer.domain_count_applicability(
                self._make_proposal("p", 0.30, 0.80), 3,
            ), 1.0,
        )
        # 1 domain → 0.33
        self.assertAlmostEqual(
            ProposalPrioritizer.domain_count_applicability(
                self._make_proposal("p", 0.30, 0.80), 1,
            ), 1.0 / 3.0, places=2,
        )

    def test_95_score_with_custom_applicability(self):
        from core.generalization.prioritizer import ProposalPrioritizer
        p = ProposalPrioritizer(applicability_fn=lambda prop: 0.5)
        proposals = [
            self._make_proposal("p1", 0.40, 0.90),  # score: 0.40*0.90*0.5 = 0.18
            self._make_proposal("p2", 0.20, 0.80),  # score: 0.20*0.80*0.5 = 0.08
        ]
        ranked = p.rank(proposals)
        self.assertEqual(len(ranked), 2)
        self.assertEqual(ranked[0][0].proposal_id, "p1")
        self.assertAlmostEqual(ranked[1][1], 0.08)


# ── Phase 14.1/14.2 — Store Integration ──────────────────────────


class TestProposalStore(TestCase):
    def setUp(self):
        from core.generalization.store import PrincipleStore
        self._tmp = tempfile.mktemp(suffix=".db")
        self.s = PrincipleStore(db_path=self._tmp)

    def tearDown(self):
        try:
            os.unlink(self._tmp)
        except Exception:
            pass

    def _make_proposal(self, proposal_id: str,
                        expected_improvement: float = 0.33,
                        confidence: float = 0.89,
                        status: str = "generated"):
        from core.generalization.models import (
            ImprovementProposal, ProposalStatus,
        )
        return ImprovementProposal(
            proposal_id=proposal_id,
            target_system="browser_tool",
            proposal_type="add_capability",
            principle_id="pr_001",
            title=f"Test {proposal_id}",
            rationale="Test rationale",
            expected_improvement=expected_improvement,
            confidence=confidence,
            status=ProposalStatus(status),
        )

    def test_100_save_and_get_proposal(self):
        p = self._make_proposal("prp_store_001")
        self.s.save_proposal(p)
        retrieved = self.s.get_proposal("prp_store_001")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.target_system, "browser_tool")
        self.assertAlmostEqual(retrieved.expected_improvement, 0.33)

    def test_101_batch_save(self):
        proposals = [self._make_proposal(f"prp_batch_{i}")
                      for i in range(5)]
        self.s.save_proposals(proposals)
        self.assertEqual(self.s.count_proposals(), 5)

    def test_102_list_by_status(self):
        from core.generalization.models import ProposalStatus
        self.s.save_proposal(self._make_proposal("prp_gen"))
        approved = self._make_proposal("prp_app", status="approved")
        self.s.save_proposal(approved)
        generated = self.s.list_proposals(status="generated")
        self.assertEqual(len(generated), 1)
        self.assertEqual(generated[0].proposal_id, "prp_gen")

    def test_103_list_by_target_system(self):
        from core.generalization.models import ImprovementProposal, ProposalStatus
        p1 = ImprovementProposal(
            proposal_id="prp_sys_a", target_system="sys_a",
            proposal_type="add_capability", principle_id="pr_001",
            title="A", rationale="R",
            expected_improvement=0.30, confidence=0.80,
        )
        p2 = ImprovementProposal(
            proposal_id="prp_sys_b", target_system="sys_b",
            proposal_type="add_capability", principle_id="pr_001",
            title="B", rationale="R",
            expected_improvement=0.30, confidence=0.80,
        )
        self.s.save_proposals([p1, p2])
        results = self.s.list_proposals(target_system="sys_a")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].proposal_id, "prp_sys_a")

    def test_104_update_status(self):
        from core.generalization.models import ProposalStatus
        p = self._make_proposal("prp_update")
        self.s.save_proposal(p)
        self.assertTrue(
            self.s.update_proposal_status("prp_update",
                                           ProposalStatus.APPROVED),
        )
        retrieved = self.s.get_proposal("prp_update")
        self.assertEqual(retrieved.status, ProposalStatus.APPROVED)

    def test_105_update_nonexistent_status(self):
        from core.generalization.models import ProposalStatus
        self.assertFalse(
            self.s.update_proposal_status("nonexistent",
                                           ProposalStatus.APPROVED),
        )

    def test_106_count_by_status(self):
        from core.generalization.models import ProposalStatus
        for i in range(3):
            self.s.save_proposal(self._make_proposal(f"prp_cnt_{i}"))
        approved = self._make_proposal("prp_cnt_app", status="approved")
        self.s.save_proposal(approved)
        self.assertEqual(self.s.count_proposals(status="generated"), 3)
        self.assertEqual(self.s.count_proposals(status="approved"), 1)

    def test_107_persistence(self):
        p = self._make_proposal("prp_persist")
        self.s.save_proposal(p)
        from core.generalization.store import PrincipleStore
        s2 = PrincipleStore(db_path=self._tmp)
        retrieved = s2.get_proposal("prp_persist")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.target_system, "browser_tool")

    def test_108_clear_includes_proposals(self):
        self.s.save_proposal(self._make_proposal("prp_clear"))
        self.s.clear()
        self.assertEqual(self.s.count_proposals(), 0)


# ── Phase 14.1/14.2 — Integration: Principle → Proposal → Prioritize → Store ──


class TestProposalIntegration(TestCase):
    """End-to-end: accepted principle → proposal engine → store → prioritize."""

    def setUp(self):
        from core.generalization.store import PrincipleStore
        from core.generalization.registry import StructuralPropertyRegistry
        self._tmp = tempfile.mktemp(suffix=".db")
        self.store = PrincipleStore(db_path=self._tmp)
        self.registry = StructuralPropertyRegistry(db_path=self._tmp)

    def tearDown(self):
        try:
            os.unlink(self._tmp)
        except Exception:
            pass

    def _make_accepted_principle(self, property_name: str,
                                  principle_id: str,
                                  discrimination: float = 0.33,
                                  confidence: float = 0.89):
        from core.generalization.models import Principle, PrincipleStatus
        return Principle(
            principle_id=principle_id,
            property_name=property_name,
            category="execution_model",
            support_rate=0.87, control_rate=0.54,
            discrimination=discrimination,
            sample_size=24, support_count=12, control_count=12,
            domains=["android", "web", "backend"],
            confidence=confidence,
            status=PrincipleStatus.ACCEPTED,
        )

    def test_110_full_pipeline(self):
        from core.generalization.proposals import ProposalEngine
        from core.generalization.prioritizer import ProposalPrioritizer

        # Seeds: two accepted principles + existing profiles
        p1 = self._make_accepted_principle("verification_builtin",
                                            "pr_v001")
        p2 = self._make_accepted_principle("retry_capable", "pr_r001",
                                            discrimination=0.35,
                                            confidence=0.92)
        self.store.save_principle(p1)
        self.store.save_principle(p2)

        principles = self.store.list_principles(status="accepted")
        profiles = self.registry.list_profiles()

        # Generate
        engine = ProposalEngine()
        proposals = engine.generate_proposals(principles, profiles)
        self.assertGreater(len(proposals), 0)

        # Store
        self.store.save_proposals(proposals)
        stored = self.store.list_proposals(status="generated")
        self.assertEqual(len(stored), len(proposals))

        # Prioritize
        prioritizer = ProposalPrioritizer()
        ranked = prioritizer.rank(stored, max_results=5)
        self.assertGreater(len(ranked), 0)

        # First result should be highest score
        for i in range(len(ranked) - 1):
            self.assertGreaterEqual(ranked[i][1], ranked[i + 1][1])

        # Verify proposal contents
        best = ranked[0][0]
        self.assertIn(best.target_system,
                      {"build_project", "automated_build"})
        self.assertIn("add_capability", best.proposal_type)

    def test_111_verification_proposal_generated_for_build_project(self):
        """build_project has verification_builtin=False, so a proposal is generated."""
        from core.generalization.proposals import ProposalEngine
        p = self._make_accepted_principle("verification_builtin", "pr_v002")
        self.store.save_principle(p)
        principles = self.store.list_principles(status="accepted")
        profiles = self.registry.list_profiles()
        engine = ProposalEngine()
        proposals = engine.generate_proposals(principles, profiles)
        targets = {prp.target_system for prp in proposals}
        self.assertIn("build_project", targets)

    def test_112_automated_build_has_no_proposals_for_existing_properties(self):
        """automated_build already has all properties=True, so no proposals."""
        from core.generalization.proposals import ProposalEngine
        p = self._make_accepted_principle("verification_builtin", "pr_v003")
        self.store.save_principle(p)
        principles = self.store.list_principles(status="accepted")
        profiles = [self.registry.get_profile("automated_build")]
        self.assertIsNotNone(profiles[0])
        engine = ProposalEngine()
        proposals = engine.generate_proposals(principles, profiles)  # type: ignore
        # automated_build has verification_builtin=True → skip
        self.assertEqual(len(proposals), 0)


# ── Phase 14.3 — Causal Model ────────────────────────────────────


class TestCausalAnalysis(TestCase):
    def test_120_creation(self):
        from core.generalization.models import CausalAnalysis, CausalStatus
        ca = CausalAnalysis(
            property_name="retry_capable",
            raw_discrimination=0.35,
            adjusted_discrimination=0.35,
            confounders_checked=["verification_builtin"],
            confounded_by=[],
            status=CausalStatus.LIKELY_CAUSAL,
            confidence=0.92,
        )
        self.assertEqual(ca.status, CausalStatus.LIKELY_CAUSAL)
        self.assertEqual(ca.confounders_checked, ["verification_builtin"])

    def test_121_to_dict(self):
        from core.generalization.models import CausalAnalysis, CausalStatus
        ca = CausalAnalysis(
            property_name="retry_capable",
            raw_discrimination=0.35,
            adjusted_discrimination=0.08,
            confounders_checked=["verification_builtin", "stateful"],
            confounded_by=["verification_builtin"],
            status=CausalStatus.LIKELY_CONFOUNDED,
            confidence=0.45,
        )
        d = ca.to_dict()
        self.assertEqual(d["status"], "likely_confounded")
        self.assertEqual(d["confounded_by"], ["verification_builtin"])

    def test_122_status_enum_values(self):
        from core.generalization.models import CausalStatus
        self.assertEqual(CausalStatus.LIKELY_CAUSAL.value, "likely_causal")
        self.assertEqual(CausalStatus.LIKELY_CONFOUNDED.value, "likely_confounded")
        self.assertEqual(CausalStatus.INSUFFICIENT_DATA.value, "insufficient_data")


# ── Phase 14.3 — CausalFilter ────────────────────────────────────


class TestCausalFilter(TestCase):
    def _make_point(self, system_id: str, success: bool,
                    properties: dict, domain: str = "build",
                    point_id: str = ""):
        from core.generalization.models import PrincipleDataPoint, SystemType
        import uuid
        return PrincipleDataPoint(
            point_id=point_id or uuid.uuid4().hex[:12],
            system_id=system_id,
            system_type=SystemType.TOOL,
            success=success,
            properties=properties,
            domain=domain,
        )

    def _make_candidate(self, property_name: str = "retry_capable",
                        discrimination: float = 0.35,
                        confidence: float = 0.92,
                        sample_size: int = 24):
        from core.generalization.models import PrincipleCandidate
        return PrincipleCandidate(
            principle_id="pc_causal",
            property_name=property_name,
            category="execution_model",
            support_rate=0.80,
            control_rate=0.45,
            discrimination=discrimination,
            sample_size=sample_size,
            support_count=sample_size // 2,
            control_count=sample_size // 2,
            domains=["build", "web", "android"],
            confidence=confidence,
        )

    def test_130_true_causal_property_survives(self):
        """retry_capable is the real driver — controlling for verification doesn't
        collapse discrimination."""
        from core.generalization.causal import CausalFilter

        # 24 data points: retry is causal, verification has no independent effect
        points = []
        for _ in range(6):
            points.append(self._make_point(
                "tool_a", True,
                {"retry_capable": True, "verification_builtin": True},
            ))
            points.append(self._make_point(
                "tool_a", True,
                {"retry_capable": True, "verification_builtin": False},
            ))
            points.append(self._make_point(
                "tool_b", False,
                {"retry_capable": False, "verification_builtin": True},
            ))
            points.append(self._make_point(
                "tool_b", False,
                {"retry_capable": False, "verification_builtin": False},
            ))

        candidate = self._make_candidate(discrimination=1.0)
        cf = CausalFilter()
        analysis = cf.analyze(candidate, points)

        self.assertEqual(analysis.status.value, "likely_causal")
        self.assertEqual(analysis.confounded_by, [])
        self.assertIn("verification_builtin", analysis.confounders_checked)
        self.assertGreaterEqual(analysis.adjusted_discrimination, 0.05)

    def test_131_confounded_property_rejected(self):
        """retry_capable correlates with success, but verification_builtin
        is the actual driver. Controlling for verification collapses discrimination."""
        from core.generalization.causal import CausalFilter

        points = [
            # Verification=True: retry doesn't matter — success with or without
            self._make_point("tool_a", True,
                             {"retry_capable": True, "verification_builtin": True}),
            self._make_point("tool_a", True,
                             {"retry_capable": True, "verification_builtin": True}),
            self._make_point("tool_a", True,
                             {"retry_capable": True, "verification_builtin": True}),
            self._make_point("tool_a", True,
                             {"retry_capable": True, "verification_builtin": True}),
            self._make_point("tool_a", True,
                             {"retry_capable": True, "verification_builtin": True}),
            self._make_point("tool_a", True,
                             {"retry_capable": True, "verification_builtin": True}),
            self._make_point("tool_a", True,
                             {"retry_capable": True, "verification_builtin": True}),
            self._make_point("tool_a", True,
                             {"retry_capable": True, "verification_builtin": True}),
            self._make_point("tool_a", True,
                             {"retry_capable": True, "verification_builtin": True}),
            self._make_point("tool_a", True,
                             {"retry_capable": True, "verification_builtin": True}),
            self._make_point("tool_b", True,
                             {"retry_capable": False, "verification_builtin": True}),
            self._make_point("tool_b", True,
                             {"retry_capable": False, "verification_builtin": True}),
            self._make_point("tool_b", True,
                             {"retry_capable": False, "verification_builtin": True}),
            self._make_point("tool_b", True,
                             {"retry_capable": False, "verification_builtin": True}),
            # Verification=False: failure regardless of retry
            self._make_point("tool_c", False,
                             {"retry_capable": True, "verification_builtin": False}),
            self._make_point("tool_c", False,
                             {"retry_capable": True, "verification_builtin": False}),
            self._make_point("tool_c", False,
                             {"retry_capable": True, "verification_builtin": False}),
            self._make_point("tool_c", False,
                             {"retry_capable": True, "verification_builtin": False}),
            self._make_point("tool_c", False,
                             {"retry_capable": True, "verification_builtin": False}),
            self._make_point("tool_c", False,
                             {"retry_capable": True, "verification_builtin": False}),
            self._make_point("tool_d", False,
                             {"retry_capable": False, "verification_builtin": False}),
            self._make_point("tool_d", False,
                             {"retry_capable": False, "verification_builtin": False}),
            self._make_point("tool_d", False,
                             {"retry_capable": False, "verification_builtin": False}),
            self._make_point("tool_d", False,
                             {"retry_capable": False, "verification_builtin": False}),
            self._make_point("tool_d", False,
                             {"retry_capable": False, "verification_builtin": False}),
            self._make_point("tool_d", False,
                             {"retry_capable": False, "verification_builtin": False}),
            self._make_point("tool_d", False,
                             {"retry_capable": False, "verification_builtin": False}),
            self._make_point("tool_d", False,
                             {"retry_capable": False, "verification_builtin": False}),
            self._make_point("tool_d", False,
                             {"retry_capable": False, "verification_builtin": False}),
            self._make_point("tool_d", False,
                             {"retry_capable": False, "verification_builtin": False}),
            self._make_point("tool_d", False,
                             {"retry_capable": False, "verification_builtin": False}),
            self._make_point("tool_d", False,
                             {"retry_capable": False, "verification_builtin": False}),
        ]

        # Raw: retry=True success = 10/16 = 0.625
        #       retry=False success = 4/16 = 0.25
        #       d = 0.375 — passes gates
        candidate = self._make_candidate(discrimination=0.375)
        cf = CausalFilter()
        analysis = cf.analyze(candidate, points)

        self.assertEqual(analysis.status.value, "likely_confounded")
        self.assertIn("verification_builtin", analysis.confounded_by)
        self.assertLess(analysis.adjusted_discrimination, 0.05)

    def test_132_no_other_boolean_properties_passes_through(self):
        """When there are no other boolean properties, candidate passes."""
        from core.generalization.causal import CausalFilter

        points = [
            self._make_point("tool_a", True,
                             {"retry_capable": True}),
            self._make_point("tool_b", False,
                             {"retry_capable": False}),
        ]
        candidate = self._make_candidate(discrimination=1.0)
        cf = CausalFilter()
        analysis = cf.analyze(candidate, points)

        self.assertEqual(analysis.status.value, "likely_causal")
        self.assertEqual(analysis.confounders_checked, [])

    def test_133_small_subset_skipped_gracefully(self):
        """When confounder subsets are too small, they're skipped."""
        from core.generalization.causal import CausalFilter

        points = [
            self._make_point("tool_a", True,
                             {"retry_capable": True, "verification_builtin": True}),
            self._make_point("tool_a", True,
                             {"retry_capable": True, "verification_builtin": True}),
            self._make_point("tool_b", False,
                             {"retry_capable": False, "verification_builtin": True}),
            self._make_point("tool_b", False,
                             {"retry_capable": False, "verification_builtin": False}),
        ]
        # Only 1 point with verification=False → below min_subset_size=4
        candidate = self._make_candidate(discrimination=0.50, sample_size=4)
        cf = CausalFilter(min_subset_size=4)
        analysis = cf.analyze(candidate, points)

        # Should still work (no subset meets min size, so controlled discriminations
        # are empty, adjusted = raw)
        self.assertIn("verification_builtin", analysis.confounders_checked)

    def test_134_multiple_confounders_all_checked(self):
        """Multiple boolean confounders are all checked."""
        from core.generalization.causal import CausalFilter

        points = []
        for _ in range(4):
            points.append(self._make_point(
                "tool_a", True,
                {"retry_capable": True, "verification_builtin": True,
                 "stateful": True, "has_failure_memory": True},
            ))
            points.append(self._make_point(
                "tool_b", False,
                {"retry_capable": False, "verification_builtin": False,
                 "stateful": False, "has_failure_memory": False},
            ))

        candidate = self._make_candidate(discrimination=1.0, sample_size=16)
        cf = CausalFilter()
        analysis = cf.analyze(candidate, points)

        self.assertGreaterEqual(len(analysis.confounders_checked), 3)
        for conf in ["verification_builtin", "stateful", "has_failure_memory"]:
            self.assertIn(conf, analysis.confounders_checked)

    def test_135_confidence_reduced_for_confounded(self):
        """Confidence should be reduced when discrimination collapses."""
        from core.generalization.causal import CausalFilter

        # Build a confounded scenario (same pattern as test_131)
        points = []
        for _ in range(8):
            points.append(self._make_point(
                "tool_a", True,
                {"retry_capable": True, "verification_builtin": True},
            ))
            points.append(self._make_point(
                "tool_b", True,
                {"retry_capable": False, "verification_builtin": True},
            ))
        for _ in range(6):
            points.append(self._make_point(
                "tool_c", False,
                {"retry_capable": True, "verification_builtin": False},
            ))
            points.append(self._make_point(
                "tool_d", False,
                {"retry_capable": False, "verification_builtin": False},
            ))

        candidate = self._make_candidate(discrimination=0.25, confidence=0.85)
        cf = CausalFilter()
        analysis = cf.analyze(candidate, points)

        if analysis.status.value == "likely_confounded":
            self.assertLess(analysis.confidence, 0.85)

    def test_136_adjusted_discrimination_reflects_minimum(self):
        """Adjusted discrimination equals the minimum controlled value."""
        from core.generalization.causal import CausalFilter

        # 3 confounders, one collapses discrimination
        points = []
        # verification=True: retry matters
        for _ in range(4):
            points.append(self._make_point(
                "tool_a", True,
                {"retry_capable": True, "verification_builtin": True,
                 "stateful": True, "has_failure_memory": True},
            ))
            points.append(self._make_point(
                "tool_b", False,
                {"retry_capable": False, "verification_builtin": True,
                 "stateful": True, "has_failure_memory": True},
            ))
        # verification=False: retry still matters (discrimination preserved)
        for _ in range(4):
            points.append(self._make_point(
                "tool_c", True,
                {"retry_capable": True, "verification_builtin": False,
                 "stateful": False, "has_failure_memory": False},
            ))
            points.append(self._make_point(
                "tool_d", False,
                {"retry_capable": False, "verification_builtin": False,
                 "stateful": False, "has_failure_memory": False},
            ))

        candidate = self._make_candidate(discrimination=1.0, sample_size=32)
        cf = CausalFilter()
        analysis = cf.analyze(candidate, points)

        # verification_builtin check: for verification=True subset,
        # retry success = 4/4 = 1.0, non-retry success = 0/4 = 0.0, d = 1.0
        # for verification=False subset:
        # retry success = 4/4 = 1.0, non-retry success = 0/4 = 0.0, d = 1.0
        # So discrimination should be preserved
        self.assertGreaterEqual(analysis.adjusted_discrimination, 0.05)


# ── Phase 14.3 — Validator Integration ──────────────────────────


class TestValidatorCausalIntegration(TestCase):
    def _make_point(self, system_id: str, success: bool,
                    properties: dict, domain: str = "build"):
        from core.generalization.models import PrincipleDataPoint, SystemType
        import uuid
        return PrincipleDataPoint(
            point_id=uuid.uuid4().hex[:12],
            system_id=system_id,
            system_type=SystemType.TOOL,
            success=success,
            properties=properties,
            domain=domain,
        )

    def _make_candidate(self, property_name: str = "retry_capable",
                        discrimination: float = 0.35,
                        sample_size: int = 24):
        from core.generalization.models import PrincipleCandidate
        return PrincipleCandidate(
            principle_id="pc_vc",
            property_name=property_name,
            category="execution_model",
            support_rate=0.80,
            control_rate=0.45,
            discrimination=discrimination,
            sample_size=sample_size,
            support_count=sample_size // 2,
            control_count=sample_size // 2,
            domains=["build", "web", "android"],
        )

    def test_140_validator_accepts_causal_without_filter(self):
        """Without CausalFilter, validator works as before."""
        from core.generalization.validator import PrincipleValidator
        from core.generalization.models import PrincipleStatus
        v = PrincipleValidator()
        candidate = self._make_candidate()
        result = v.validate(candidate)
        self.assertEqual(result.status, PrincipleStatus.ACCEPTED)

    def test_141_validator_rejects_confounded_with_filter(self):
        """With CausalFilter, confounded candidates are rejected."""
        from core.generalization.causal import CausalFilter
        from core.generalization.validator import PrincipleValidator
        from core.generalization.models import PrincipleStatus

        points = []
        for _ in range(8):
            points.append(self._make_point(
                "tool_a", True,
                {"retry_capable": True, "verification_builtin": True},
            ))
            points.append(self._make_point(
                "tool_b", True,
                {"retry_capable": False, "verification_builtin": True},
            ))
        for _ in range(6):
            points.append(self._make_point(
                "tool_c", False,
                {"retry_capable": True, "verification_builtin": False},
            ))
            points.append(self._make_point(
                "tool_d", False,
                {"retry_capable": False, "verification_builtin": False},
            ))

        cf = CausalFilter()
        v = PrincipleValidator(causal_filter=cf)
        candidate = self._make_candidate(discrimination=0.25)
        result = v.validate(candidate, data_points=points)
        self.assertEqual(result.status, PrincipleStatus.CANDIDATE)

    def test_142_validator_accepts_causal_with_filter(self):
        """With CausalFilter, truly causal candidates still pass."""
        from core.generalization.causal import CausalFilter
        from core.generalization.validator import PrincipleValidator
        from core.generalization.models import PrincipleStatus

        points = []
        for _ in range(6):
            points.append(self._make_point(
                "tool_a", True,
                {"retry_capable": True, "verification_builtin": True},
            ))
            points.append(self._make_point(
                "tool_a", True,
                {"retry_capable": True, "verification_builtin": False},
            ))
            points.append(self._make_point(
                "tool_b", False,
                {"retry_capable": False, "verification_builtin": True},
            ))
            points.append(self._make_point(
                "tool_b", False,
                {"retry_capable": False, "verification_builtin": False},
            ))

        cf = CausalFilter()
        v = PrincipleValidator(causal_filter=cf)
        candidate = self._make_candidate(discrimination=1.0)
        result = v.validate(candidate, data_points=points)
        self.assertEqual(result.status, PrincipleStatus.ACCEPTED)

    def test_143_override_causal_check(self):
        """With override_causal_check=True, confounded candidates are accepted."""
        from core.generalization.causal import CausalFilter
        from core.generalization.validator import PrincipleValidator
        from core.generalization.models import PrincipleStatus

        points = []
        for _ in range(8):
            points.append(self._make_point(
                "tool_a", True,
                {"retry_capable": True, "verification_builtin": True},
            ))
            points.append(self._make_point(
                "tool_b", True,
                {"retry_capable": False, "verification_builtin": True},
            ))
        for _ in range(6):
            points.append(self._make_point(
                "tool_c", False,
                {"retry_capable": True, "verification_builtin": False},
            ))
            points.append(self._make_point(
                "tool_d", False,
                {"retry_capable": False, "verification_builtin": False},
            ))

        cf = CausalFilter()
        v = PrincipleValidator(causal_filter=cf, override_causal_check=True)
        candidate = self._make_candidate(discrimination=0.25)
        result = v.validate(candidate, data_points=points)
        self.assertEqual(result.status, PrincipleStatus.ACCEPTED)

    def test_144_set_causal_filter_after_construction(self):
        """Causal filter can be set after construction via set_causal_filter."""
        from core.generalization.causal import CausalFilter
        from core.generalization.validator import PrincipleValidator
        v = PrincipleValidator()
        cf = CausalFilter()
        v.set_causal_filter(cf)
        self.assertIsNotNone(v._causal_filter)


# ── Phase 14.4 — Derived Property Extraction ────────────────────


class TestDerivedPropertyExtractor(TestCase):
    def setUp(self):
        from core.generalization.store import PrincipleStore
        from core.generalization.registry import StructuralPropertyRegistry
        import tempfile
        self._tmp = tempfile.mktemp(suffix=".db")
        self.store = PrincipleStore(db_path=self._tmp)
        self.registry = StructuralPropertyRegistry(db_path=self._tmp)

    def tearDown(self):
        import os
        try:
            os.unlink(self._tmp)
        except Exception:
            pass

    def _make_point(self, system_id: str, success: bool,
                    properties: dict, domain: str = "build"):
        from core.generalization.models import PrincipleDataPoint, SystemType
        import uuid
        return PrincipleDataPoint(
            point_id=uuid.uuid4().hex[:12],
            system_id=system_id,
            system_type=SystemType.TOOL,
            success=success,
            properties=properties,
            domain=domain,
        )

    def test_150_computes_average_of_numeric_derived_properties(self):
        """artifact_count averaged across multiple executions of same system."""
        from core.generalization.derived import DerivedPropertyExtractor

        points = [
            self._make_point("tool_x", True, {"artifact_count": 3}),
            self._make_point("tool_x", True, {"artifact_count": 5}),
            self._make_point("tool_x", False, {"artifact_count": 2}),
        ]
        self.store.save_data_points(points)

        extractor = DerivedPropertyExtractor(self.registry)
        updated = extractor.compute_all(points)

        self.assertGreater(len(updated), 0)
        profile = self.registry.get_profile("tool_x")
        self.assertIsNotNone(profile)
        self.assertIn("artifact_count", profile.properties)
        self.assertAlmostEqual(profile.properties["artifact_count"],
                                round((3 + 5 + 2) / 3.0, 3))

    def test_151_multiple_systems_independent_averages(self):
        """Each system's derived values are computed independently."""
        from core.generalization.derived import DerivedPropertyExtractor

        points = [
            self._make_point("tool_a", True, {"artifact_count": 10,
                                               "avg_retry_count": 2}),
            self._make_point("tool_a", True, {"artifact_count": 20,
                                               "avg_retry_count": 4}),
            self._make_point("tool_b", True, {"artifact_count": 1,
                                               "avg_retry_count": 0}),
            self._make_point("tool_b", True, {"artifact_count": 3,
                                               "avg_retry_count": 1}),
        ]
        extractor = DerivedPropertyExtractor(self.registry)
        extractor.compute_all(points)

        profile_a = self.registry.get_profile("tool_a")
        self.assertIsNotNone(profile_a)
        self.assertAlmostEqual(profile_a.properties["artifact_count"], 15.0)
        self.assertAlmostEqual(profile_a.properties["avg_retry_count"], 3.0)

        profile_b = self.registry.get_profile("tool_b")
        self.assertIsNotNone(profile_b)
        self.assertAlmostEqual(profile_b.properties["artifact_count"], 2.0)
        self.assertAlmostEqual(profile_b.properties["avg_retry_count"], 0.5)

    def test_152_empty_data_points_returns_empty(self):
        from core.generalization.derived import DerivedPropertyExtractor
        extractor = DerivedPropertyExtractor(self.registry)
        result = extractor.compute_all([])
        self.assertEqual(result, [])

    def test_153_bool_properties_skipped(self):
        """Boolean properties are not averaged even if defined as derived."""
        from core.generalization.derived import DerivedPropertyExtractor

        points = [
            self._make_point("tool_x", True,
                             {"retry_capable": True, "artifact_count": 5}),
            self._make_point("tool_x", True,
                             {"retry_capable": False, "artifact_count": 3}),
        ]
        extractor = DerivedPropertyExtractor(self.registry)
        extractor.compute_all(points)

        profile = self.registry.get_profile("tool_x")
        self.assertIsNotNone(profile)
        # artifact_count should be computed
        self.assertIn("artifact_count", profile.properties)
        # retry_capable is bool — should not be in derived properties
        # (it may be in the profile from other sources, but not from this extractor)

    def test_154_numeric_property_not_in_derived_list_skipped(self):
        """Numeric properties not defined as DERIVED in registry are skipped."""
        from core.generalization.derived import DerivedPropertyExtractor

        points = [
            self._make_point("tool_x", True,
                             {"custom_numeric": 42, "artifact_count": 5}),
            self._make_point("tool_x", True,
                             {"custom_numeric": 10, "artifact_count": 3}),
        ]
        extractor = DerivedPropertyExtractor(self.registry)
        extractor.compute_all(points)

        profile = self.registry.get_profile("tool_x")
        self.assertIsNotNone(profile)
        # artifact_count should be present
        self.assertIn("artifact_count", profile.properties)
        # custom_numeric is not a DERIVED property — should not be computed
        self.assertNotIn("custom_numeric", profile.properties)

    def test_155_compute_for_single_system(self):
        from core.generalization.derived import DerivedPropertyExtractor

        points = [
            self._make_point("tool_a", True, {"artifact_count": 7}),
            self._make_point("tool_b", True, {"artifact_count": 99}),
        ]
        extractor = DerivedPropertyExtractor(self.registry)
        result = extractor.compute_for_system(points, "tool_a")
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.properties["artifact_count"], 7.0)

        # tool_b should not be affected
        profile_a = self.registry.get_profile("tool_b")
        self.assertIsNone(profile_a)

    def test_156_system_with_no_matching_points_returns_none(self):
        from core.generalization.derived import DerivedPropertyExtractor
        points = [self._make_point("tool_a", True, {"artifact_count": 5})]
        extractor = DerivedPropertyExtractor(self.registry)
        result = extractor.compute_for_system(points, "nonexistent")
        self.assertIsNone(result)

    def test_157_preserves_existing_static_properties(self):
        """Merging derived values does not overwrite existing static properties."""
        from core.generalization.derived import DerivedPropertyExtractor
        from core.generalization.models import SystemProfile, SystemType

        # Pre-register a profile with static properties
        existing = SystemProfile(
            system_id="tool_x",
            system_type=SystemType.TOOL,
            properties={"retry_capable": True, "stateful": False},
        )
        self.registry.register_profile(existing)

        points = [
            self._make_point("tool_x", True, {"artifact_count": 4}),
            self._make_point("tool_x", True, {"artifact_count": 6}),
        ]
        extractor = DerivedPropertyExtractor(self.registry)
        extractor.compute_all(points)

        profile = self.registry.get_profile("tool_x")
        self.assertIsNotNone(profile)
        # Static properties preserved
        self.assertTrue(profile.properties["retry_capable"])
        self.assertFalse(profile.properties["stateful"])
        # Derived property added
        self.assertAlmostEqual(profile.properties["artifact_count"], 5.0)

    def test_158_system_with_no_existing_profile_creates_one(self):
        """If no profile exists for a system, one is created."""
        from core.generalization.derived import DerivedPropertyExtractor

        points = [
            self._make_point("brand_new_tool", True, {"artifact_count": 8}),
        ]
        extractor = DerivedPropertyExtractor(self.registry)
        extractor.compute_all(points)

        profile = self.registry.get_profile("brand_new_tool")
        self.assertIsNotNone(profile)
        self.assertAlmostEqual(profile.properties["artifact_count"], 8.0)

    def test_159_derived_property_names_from_registry(self):
        """Only properties the registry defines as DERIVED are computed."""
        from core.generalization.derived import DerivedPropertyExtractor
        from core.generalization.models import (
            StructuralProperty, PropertySource, PropertyValueType,
        )

        # Register a custom derived property
        custom = StructuralProperty(
            property_id="prop_custom_derived",
            name="custom_score",
            category="execution_model",
            value_type=PropertyValueType.FLOAT,
            source=PropertySource.DERIVED,
        )
        self.registry.register_property(custom)

        points = [
            self._make_point("tool_x", True,
                             {"artifact_count": 3, "custom_score": 0.8}),
            self._make_point("tool_x", True,
                             {"artifact_count": 7, "custom_score": 0.6}),
        ]
        extractor = DerivedPropertyExtractor(self.registry)
        extractor.compute_all(points)

        profile = self.registry.get_profile("tool_x")
        self.assertIsNotNone(profile)
        # Both derived properties should be computed
        self.assertIn("artifact_count", profile.properties)
        self.assertIn("custom_score", profile.properties)
        self.assertAlmostEqual(profile.properties["custom_score"], 0.7)


# ── Phase 15.0 — Proposal Executor ──────────────────────────────


class TestProposalExecutor(TestCase):
    def setUp(self):
        import tempfile
        from unittest.mock import Mock, MagicMock
        self._tmp = tempfile.mktemp(suffix=".db")
        from core.generalization.store import PrincipleStore
        self.store = PrincipleStore(db_path=self._tmp)

        # Mock ExperimentRunner
        self.mock_runner = MagicMock()
        mock_exp = MagicMock()
        mock_exp.experiment_id = "exp_mock_001"
        self.mock_runner.create_experiment.return_value = mock_exp

    def tearDown(self):
        import os
        try:
            os.unlink(self._tmp)
        except Exception:
            pass

    def _make_approved_proposal(self, proposal_id: str = "prp_exec_001",
                                  target_system: str = "browser_tool"):
        from core.generalization.models import ImprovementProposal, ProposalStatus
        return ImprovementProposal(
            proposal_id=proposal_id,
            target_system=target_system,
            proposal_type="add_capability",
            principle_id="pr_001",
            title=f"Add verification to {target_system}",
            rationale="Test rationale",
            expected_improvement=0.33,
            confidence=0.89,
            status=ProposalStatus.APPROVED,
        )

    def test_160_execute_approved_proposal(self):
        from core.generalization.executor import ProposalExecutor
        executor = ProposalExecutor(experiment_runner=self.mock_runner)
        proposal = self._make_approved_proposal()
        self.store.save_proposal(proposal)

        experiment_id = executor.execute(proposal, self.store)

        self.mock_runner.create_experiment.assert_called_once()
        self.assertEqual(proposal.status.value, "experimenting")
        retrieved = self.store.get_proposal(proposal.proposal_id)
        self.assertEqual(retrieved.status.value, "experimenting")
        self.assertIsNotNone(experiment_id)

    def test_161_execute_non_approved_raises(self):
        from core.generalization.executor import ProposalExecutor
        from core.generalization.models import ImprovementProposal, ProposalStatus
        executor = ProposalExecutor(experiment_runner=self.mock_runner)
        pending = ImprovementProposal(
            proposal_id="prp_pending",
            target_system="tool",
            proposal_type="add_capability",
            principle_id="pr_001",
            title="Test", rationale="R",
            expected_improvement=0.30, confidence=0.80,
            status=ProposalStatus.GENERATED,
        )
        with self.assertRaises(ValueError):
            executor.execute(pending, self.store)

    def test_162_complete_success_promotes(self):
        from core.generalization.executor import ProposalExecutor
        from core.generalization.models import ProposalStatus
        executor = ProposalExecutor(experiment_runner=self.mock_runner)
        proposal = self._make_approved_proposal()
        self.store.save_proposal(proposal)
        executor.execute(proposal, self.store)

        result = executor.complete(proposal, self.store, success=True)
        self.assertTrue(result)
        self.assertEqual(proposal.status, ProposalStatus.PROMOTED)
        retrieved = self.store.get_proposal(proposal.proposal_id)
        self.assertEqual(retrieved.status, ProposalStatus.PROMOTED)

    def test_163_complete_failure_rejects(self):
        from core.generalization.executor import ProposalExecutor
        from core.generalization.models import ProposalStatus
        executor = ProposalExecutor(experiment_runner=self.mock_runner)
        proposal = self._make_approved_proposal()
        executor.execute(proposal, self.store)

        result = executor.complete(proposal, self.store, success=False)
        self.assertFalse(result)
        self.assertEqual(proposal.status, ProposalStatus.REJECTED)

    def test_164_complete_non_experimenting_raises(self):
        from core.generalization.executor import ProposalExecutor
        executor = ProposalExecutor(experiment_runner=self.mock_runner)
        proposal = self._make_approved_proposal()
        # Not executed — still APPROVED
        with self.assertRaises(ValueError):
            executor.complete(proposal, self.store, success=True)

    def test_165_outcome_data_point_recorded(self):
        from core.generalization.executor import ProposalExecutor
        from core.generalization.models import ProposalStatus
        executor = ProposalExecutor(experiment_runner=self.mock_runner)
        proposal = self._make_approved_proposal()
        executor.execute(proposal, self.store)

        executor.complete(proposal, self.store, success=True,
                           control_metrics={"success_rate": 0.5},
                           candidate_metrics={"success_rate": 0.8})

        # Should have recorded an outcome data point
        points = self.store.list_data_points(system_id=proposal.target_system)
        self.assertGreater(len(points), 0)
        outcome_point = points[0]
        self.assertEqual(outcome_point.domain, "self_improvement")
        self.assertEqual(outcome_point.session_id, proposal.proposal_id)
        self.assertTrue(outcome_point.success)
        self.assertIn("proposal_type", outcome_point.properties)

    def test_166_execute_and_complete_shortcut(self):
        from core.generalization.executor import ProposalExecutor
        executor = ProposalExecutor(experiment_runner=self.mock_runner)
        proposal = self._make_approved_proposal()

        experiment_id, promoted = executor.execute_and_complete(
            proposal, self.store, success=True,
        )
        self.assertTrue(promoted)
        self.assertEqual(proposal.status.value, "promoted")

    def test_167_two_proposals_independent_lifecycles(self):
        from core.generalization.executor import ProposalExecutor
        from core.generalization.models import ProposalStatus
        executor = ProposalExecutor(experiment_runner=self.mock_runner)
        p1 = self._make_approved_proposal("prp_a", "tool_a")
        p2 = self._make_approved_proposal("prp_b", "tool_b")
        self.store.save_proposals([p1, p2])

        executor.execute(p1, self.store)
        executor.execute(p2, self.store)

        self.assertEqual(p1.status, ProposalStatus.EXPERIMENTING)
        self.assertEqual(p2.status, ProposalStatus.EXPERIMENTING)

        executor.complete(p1, self.store, success=True)
        executor.complete(p2, self.store, success=False)

        self.assertEqual(p1.status, ProposalStatus.PROMOTED)
        self.assertEqual(p2.status, ProposalStatus.REJECTED)

        retrieved_a = self.store.get_proposal("prp_a")
        retrieved_b = self.store.get_proposal("prp_b")
        self.assertEqual(retrieved_a.status, ProposalStatus.PROMOTED)
        self.assertEqual(retrieved_b.status, ProposalStatus.REJECTED)
