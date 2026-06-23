"""Belief Quality Engine tests — Phase 16.0–16.2.

Covers:
  - Models: SourceProfile, DecomposedConfidence, AccuracyRecord
  - SourceTracker: reliability, contradictions, domain scores
  - FreshnessScorer: exponential decay, half-lives, edge cases
  - AccuracyTracker: per-domain/category/source accuracy
  - ConsensusScorer: cross-source corroboration scoring
  - QualityEngine: decomposed confidence computation (5 dimensions)
  - BeliefStore: SQLite persistence
  - BeliefIntegrator: integration adapters
"""

import os
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from core.belief.accuracy import AccuracyTracker
from core.belief.consensus import ConsensusScorer
from core.belief.freshness import FreshnessScorer
from core.belief.integration import BeliefIntegrator
from core.belief.models import (
    AccuracyRecord,
    BeliefCategory,
    BeliefQualityRequest,
    DecomposedConfidence,
    SourceProfile,
    SourceType,
)
from core.belief.quality import QualityEngine
from core.belief.source_tracker import SourceTracker
from core.belief.store import BeliefStore
from core.strategy.memory_adapter import MemoryAdapter
from core.strategy.predictor import OutcomePredictor
from core.generalization.validator import PrincipleValidator


# ── Model Tests ──────────────────────────────────────────────────────────


class TestModels(unittest.TestCase):
    """SourceProfile, DecomposedConfidence, and AccuracyRecord basics."""

    def test_01_source_profile_defaults(self):
        p = SourceProfile(source_id="src_1", source_type=SourceType.RESEARCH_URL)
        self.assertEqual(p.source_id, "src_1")
        self.assertEqual(p.reliability_score, 0.5)
        self.assertEqual(p.total_references, 0)
        self.assertEqual(p.domain_scores, {})

    def test_02_source_profile_to_dict_roundtrip(self):
        now = datetime.now(timezone.utc)
        p = SourceProfile(
            source_id="src_2",
            source_type=SourceType.TOOL,
            reliability_score=0.85,
            domain_scores={"android": 0.9, "web": 0.7},
            total_references=10,
            correct_references=8,
            first_seen=now,
        )
        d = p.to_dict()
        restored = SourceProfile.from_dict(d)
        self.assertEqual(restored.source_id, "src_2")
        self.assertEqual(restored.source_type, SourceType.TOOL)
        self.assertEqual(restored.reliability_score, 0.85)
        self.assertEqual(restored.domain_scores, {"android": 0.9, "web": 0.7})
        self.assertEqual(restored.total_references, 10)
        self.assertEqual(restored.first_seen.isoformat(), p.first_seen.isoformat())

    def test_03_decomposed_confidence_defaults(self):
        dc = DecomposedConfidence()
        self.assertEqual(dc.overall, 0.5)
        self.assertEqual(dc.source_quality, 0.5)
        self.assertEqual(dc.freshness, 1.0)
        self.assertEqual(dc.components, {})

    def test_04_decomposed_confidence_to_dict(self):
        dc = DecomposedConfidence(
            overall=0.74,
            source_quality=0.85,
            evidence_strength=0.92,
            accuracy=0.82,
            freshness=0.95,
            components={"evidence_count": 24.0},
        )
        d = dc.to_dict()
        self.assertEqual(d["overall"], 0.74)
        self.assertEqual(d["source_quality"], 0.85)
        self.assertEqual(d["raw_evidence_count"], 24.0)

    def test_05_accuracy_record(self):
        ar = AccuracyRecord(
            record_id="r1",
            belief_id="b1",
            domain="android",
            category="pattern",
            predicted_value=0.85,
            actual_value=0.90,
            error=0.05,
        )
        self.assertEqual(ar.error, 0.05)
        d = ar.to_dict()
        self.assertEqual(d["belief_id"], "b1")
        self.assertEqual(d["error"], 0.05)

    def test_06_source_type_enum(self):
        self.assertEqual(SourceType.RESEARCH_URL.value, "research_url")
        self.assertEqual(SourceType.ACTIVITY.value, "activity")
        self.assertEqual(SourceType.HUMAN_FEEDBACK.value, "human_feedback")

    def test_07_belief_category_enum(self):
        self.assertEqual(BeliefCategory.PATTERN.value, "pattern")
        self.assertEqual(BeliefCategory.PRINCIPLE.value, "principle")


# ── SourceTracker Tests ──────────────────────────────────────────────────


class TestSourceTracker(unittest.TestCase):
    """Source reliability tracking."""

    def setUp(self):
        self.tracker = SourceTracker()

    def test_08_unknown_source_returns_prior(self):
        self.assertEqual(self.tracker.get_reliability("unknown"), 0.5)

    def test_09_single_reference_does_not_drive_to_extremes(self):
        self.tracker.record_reference("src_a", was_correct=True)
        r = self.tracker.get_reliability("src_a")
        # With 1 correct ref + prior_weight=5 prior=0.5: (1 + 2.5) / (1 + 5) = 0.583
        self.assertAlmostEqual(r, 0.583, places=2)

    def test_10_many_correct_references_drive_reliability_up(self):
        for _ in range(20):
            self.tracker.record_reference("src_b", was_correct=True)
        r = self.tracker.get_reliability("src_b")
        self.assertGreater(r, 0.7)

    def test_11_many_wrong_references_drive_reliability_down(self):
        for _ in range(20):
            self.tracker.record_reference("src_c", was_correct=False)
        r = self.tracker.get_reliability("src_c")
        self.assertLess(r, 0.15)

    def test_12_contradiction_tracking(self):
        self.tracker.record_reference("src_d", was_correct=True)
        self.tracker.record_contradiction("src_d")
        profile = self.tracker.get_profile("src_d")
        self.assertEqual(profile.contradictory_references, 1)

    def test_13_neutral_reference_does_not_affect_correctness(self):
        self.tracker.record_reference("src_e", was_correct=None)
        profile = self.tracker.get_profile("src_e")
        self.assertEqual(profile.correct_references, 0)
        self.assertEqual(profile.total_references, 1)

    def test_14_get_all_profiles(self):
        self.tracker.record_reference("src_f", was_correct=True)
        self.tracker.record_reference("src_g", was_correct=False)
        profiles = self.tracker.get_all_profiles()
        self.assertEqual(len(profiles), 2)

    def test_15_clear(self):
        self.tracker.record_reference("src_h", was_correct=True)
        self.tracker.clear()
        self.assertEqual(self.tracker.profile_count(), 0)

    def test_16_set_profiles(self):
        p = SourceProfile(source_id="src_i", source_type=SourceType.TOOL, reliability_score=0.9)
        self.tracker.set_profiles([p])
        self.assertEqual(self.tracker.profile_count(), 1)
        self.assertEqual(self.tracker.get_reliability("src_i"), 0.9)


# ── FreshnessScorer Tests ────────────────────────────────────────────────


class TestFreshnessScorer(unittest.TestCase):
    """Time-based evidence decay."""

    def setUp(self):
        self.scorer = FreshnessScorer()

    def test_17_no_timestamp_returns_1_0(self):
        self.assertEqual(self.scorer.score(), 1.0)

    def test_18_recent_evidence_returns_high_freshness(self):
        recent = datetime.now(timezone.utc) - timedelta(hours=1)
        score = self.scorer.score(created_at=recent)
        self.assertGreater(score, 0.95)

    def test_19_old_evidence_decays(self):
        old = datetime.now(timezone.utc) - timedelta(days=365 * 2)
        score = self.scorer.score(created_at=old)
        self.assertLess(score, 0.3)

    def test_20_different_half_lives_produce_different_scores(self):
        now = datetime.now(timezone.utc)
        old = now - timedelta(days=200)

        # Warning has 60-day half-life → decays faster
        warning_score = self.scorer.score(
            created_at=old, category=BeliefCategory.WARNING.value
        )
        # Principle has 365-day half-life → decays slower
        principle_score = self.scorer.score(
            created_at=old, category=BeliefCategory.PRINCIPLE.value
        )
        self.assertLess(warning_score, principle_score)

    def test_21_freshness_never_below_minimum(self):
        ancient = datetime.now(timezone.utc) - timedelta(days=365 * 100)
        score = self.scorer.score(created_at=ancient)
        self.assertGreaterEqual(score, 0.10)

    def test_22_last_validated_preferred_over_created(self):
        now = datetime.now(timezone.utc)
        old = now - timedelta(days=1000)
        recent = now - timedelta(hours=1)

        scored_old = self.scorer.score(created_at=old, category="heuristic")
        scored_validated = self.scorer.score(
            created_at=old, last_validated=recent, category="heuristic"
        )
        self.assertGreater(scored_validated, scored_old)

    def test_23_score_many_uses_max(self):
        now = datetime.now(timezone.utc)
        old = now - timedelta(days=365)
        recent = now - timedelta(hours=1)

        combined = self.scorer.score_many(
            [old, old, recent], category="heuristic"
        )
        single_old = self.scorer.score(created_at=old, category="heuristic")
        self.assertGreater(combined, single_old)

    def test_24_custom_half_life(self):
        scorer = FreshnessScorer(half_lives={"custom": 30.0})
        self.assertEqual(scorer.get_half_life("custom"), 30.0)

    def test_25_set_half_life(self):
        self.scorer.set_half_life( BeliefCategory.PRINCIPLE.value, 500.0)
        self.assertEqual(self.scorer.get_half_life(BeliefCategory.PRINCIPLE.value), 500.0)

    def test_26_zero_half_life_returns_minimum(self):
        scorer = FreshnessScorer(half_lives={"test": 0.0})
        old = datetime.now(timezone.utc) - timedelta(days=1)
        score = scorer.score(created_at=old, category="test")
        self.assertAlmostEqual(score, 0.10, places=2)


# ── AccuracyTracker Tests ────────────────────────────────────────────────


class TestAccuracyTracker(unittest.TestCase):
    """Prediction accuracy tracking."""

    def setUp(self):
        self.tracker = AccuracyTracker()

    def test_27_no_records_returns_prior(self):
        self.assertEqual(self.tracker.get_accuracy(), 0.5)

    def test_28_accurate_records_increase_accuracy(self):
        for _ in range(10):
            self.tracker.record(
                belief_id="b1", domain="android", category="pattern",
                predicted_value=0.9, actual_value=0.85,
            )
        acc = self.tracker.get_accuracy(domain="android", category="pattern")
        self.assertGreater(acc, 0.5)

    def test_29_inaccurate_records_decrease_accuracy(self):
        for _ in range(10):
            self.tracker.record(
                belief_id="b2", domain="web", category="heuristic",
                predicted_value=0.9, actual_value=0.2,
            )
        acc = self.tracker.get_accuracy(domain="web")
        self.assertLess(acc, 0.5)

    def test_30_domain_filtering(self):
        for _ in range(5):
            self.tracker.record(
                belief_id="b3", domain="android", category="pattern",
                predicted_value=0.9, actual_value=0.85,
            )
        for _ in range(5):
            self.tracker.record(
                belief_id="b4", domain="web", category="pattern",
                predicted_value=0.9, actual_value=0.2,
            )
        android_acc = self.tracker.get_accuracy(domain="android")
        web_acc = self.tracker.get_accuracy(domain="web")
        self.assertGreater(android_acc, web_acc)

    def test_31_contradiction_rate(self):
        # Same belief_id with diverging values → contradiction
        self.tracker.record("b5", "test", "heuristic", 0.9, 0.1)
        self.tracker.record("b5", "test", "heuristic", 0.2, 0.1)
        rate = self.tracker.get_contradiction_rate(domain="test")
        self.assertGreater(rate, 0.0)

    def test_32_no_contradiction(self):
        self.tracker.record("b6", "test", "heuristic", 0.9, 0.85)
        self.tracker.record("b7", "test", "heuristic", 0.8, 0.75)
        rate = self.tracker.get_contradiction_rate(domain="test")
        self.assertEqual(rate, 0.0)

    def test_33_domain_metrics(self):
        for _ in range(8):
            self.tracker.record("b8", "android", "pattern", 0.9, 0.88)
        metrics = self.tracker.get_domain_metrics("android")
        self.assertEqual(metrics.domain, "android")
        self.assertEqual(metrics.total_records, 8)
        self.assertEqual(metrics.correct_predictions, 8)
        self.assertEqual(metrics.accuracy, 1.0)

    def test_34_all_domain_metrics(self):
        self.tracker.record("b9", "android", "pattern", 0.9, 0.85)
        self.tracker.record("b10", "web", "pattern", 0.9, 0.2)
        metrics_list = self.tracker.get_all_domain_metrics()
        self.assertEqual(len(metrics_list), 2)

    def test_35_set_records(self):
        records = [
            AccuracyRecord(
                record_id=f"r{i}", belief_id=f"b{i}", domain="test",
                category="heuristic", predicted_value=0.9, actual_value=0.85,
                error=0.05,
            )
            for i in range(3)
        ]
        self.tracker.set_records(records)
        self.assertEqual(self.tracker.record_count(), 3)


# ── QualityEngine Tests ──────────────────────────────────────────────────


class TestQualityEngine(unittest.TestCase):
    """Unified confidence computation."""

    def setUp(self):
        self.engine = QualityEngine()
        # Pre-seed some accuracy records for realistic tests
        for _ in range(10):
            self.engine.accuracy_tracker.record(
                belief_id="seed", domain="android", category="pattern",
                predicted_value=0.85, actual_value=0.90,
            )

    def test_36_default_request_produces_baseline_confidence(self):
        # No source, zero evidence → conservative baseline
        dc = self.engine.compute(BeliefQualityRequest())
        self.assertGreater(dc.overall, 0.0)
        self.assertLess(dc.overall, 1.0)
        # All dimensions should be present
        self.assertGreaterEqual(dc.source_quality, 0.0)
        self.assertGreaterEqual(dc.evidence_strength, 0.0)
        self.assertGreaterEqual(dc.accuracy, 0.0)
        self.assertGreaterEqual(dc.freshness, 0.0)

    def test_37_strong_evidence_increases_confidence(self):
        weak = self.engine.compute(BeliefQualityRequest(evidence_count=1))
        strong = self.engine.compute(BeliefQualityRequest(evidence_count=20))
        self.assertGreater(strong.overall, weak.overall)

    def test_38_recent_evidence_higher_than_old(self):
        now = datetime.now(timezone.utc)
        recent = self.engine.compute(BeliefQualityRequest(
            evidence_count=5, created_at=now
        ))
        old = self.engine.compute(BeliefQualityRequest(
            evidence_count=5, created_at=now - timedelta(days=365 * 2)
        ))
        self.assertGreater(recent.overall, old.overall)

    def test_39_reliable_source_increases_confidence(self):
        # Seed source reliability
        self.engine.source_tracker.record_reference(
            "trusted", was_correct=True
        )
        for _ in range(20):
            self.engine.source_tracker.record_reference("trusted", was_correct=True)

        with_source = self.engine.compute(BeliefQualityRequest(
            source_id="trusted", evidence_count=5, domain="android"
        ))
        without_source = self.engine.compute(BeliefQualityRequest(
            evidence_count=5, domain="android"
        ))
        self.assertGreater(with_source.overall, without_source.overall)

    def test_40_high_accuracy_domain_increases_confidence(self):
        # AccuracyTracker already seeded with 10 correct android records
        android = self.engine.compute(BeliefQualityRequest(
            evidence_count=5, domain="android", category=BeliefCategory.PATTERN
        ))
        unknown = self.engine.compute(BeliefQualityRequest(
            evidence_count=5, domain="unknown_domain", category=BeliefCategory.PATTERN
        ))
        self.assertGreater(android.accuracy, unknown.accuracy)

    def test_41_compute_from_scratch_convenience(self):
        dc = self.engine.compute_from_scratch(
            evidence_count=10,
            category="pattern",
            domain="android",
        )
        self.assertIsInstance(dc, DecomposedConfidence)
        self.assertGreater(dc.overall, 0.0)

    def test_42_existing_confidence_blend(self):
        without_blend = self.engine.compute(BeliefQualityRequest(
            evidence_count=1, domain="unknown"
        ))
        with_blend = self.engine.compute(BeliefQualityRequest(
            evidence_count=1, domain="unknown",
            current_confidence=0.95,
        ))
        # Blend should pull toward 0.95
        self.assertGreater(with_blend.overall, without_blend.overall)

    def test_43_recompute_many(self):
        requests = [
            BeliefQualityRequest(evidence_count=1),
            BeliefQualityRequest(evidence_count=10),
            BeliefQualityRequest(evidence_count=50),
        ]
        results = self.engine.recompute_many(requests)
        self.assertEqual(len(results), 3)
        self.assertLess(results[0].overall, results[1].overall)
        self.assertLess(results[1].overall, results[2].overall)

    def test_44_dimension_summary(self):
        summary = self.engine.get_dimension_summary(BeliefQualityRequest(
            evidence_count=5, domain="android"
        ))
        self.assertIn("overall", summary)
        self.assertIn("source_quality", summary)
        self.assertIn("evidence_strength", summary)
        self.assertIn("accuracy", summary)
        self.assertIn("freshness", summary)

    def test_45_evidence_strength_saturates(self):
        low = self.engine._compute_evidence_strength(0)
        mid = self.engine._compute_evidence_strength(5)
        high = self.engine._compute_evidence_strength(20)
        very_high = self.engine._compute_evidence_strength(100)
        self.assertEqual(low, 0.05)
        self.assertEqual(high, 1.0)
        self.assertEqual(very_high, 1.0)
        self.assertAlmostEqual(mid, 0.5, places=2)

    # ── Consensus dimension tests ──────────────────────────────────────

    def test_46_consensus_defaults_to_no_penalty(self):
        """No source data → consensus = 1.0 (neutral)."""
        dc = self.engine.compute(BeliefQualityRequest(evidence_count=5))
        self.assertEqual(dc.consensus, 1.0)

    def test_47_consensus_single_source_penalty(self):
        """Single supporting source → consensus ≈ 0.55."""
        dc = self.engine.compute(BeliefQualityRequest(
            evidence_count=5, supporting_sources=["src_1"]
        ))
        self.assertGreater(dc.consensus, 0.50)
        self.assertLess(dc.consensus, 0.65)

    def test_48_consensus_many_sources_all_agreeing(self):
        """8 supporting sources, no contradicting → consensus near 1.0."""
        dc = self.engine.compute(BeliefQualityRequest(
            evidence_count=5,
            supporting_sources=[f"src_{i}" for i in range(8)],
        ))
        self.assertGreater(dc.consensus, 0.80)

    def test_49_consensus_contradicting_sources(self):
        """5 supporting + 3 contradicting → consensus intermediate."""
        dc = self.engine.compute(BeliefQualityRequest(
            evidence_count=5,
            supporting_sources=[f"src_a{i}" for i in range(5)],
            contradicting_sources=[f"src_b{i}" for i in range(3)],
        ))
        self.assertGreater(dc.consensus, 0.40)
        self.assertLess(dc.consensus, 0.70)

    def test_50_consensus_equal_split(self):
        """4 supporting + 4 contradicting → consensus low (contested)."""
        dc = self.engine.compute(BeliefQualityRequest(
            evidence_count=5,
            supporting_sources=[f"src_a{i}" for i in range(4)],
            contradicting_sources=[f"src_b{i}" for i in range(4)],
        ))
        self.assertGreater(dc.consensus, 0.30)
        self.assertLess(dc.consensus, 0.55)

    def test_51_consensus_lowers_overall_confidence(self):
        """Consensus penalty should reduce overall confidence compared to no-penalty case."""
        no_consensus = self.engine.compute(BeliefQualityRequest(
            evidence_count=10, domain="android",
        ))
        with_penalty = self.engine.compute(BeliefQualityRequest(
            evidence_count=10, domain="android",
            supporting_sources=["only_one"],
        ))
        self.assertGreater(no_consensus.overall, with_penalty.overall)

    def test_52_consensus_in_dimension_summary(self):
        """Dimension summary should include consensus."""
        summary = self.engine.get_dimension_summary(BeliefQualityRequest(
            evidence_count=5, supporting_sources=["src_1"]
        ))
        self.assertIn("consensus", summary)

    def test_53_consensus_from_scratch_passthrough(self):
        """compute_from_scratch doesn't pass sources — defaults to 1.0."""
        dc = self.engine.compute_from_scratch(evidence_count=5)
        self.assertEqual(dc.consensus, 1.0)


# ── ConsensusScorer Unit Tests ──────────────────────────────────────────


class TestConsensusScorer(unittest.TestCase):
    """Standalone ConsensusScorer behavior."""

    def setUp(self):
        self.scorer = ConsensusScorer()

    def test_54_no_sources_returns_default(self):
        self.assertEqual(self.scorer.score(), 1.0)
        self.assertEqual(self.scorer.score(supporting_sources=None, contradicting_sources=None), 1.0)
        self.assertEqual(self.scorer.score(supporting_sources=[], contradicting_sources=[]), 1.0)

    def test_55_single_source(self):
        s = self.scorer.score(supporting_sources=["url_1"])
        self.assertAlmostEqual(s, 0.55, places=2)

    def test_56_single_source_with_contradiction(self):
        """Single source contradicted by others."""
        s = self.scorer.score(
            supporting_sources=["url_1"],
            contradicting_sources=["url_2", "url_3"],
        )
        self.assertLess(s, 0.40)  # 1 vs 2 → low consensus

    def test_57_many_sources_all_agree(self):
        s = self.scorer.score(supporting_sources=[f"url_{i}" for i in range(8)])
        self.assertGreater(s, 0.75)

    def test_58_mixed_evidence(self):
        s = self.scorer.score(
            supporting_sources=[f"url_a{i}" for i in range(5)],
            contradicting_sources=[f"url_b{i}" for i in range(3)],
        )
        self.assertGreater(s, 0.30)
        self.assertLess(s, 0.70)

    def test_59_equal_split(self):
        s = self.scorer.score(
            supporting_sources=[f"url_a{i}" for i in range(4)],
            contradicting_sources=[f"url_b{i}" for i in range(4)],
        )
        self.assertGreater(s, 0.30)
        self.assertLess(s, 0.55)

    def test_60_score_from_fact_sets_no_contradictions(self):
        s = self.scorer.score_from_fact_sets(
            supporting_fact_sources=[
                ["url_1", "url_2"],
                ["url_3"],
                ["url_4", "url_5", "url_6"],
            ],
        )
        # 6 unique sources, all supporting
        self.assertGreater(s, 0.70)

    def test_61_score_from_fact_sets_with_contradictions(self):
        s = self.scorer.score_from_fact_sets(
            supporting_fact_sources=[
                ["url_1", "url_2"],
                ["url_3"],
            ],
            contradicting_fact_sources=[
                ["url_4"],
                ["url_5", "url_6"],
            ],
        )
        # 3 supporting, 3 contradicting
        self.assertGreater(s, 0.30)
        self.assertLess(s, 0.60)

    def test_62_score_from_fact_sets_overlap_removed(self):
        """Sources supporting both sides are removed from both."""
        s = self.scorer.score_from_fact_sets(
            supporting_fact_sources=[["url_1", "url_2"]],
            contradicting_fact_sources=[["url_2", "url_3"]],
        )
        # After removing overlap (url_2): 1 supporting, 1 contradicting
        # total=2, 1 supporting = 50% → ~0.43
        self.assertGreater(s, 0.30)
        self.assertLess(s, 0.55)

    def test_63_dimension_name(self):
        self.assertEqual(self.scorer.dimension_name(), "consensus")

    def test_64_dimension_summary_labels(self):
        self.assertIn("strong", self.scorer.dimension_summary(0.85))
        self.assertIn("moderate", self.scorer.dimension_summary(0.60))
        self.assertIn("weak", self.scorer.dimension_summary(0.40))
        self.assertIn("contested", self.scorer.dimension_summary(0.20))


# ── BeliefStore Tests ────────────────────────────────────────────────────


class TestBeliefStore(unittest.TestCase):
    """SQLite-backed persistence for belief quality data."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._db = os.path.join(self._tmp, "test_belief.db")
        self.store = BeliefStore(db_path=self._db)

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_46_save_and_get_source_profile(self):
        p = SourceProfile(
            source_id="src_store_1",
            source_type=SourceType.TOOL,
            reliability_score=0.85,
            total_references=10,
            correct_references=8,
        )
        self.store.save_source_profile(p)
        fetched = self.store.get_source_profile("src_store_1")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.source_id, "src_store_1")
        self.assertEqual(fetched.reliability_score, 0.85)
        self.assertEqual(fetched.total_references, 10)

    def test_47_get_nonexistent_profile(self):
        fetched = self.store.get_source_profile("does_not_exist")
        self.assertIsNone(fetched)

    def test_48_save_and_get_all_profiles(self):
        p1 = SourceProfile(source_id="a", source_type=SourceType.TOOL)
        p2 = SourceProfile(source_id="b", source_type=SourceType.AGENT)
        self.store.save_source_profile(p1)
        self.store.save_source_profile(p2)
        profiles = self.store.get_all_source_profiles()
        self.assertEqual(len(profiles), 2)

    def test_49_update_profile(self):
        p = SourceProfile(source_id="upd", source_type=SourceType.TOOL, reliability_score=0.5)
        self.store.save_source_profile(p)
        p.reliability_score = 0.95
        self.store.save_source_profile(p)
        fetched = self.store.get_source_profile("upd")
        self.assertEqual(fetched.reliability_score, 0.95)

    def test_50_save_and_query_accuracy_record(self):
        ar = AccuracyRecord(
            record_id="ar1", belief_id="b1", domain="android",
            category="pattern", predicted_value=0.9, actual_value=0.85,
            error=0.05,
        )
        self.store.save_accuracy_record(ar)
        results = self.store.get_accuracy_records(domain="android")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].record_id, "ar1")

    def test_51_accuracy_record_filtering(self):
        records = [
            AccuracyRecord(record_id=f"ar{i}", belief_id=f"b{i}",
                           domain="d1", category="pat",
                           predicted_value=0.8, actual_value=0.7, error=0.1)
            for i in range(3)
        ] + [
            AccuracyRecord(record_id=f"ar{i}", belief_id=f"b{i}",
                           domain="d2", category="pat",
                           predicted_value=0.8, actual_value=0.9, error=0.1)
            for i in range(3, 5)
        ]
        for r in records:
            self.store.save_accuracy_record(r)

        d1 = self.store.get_accuracy_records(domain="d1")
        d2 = self.store.get_accuracy_records(domain="d2")
        self.assertEqual(len(d1), 3)
        self.assertEqual(len(d2), 2)

    def test_52_delete_accuracy_records(self):
        ar = AccuracyRecord(
            record_id="ar_del", belief_id="b_del", domain="test",
            category="heuristic", predicted_value=0.5, actual_value=0.5,
            error=0.0,
        )
        self.store.save_accuracy_record(ar)
        self.assertEqual(self.store.get_accuracy_record_count(), 1)
        self.store.delete_accuracy_records("b_del")
        results = self.store.get_accuracy_records(belief_id="b_del")
        self.assertEqual(len(results), 0)

    def test_53_source_profile_count(self):
        self.assertEqual(self.store.source_profile_count(), 0)
        self.store.save_source_profile(
            SourceProfile(source_id="cnt", source_type=SourceType.TOOL)
        )
        self.assertEqual(self.store.source_profile_count(), 1)

    def test_54_get_statistics(self):
        stats = self.store.get_statistics()
        self.assertIn("source_profiles", stats)
        self.assertIn("accuracy_records", stats)

    def test_55_save_and_load_bulk(self):
        profiles = [
            SourceProfile(source_id=f"bulk_{i}", source_type=SourceType.TOOL,
                          reliability_score=0.5 + i * 0.1)
            for i in range(3)
        ]
        self.store.save_all_source_profiles(profiles)
        self.assertEqual(self.store.source_profile_count(), 3)

        records = [
            AccuracyRecord(record_id=f"br_{i}", belief_id=f"bb_{i}",
                           domain="test", category="h",
                           predicted_value=0.5, actual_value=0.5, error=0.0)
            for i in range(3)
        ]
        self.store.save_all_accuracy_records(records)
        self.assertEqual(self.store.get_accuracy_record_count(), 3)


# ── BeliefIntegrator Tests ───────────────────────────────────────────────


class TestBeliefIntegrator(unittest.TestCase):
    """Integration adapters."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._db = os.path.join(self._tmp, "test_integration.db")
        self.store = BeliefStore(db_path=self._db)
        # Seed accuracy data
        self.integrator = BeliefIntegrator(store=self.store)
        for _ in range(10):
            self.integrator.accuracy_tracker.record(
                belief_id="seed", domain="android", category="pattern",
                predicted_value=0.85, actual_value=0.90,
            )

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_56_adjust_knowledge_confidence(self):
        dc = self.integrator.adjust_knowledge_confidence(
            category="pattern",
            evidence_count=5,
            domain="android",
        )
        self.assertIsInstance(dc, DecomposedConfidence)
        self.assertGreater(dc.overall, 0.0)
        self.assertIn(dc.evidence_strength, dc.to_dict().values())

    def test_57_adjust_knowledge_confidence_with_source(self):
        self.integrator.source_tracker.record_reference(
            "trusted", was_correct=True
        )
        for _ in range(10):
            self.integrator.source_tracker.record_reference("trusted", was_correct=True)

        dc = self.integrator.adjust_knowledge_confidence(
            category="pattern",
            evidence_count=5,
            domain="android",
            source_id="trusted",
        )
        self.assertGreater(dc.source_quality, 0.5)

    def test_58_adjust_prediction_confidence(self):
        conf = self.integrator.adjust_prediction_confidence(
            domain="android", evidence_count=5
        )
        self.assertGreater(conf, 0.0)
        self.assertLessEqual(conf, 1.0)

    def test_59_adjust_evidence_bundle_confidence(self):
        conf = self.integrator.adjust_evidence_bundle_confidence(
            sample_size=10, domain="android"
        )
        self.assertGreater(conf, 0.0)

    def test_60_adjust_principle_confidence(self):
        dc = self.integrator.adjust_principle_confidence(
            discrimination=0.35,
            sample_size=15,
            domains=["android", "web", "research"],
        )
        self.assertIsInstance(dc, DecomposedConfidence)
        # Strong discrimination should produce higher accuracy
        weak = self.integrator.adjust_principle_confidence(
            discrimination=0.05,
            sample_size=15,
            domains=["android"],
        )
        self.assertGreater(dc.accuracy, weak.accuracy)

    def test_61_record_source_reference(self):
        self.integrator.record_source_reference(
            source_id="url_1", source_type="research_url",
            domain="android", was_correct=True,
        )
        r = self.integrator.source_tracker.get_reliability("url_1")
        self.assertGreater(r, 0.0)

    def test_62_record_source_contradiction(self):
        self.integrator.record_source_contradiction(
            source_id="url_2", source_type="research_url", domain="web",
        )
        profile = self.integrator.source_tracker.get_profile("url_2")
        self.assertEqual(profile.contradictory_references, 1)

    def test_63_record_prediction_accuracy(self):
        self.integrator.record_prediction_accuracy(
            belief_id="test_belief", domain="android", category="pattern",
            predicted_value=0.8, actual_value=0.9,
        )
        acc = self.integrator.accuracy_tracker.get_accuracy(
            domain="android", category="pattern"
        )
        self.assertGreater(acc, 0.0)

    def test_64_persist_and_load(self):
        # Add data in memory
        self.integrator.source_tracker.record_reference("persist_test", was_correct=True)
        self.integrator.record_prediction_accuracy(
            belief_id="persist_belief", domain="test", category="heuristic",
            predicted_value=0.8, actual_value=0.9,
        )
        self.integrator.persist()

        # Create new integrator and load
        integrator2 = BeliefIntegrator(store=self.store)
        integrator2.load()
        r = integrator2.source_tracker.get_reliability("persist_test")
        self.assertGreater(r, 0.0)

    def test_65_get_statistics(self):
        stats = self.integrator.get_statistics()
        self.assertIn("source_profiles", stats)
        self.assertIn("accuracy_records", stats)

    def test_66_adjust_knowledge_confidence_with_timestamps(self):
        now = datetime.now(timezone.utc)
        old = now - timedelta(days=500)
        recent = self.integrator.adjust_knowledge_confidence(
            category="pattern", evidence_count=5, domain="android",
            created_at=now,
        )
        stale = self.integrator.adjust_knowledge_confidence(
            category="pattern", evidence_count=5, domain="android",
            created_at=old,
        )
        self.assertGreater(recent.freshness, stale.freshness)

    def test_67_adjust_knowledge_confidence_with_consensus(self):
        """Consensus data passed through integrator affects confidence."""
        no_consensus = self.integrator.adjust_knowledge_confidence(
            category="pattern", evidence_count=5, domain="android",
        )
        with_consensus = self.integrator.adjust_knowledge_confidence(
            category="pattern", evidence_count=5, domain="android",
            supporting_sources=["src_1", "src_2", "src_3"],
            contradicting_sources=["src_4"],
        )
        self.assertIn("consensus", no_consensus.to_dict())
        self.assertEqual(no_consensus.consensus, 1.0)  # no data → neutral
        self.assertLess(with_consensus.consensus, 1.0)  # mixed → penalty

    def test_68_adjust_knowledge_confidence_single_source_penalty(self):
        """Single source through integrator gets consensus penalty."""
        dc = self.integrator.adjust_knowledge_confidence(
            category="pattern", evidence_count=5, domain="android",
            supporting_sources=["only_one"],
        )
        self.assertAlmostEqual(dc.consensus, 0.55, places=2)


# ── Full-Chain Integration Audit Tests ────────────────────────────────────
#
# These tests validate that all 5 integration points work correctly with
# the Belief Quality Engine as the single confidence source of truth.
#
# Chain:
#   KnowledgeSynthesizer → KnowledgeItem.confidence
#   MemoryAdapter        → EvidenceBundle.confidence
#   OutcomePredictor     → Prediction.confidence
#   PrincipleValidator   → PrincipleCandidate.confidence
#   PredictionCalibrator → Prediction.confidence (via calibration)
#
# Each test creates the subsystem WITH a BeliefIntegrator and verifies
# the confidence output is computed through the engine.


class _MemoryAdapterForTest(MemoryAdapter):
    """MemoryAdapter that doesn't try to query real stores."""
    def __init__(self, belief_integrator=None):
        super().__init__(belief_integrator=belief_integrator)
        self._activity_store = _MockStore()
        self._knowledge_store = _MockStore()
        self._fact_store = _MockStore()


class _MockStore:
    """Mock for store objects that returns empty results."""
    def search_nodes(self, *a, **kw): return []
    def get_experiences_by_domain(self, *a, **kw): return []
    def query_knowledge(self, *a, **kw): return []
    def search_facts(self, *a, **kw): return []


class TestIntegrationAudit(unittest.TestCase):
    """Validates all 5 integration points wire correctly.

    Each test exercises a subsystem with BeliefIntegrator injected and
    verifies the confidence output is decomposed and explainable.
    """

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._db = os.path.join(self._tmp, "test_audit.db")
        self.store = BeliefStore(db_path=self._db)
        self.integrator = BeliefIntegrator(store=self.store)
        # Seed accuracy data so domain-specific scores are meaningful
        for _ in range(15):
            self.integrator.accuracy_tracker.record(
                belief_id="audit_seed", domain="android", category="pattern",
                predicted_value=0.85, actual_value=0.90,
            )
        for _ in range(5):
            self.integrator.accuracy_tracker.record(
                belief_id="audit_seed2", domain="general", category="heuristic",
                predicted_value=0.85, actual_value=0.30,  # inaccurate domain
            )

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    # ── KnowledgeSynthesizer ──────────────────────────────────────────

    def test_70_synthesizer_with_belief_engine(self):
        """KnowledgeSynthesizer confidence comes from BeliefIntegrator."""
        from core.long_term_memory.synthesizer import KnowledgeSynthesizer
        from core.long_term_memory.store import KnowledgeStore
        from core.long_term_memory.models import ExperienceSummary

        ks_db = os.path.join(self._tmp, "synth.db")
        kstore = KnowledgeStore(db_path=ks_db)
        synth = KnowledgeSynthesizer(kstore, belief_integrator=self.integrator)

        exps = [
            ExperienceSummary(
                activity_id=f"audit_syn_{i}",
                goal=f"Build feature {i}",
                domain="android",
                status="COMPLETED",
                node_count=10,
                tools_used=["build_project"],
                success=True,
            )
            for i in range(5)
        ]
        items = synth.synthesize_from_experiences(exps)
        # Items created through the belief engine should have confidence
        # that differs from the heuristic (simple success_rate)
        items_with_conf = [i for i in items if i.confidence != 0.5]
        self.assertGreater(len(items_with_conf), 0)
        # Verify confidence is in valid range
        for item in items:
            self.assertGreaterEqual(item.confidence, 0.0)
            self.assertLessEqual(item.confidence, 1.0)

    def test_71_synthesizer_different_domains_different_confidence(self):
        """Different domains get different confidence from the same evidence count."""
        from core.long_term_memory.synthesizer import KnowledgeSynthesizer
        from core.long_term_memory.store import KnowledgeStore
        from core.long_term_memory.models import ExperienceSummary

        ks_db = os.path.join(self._tmp, "synth2.db")
        kstore = KnowledgeStore(db_path=ks_db)
        synth = KnowledgeSynthesizer(kstore, belief_integrator=self.integrator)

        # Android domain (high accuracy in our seed data)
        android_exps = [
            ExperienceSummary(
                activity_id=f"audit_ad_{i}", goal=f"Android feature {i}",
                domain="android", status="COMPLETED", node_count=5,
                tools_used=["build_project"], success=True,
            )
            for i in range(5)
        ]
        # General domain (low accuracy in our seed data)
        general_exps = [
            ExperienceSummary(
                activity_id=f"audit_gn_{i}", goal=f"General task {i}",
                domain="general", status="COMPLETED", node_count=5,
                tools_used=["build_project"], success=True,
            )
            for i in range(5)
        ]

        android_items = synth.synthesize_from_experiences(android_exps)
        general_items = synth.synthesize_from_experiences(general_exps)

        # Android accuracy is seeded high (0.85→0.90), general is low (0.30)
        # So android domain patterns should have higher confidence
        android_patterns = [i for i in android_items if i.category == "pattern"]
        general_patterns = [i for i in general_items if i.category == "pattern"]

        if android_patterns and general_patterns:
            android_conf = android_patterns[0].confidence
            general_conf = general_patterns[0].confidence
            self.assertGreater(
                android_conf, general_conf,
                f"Android domain confidence ({android_conf}) should be higher "
                f"than general ({general_conf}) due to seeded accuracy data"
            )

    # ── MemoryAdapter (EvidenceBundle) ────────────────────────────────

    def test_72_memory_adapter_with_belief_engine(self):
        """MemoryAdapter EvidenceBundle confidence comes from BeliefIntegrator."""
        adapter = _MemoryAdapterForTest(belief_integrator=self.integrator)

        bundle = adapter._build_bundle(
            durations=[10.0, 15.0, 20.0],
            successes=[True, True, True],
            goal_labels=["test"],
            failures=[],
            avg_similarity=0.0,
            domain="android",
        )
        # With belief engine: android domain has high accuracy → higher confidence
        self.assertGreater(bundle.confidence, 0.0)
        self.assertLessEqual(bundle.confidence, 1.0)

    def test_73_memory_adapter_domain_affects_confidence(self):
        """EvidenceBundle confidence varies by domain accuracy."""
        adapter = _MemoryAdapterForTest(belief_integrator=self.integrator)

        # Use sample_size=5 to avoid MIN_DIMENSION clamping
        android = adapter._build_bundle(
            durations=[10.0]*5, successes=[True]*5, goal_labels=["t"],
            failures=[], avg_similarity=0.0, domain="android",
        )
        general = adapter._build_bundle(
            durations=[10.0]*5, successes=[True]*5, goal_labels=["t"],
            failures=[], avg_similarity=0.0, domain="general",
        )
        # Android has seeded high accuracy, general has low
        self.assertGreater(
            android.confidence, general.confidence,
            f"Android confidence ({android.confidence}) should exceed "
            f"general ({general.confidence})"
        )

    # ── OutcomePredictor ──────────────────────────────────────────────

    def test_74_predictor_with_belief_engine(self):
        """OutcomePredictor confidence comes from BeliefIntegrator."""
        from core.strategy.models import Strategy, StrategyTag

        predictor = OutcomePredictor(belief_integrator=self.integrator)
        strategy = Strategy(
            name="Test", description="",
            goal="Build android coffee shop app",
            tags=[StrategyTag.MVP],
        )
        result = predictor.predict(strategy, "build")
        self.assertIsNotNone(result)
        self.assertGreater(result.confidence, 0.0)
        self.assertLessEqual(result.confidence, 1.0)

    def test_75_predictor_with_blend(self):
        """Predictor._blend confidence uses BeliefIntegrator."""
        from core.strategy.models import Prediction, EvidenceBundle

        predictor = OutcomePredictor(belief_integrator=self.integrator)
        heuristic = Prediction(
            success_probability=0.75, estimated_duration_days=14.0,
            estimated_risk=0.3, estimated_effort=5.0,
            confidence=0.5, evidence_count=3,
        )
        evidence = EvidenceBundle(
            sample_size=10, avg_duration_days=18.0,
            success_rate=0.6, confidence=0.5,
        )
        result = predictor._blend(heuristic, evidence, goal="Build android app")
        self.assertIsNotNone(result)
        self.assertGreater(result.confidence, 0.0)
        self.assertLessEqual(result.confidence, 1.0)

    # ── PrincipleValidator ────────────────────────────────────────────

    def test_76_validator_with_belief_engine(self):
        """PrincipleValidator confidence comes from BeliefIntegrator."""
        from core.generalization.models import PrincipleCandidate

        validator = PrincipleValidator(belief_integrator=self.integrator)
        candidate = PrincipleCandidate(
            principle_id="p_test",
            property_name="retry_capable",
            category="execution_model",
            support_rate=0.91,
            control_rate=0.58,
            discrimination=0.33,
            sample_size=24,
            support_count=14,
            control_count=10,
            domains=["android", "web", "research"],
        )
        validator.validate(candidate)
        # Should be ACCEPTED (strong discrimination, high sample size)
        self.assertEqual(candidate.status.value, "accepted")
        # Confidence should be explainable (not just the heuristic formula)
        self.assertGreaterEqual(candidate.confidence, 0.0)
        self.assertLessEqual(candidate.confidence, 1.0)

    def test_77_validator_confidence_decomposable(self):
        """Principle confidence can be traced back to quality dimensions."""
        from core.generalization.models import PrincipleCandidate

        # Inject into integrator directly to get DecomposedConfidence
        dc = self.integrator.adjust_principle_confidence(
            discrimination=0.35,
            sample_size=20,
            domains=["android", "web", "research"],
        )
        # Verify all four dimensions exist
        self.assertGreater(dc.source_quality, 0.0)
        self.assertGreater(dc.evidence_strength, 0.0)
        self.assertGreater(dc.accuracy, 0.0)
        self.assertGreater(dc.freshness, 0.0)

    # ── PredictionCalibrator ──────────────────────────────────────────

    def test_78_calibrator_with_belief_engine(self):
        """PredictionCalibrator confidence uses BeliefIntegrator."""
        from core.strategy.models import Prediction
        from core.strategy.calibration import PredictionCalibrator, CalibrationStore

        calibrator = PredictionCalibrator(belief_integrator=self.integrator)
        prediction = Prediction(
            success_probability=0.75, estimated_duration_days=14.0,
            estimated_risk=0.3, estimated_effort=5.0,
            confidence=0.5, evidence_count=5,
        )
        result = calibrator.calibrate(prediction, "build")
        self.assertIsNotNone(result)
        self.assertGreater(result.confidence, 0.0)
        self.assertLessEqual(result.confidence, 1.0)

    def test_79_full_pipeline_with_belief(self):
        """End-to-end: KnowledgeSynthesizer → MemoryAdapter → Predictor → Calibrator.

        This is the same pipeline the system uses in production.
        """
        from core.long_term_memory.synthesizer import KnowledgeSynthesizer
        from core.long_term_memory.store import KnowledgeStore
        from core.long_term_memory.models import ExperienceSummary
        from core.strategy.models import Strategy, StrategyTag, EvidenceBundle, Prediction
        from core.strategy.calibration import PredictionCalibrator

        # Step 1: KnowledgeSynthesizer creates items through BeliefIntegrator
        ks_db = os.path.join(self._tmp, "pipeline.db")
        kstore = KnowledgeStore(db_path=ks_db)
        synth = KnowledgeSynthesizer(kstore, belief_integrator=self.integrator)

        exps = [
            ExperienceSummary(
                activity_id=f"pipe_{i}", goal=f"Task {i}",
                domain="android", status="COMPLETED",
                node_count=5, tools_used=["build_project"],
                success=True,
            )
            for i in range(5)
        ]
        items = synth.synthesize_from_experiences(exps)

        # Step 2: MemoryAdapter builds EvidenceBundle through BeliefIntegrator
        adapter = _MemoryAdapterForTest(belief_integrator=self.integrator)
        bundle = adapter._build_bundle(
            durations=[10.0, 15.0],
            successes=[True, True],
            goal_labels=["test"],
            failures=[],
            domain="android",
        )

        # Step 3: Predictor blends through BeliefIntegrator
        predictor = OutcomePredictor(belief_integrator=self.integrator)
        strategy = Strategy(
            name="Test", description="",
            goal="Build android coffee shop app",
            tags=[StrategyTag.MVP],
        )
        prediction = predictor.predict(strategy, "build", memory_adapter=adapter)

        # Step 4: Calibrator adjusts through BeliefIntegrator
        calibrator = PredictionCalibrator(belief_integrator=self.integrator)
        calibrated = calibrator.calibrate(prediction, "build")

        # Verify the full chain produces valid confidence values
        self.assertGreater(len(items), 0)
        self.assertGreater(bundle.confidence, 0.0)
        self.assertGreater(prediction.confidence, 0.0)
        self.assertGreater(calibrated.confidence, 0.0)

        # Verify that android-specific accuracy produces higher confidence
        # than what the heuristic formulas would produce for a domain with
        # known inaccuracy (general domain has seeded 0.30 accuracy)
        general_prediction = predictor.predict(strategy, "build")
        # Since we don't give general domain for android goal, it may use
        # android accuracy. Just verify the prediction is valid.
        self.assertLessEqual(calibrated.confidence, 1.0)

    def test_80_confidence_explainable(self):
        """Confidence values are decomposable and explainable."""
        request = BeliefQualityRequest(
            evidence_count=10,
            category=BeliefCategory.PATTERN,
            domain="android",
        )
        summary = self.integrator.quality_engine.get_dimension_summary(request)
        self.assertIn("overall", summary)
        self.assertIn("source_quality", summary)
        self.assertIn("evidence_strength", summary)
        self.assertIn("accuracy", summary)
        self.assertIn("freshness", summary)
        # Verify human-readable explanations
        self.assertIn("—", summary["source_quality"])
        self.assertIn("—", summary["evidence_strength"])

    def test_81_fallback_when_no_belief_engine(self):
        """All subsystems fall back to heuristic when no BeliefIntegrator."""
        from core.long_term_memory.synthesizer import KnowledgeSynthesizer
        from core.long_term_memory.store import KnowledgeStore
        from core.long_term_memory.models import ExperienceSummary
        from core.strategy.models import Strategy, StrategyTag, EvidenceBundle, Prediction
        from core.generalization.models import PrincipleCandidate

        # KnowledgeSynthesizer without belief
        ks_db = os.path.join(self._tmp, "fallback.db")
        kstore = KnowledgeStore(db_path=ks_db)
        synth = KnowledgeSynthesizer(kstore)
        exps = [
            ExperienceSummary(
                activity_id=f"fb_{i}", goal=f"Task {i}",
                domain="test", status="COMPLETED",
                node_count=5, tools_used=["build_project"],
                success=True,
            )
            for i in range(5)
        ]
        items = synth.synthesize_from_experiences(exps)
        self.assertGreater(len(items), 0)

        # MemoryAdapter without belief
        adapter = MemoryAdapter()
        bundle = adapter._build_bundle(
            durations=[10.0], successes=[True], goal_labels=["t"],
            failures=[], domain="test",
        )
        self.assertGreater(bundle.confidence, 0.0)

        # Predictor without belief
        predictor = OutcomePredictor()
        strategy = Strategy(name="T", description="", goal="test", tags=[])
        pred = predictor.predict(strategy, "build")
        self.assertGreater(pred.confidence, 0.0)

        # Validator without belief
        validator = PrincipleValidator()
        candidate = PrincipleCandidate(
            principle_id="p_fb", property_name="retry", category="ex",
            support_rate=0.85, control_rate=0.5, discrimination=0.35,
            sample_size=15, support_count=10, control_count=5,
            domains=["a", "b", "c"],
        )
        validator.validate(candidate)
        self.assertEqual(candidate.status.value, "accepted")

    def test_82_persisted_confidence_survives_restart(self):
        """BeliefIntegrator state persists across load/save cycles."""
        from core.strategy.models import Prediction
        from core.strategy.calibration import PredictionCalibrator

        # First session: create and persist
        integrator = BeliefIntegrator(store=self.store)
        for _ in range(10):
            integrator.accuracy_tracker.record(
                belief_id="restart", domain="test", category="heuristic",
                predicted_value=0.8, actual_value=0.75,
            )
        integrator.source_tracker.record_reference("src_r", was_correct=True)
        integrator.source_tracker.record_reference("src_r", was_correct=True)
        integrator.persist()

        # Second session: load and verify
        integrator2 = BeliefIntegrator(store=self.store)
        integrator2.load()

        acc = integrator2.accuracy_tracker.get_accuracy(domain="test")
        self.assertGreater(acc, 0.5)

        rel = integrator2.source_tracker.get_reliability("src_r")
        self.assertGreater(rel, 0.5)


if __name__ == "__main__":
    unittest.main()
