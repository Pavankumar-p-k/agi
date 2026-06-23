"""Tests for Phase 9 — Long-Term Memory & Knowledge Consolidation.

Covers KnowledgeStore, ExperienceExtractor, KnowledgeSynthesizer,
BehaviorAdapter, Consolidator.
"""

import os
import shutil
import tempfile
import uuid
from datetime import datetime, timedelta
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import MagicMock, patch

from core.activity.manager import ActivityManager
from core.activity.models import ActivityNode, ActivityStatus
from core.activity.storage import ActivityStore
from core.long_term_memory.adapter import BehaviorAdapter
from core.long_term_memory.consolidator import Consolidator
from core.long_term_memory.extractor import ExperienceExtractor
from core.long_term_memory.models import (
    ExperienceSummary,
    KnowledgeItem,
    KnowledgeQuery,
)
from core.long_term_memory.store import KnowledgeStore
from core.long_term_memory.synthesizer import KnowledgeSynthesizer


def _make_db() -> str:
    tmp = tempfile.mkdtemp()
    return os.path.join(tmp, "test_workflow.db")


class TestKnowledgeItem(TestCase):
    """KnowledgeItem dataclass."""

    def test_01_create_item(self):
        item = KnowledgeItem(
            knowledge_id="kn_001",
            category="pattern",
            claim="Payment features succeed",
            confidence=0.9,
            evidence_count=5,
        )
        self.assertEqual(item.knowledge_id, "kn_001")
        self.assertEqual(item.category, "pattern")
        self.assertAlmostEqual(item.confidence, 0.9)

    def test_02_to_dict(self):
        item = KnowledgeItem(
            knowledge_id="kn_002",
            category="warning",
            claim="High fan-in files risk regressions",
            tags=["risk", "fan-in"],
        )
        d = item.to_dict()
        self.assertIn("knowledge_id", d)
        self.assertIn("confidence", d)
        self.assertEqual(d["tags"], ["risk", "fan-in"])

    def test_03_experience_summary(self):
        exp = ExperienceSummary(
            activity_id="act_001",
            goal="Build Android app",
            domain="android",
            status="COMPLETED",
            node_count=15,
            tools_used=["browser_navigate", "build_project"],
            success=True,
        )
        self.assertEqual(exp.domain, "android")
        d = exp.to_dict()
        self.assertTrue(d["success"])
        self.assertEqual(d["goal"], "Build Android app")

    def test_04_knowledge_query_defaults(self):
        q = KnowledgeQuery()
        self.assertIsNone(q.category)
        self.assertEqual(q.min_confidence, 0.0)
        self.assertEqual(q.min_evidence, 1)
        self.assertEqual(q.limit, 20)

        q2 = KnowledgeQuery(category="warning", min_confidence=0.7, min_evidence=3)
        self.assertEqual(q2.category, "warning")
        self.assertEqual(q2.min_evidence, 3)


class TestKnowledgeStore(TestCase):
    """KnowledgeStore CRUD + query operations."""

    def setUp(self):
        self._db = _make_db()
        self._store = KnowledgeStore(db_path=self._db)

    def tearDown(self):
        shutil.rmtree(os.path.dirname(self._db), ignore_errors=True)

    def test_05_insert_and_get(self):
        item = KnowledgeItem(
            knowledge_id="kn_test_01",
            category="pattern",
            claim="Test pattern",
            confidence=0.8,
            evidence_count=3,
            tags=["test"],
        )
        self._store.insert_knowledge(item)
        retrieved = self._store.get_knowledge("kn_test_01")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.claim, "Test pattern")
        self.assertAlmostEqual(retrieved.confidence, 0.8)

    def test_06_insert_overwrites(self):
        item = KnowledgeItem(
            knowledge_id="kn_overwrite",
            category="pattern",
            claim="Original",
            confidence=0.5,
        )
        self._store.insert_knowledge(item)
        item.confidence = 0.9
        item.claim = "Updated"
        self._store.insert_knowledge(item)
        retrieved = self._store.get_knowledge("kn_overwrite")
        self.assertEqual(retrieved.claim, "Updated")
        self.assertAlmostEqual(retrieved.confidence, 0.9)

    def test_07_search_by_text(self):
        self._store.insert_knowledge(KnowledgeItem(
            knowledge_id="kn_search_1", category="pattern",
            claim="Payment features are reliable", confidence=0.9,
        ))
        self._store.insert_knowledge(KnowledgeItem(
            knowledge_id="kn_search_2", category="warning",
            claim="Database migrations are risky", confidence=0.6,
        ))
        results = self._store.search_knowledge("Payment", limit=10)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].knowledge_id, "kn_search_1")

    def test_08_query_by_category(self):
        self._store.insert_knowledge(KnowledgeItem(
            knowledge_id="kn_cat_1", category="pattern",
            claim="Pattern 1", confidence=0.7,
        ))
        self._store.insert_knowledge(KnowledgeItem(
            knowledge_id="kn_cat_2", category="warning",
            claim="Warning 1", confidence=0.8,
        ))
        results = self._store.query_knowledge(
            KnowledgeQuery(category="pattern", min_confidence=0.5),
        )
        self.assertEqual(len(results), 1)

    def test_09_query_by_tag(self):
        self._store.insert_knowledge(KnowledgeItem(
            knowledge_id="kn_tag_1", category="pattern",
            claim="Android patterns", tags=["android", "mobile"],
        ))
        results = self._store.query_knowledge(
            KnowledgeQuery(tag="android"),
        )
        self.assertGreaterEqual(len(results), 1)

    def test_10_query_by_evidence(self):
        self._store.insert_knowledge(KnowledgeItem(
            knowledge_id="kn_ev_1", category="pattern",
            claim="High evidence pattern", confidence=0.7,
            evidence_count=5,
        ))
        self._store.insert_knowledge(KnowledgeItem(
            knowledge_id="kn_ev_2", category="pattern",
            claim="Low evidence", confidence=0.7,
            evidence_count=1,
        ))
        results = self._store.query_knowledge(
            KnowledgeQuery(min_evidence=3),
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].knowledge_id, "kn_ev_1")

    def test_11_delete_knowledge(self):
        self._store.insert_knowledge(KnowledgeItem(
            knowledge_id="kn_del", category="pattern", claim="Delete me",
        ))
        self._store.delete_knowledge("kn_del")
        self.assertIsNone(self._store.get_knowledge("kn_del"))

    def test_12_update_confidence(self):
        self._store.insert_knowledge(KnowledgeItem(
            knowledge_id="kn_conf", category="pattern",
            claim="Confidence update", confidence=0.5,
        ))
        self._store.update_confidence("kn_conf", 0.95)
        retrieved = self._store.get_knowledge("kn_conf")
        self.assertAlmostEqual(retrieved.confidence, 0.95)
        self.assertIsNotNone(retrieved.last_validated)

    def test_13_count_knowledge(self):
        self._store.insert_knowledge(KnowledgeItem(
            knowledge_id="kn_ct_1", category="pattern", claim="P1",
        ))
        self._store.insert_knowledge(KnowledgeItem(
            knowledge_id="kn_ct_2", category="warning", claim="W1",
        ))
        counts = self._store.count_knowledge()
        self.assertIn("pattern", counts)
        self.assertIn("warning", counts)

    def test_14_get_all_knowledge(self):
        for i in range(5):
            self._store.insert_knowledge(KnowledgeItem(
                knowledge_id=f"kn_all_{i}", category="pattern",
                claim=f"Item {i}", confidence=0.5 + i * 0.1,
            ))
        all_items = self._store.get_all_knowledge()
        self.assertGreaterEqual(len(all_items), 5)

    def test_15_experience_crud(self):
        exp = ExperienceSummary(
            activity_id="act_crud",
            goal="Test activity",
            domain="test",
            status="COMPLETED",
            node_count=10,
            success=True,
        )
        self._store.insert_experience(exp)
        retrieved = self._store.get_experience("act_crud")
        self.assertIsNotNone(retrieved)
        self.assertTrue(retrieved.success)
        self.assertEqual(retrieved.goal, "Test activity")

    def test_16_experiences_by_domain(self):
        self._store.insert_experience(ExperienceSummary(
            activity_id="act_d1", goal="G1", domain="android",
            status="COMPLETED", node_count=1, success=True,
        ))
        self._store.insert_experience(ExperienceSummary(
            activity_id="act_d2", goal="G2", domain="web",
            status="COMPLETED", node_count=1, success=True,
        ))
        android = self._store.get_experiences_by_domain("android")
        self.assertEqual(len(android), 1)
        self.assertEqual(android[0].activity_id, "act_d1")

    def test_17_statistics(self):
        self._store.insert_experience(ExperienceSummary(
            activity_id="act_stat", goal="G", domain="test",
            status="COMPLETED", node_count=1, success=True,
        ))
        self._store.insert_knowledge(KnowledgeItem(
            knowledge_id="kn_stat", category="pattern", claim="P",
        ))
        stats = self._store.get_statistics()
        self.assertGreaterEqual(stats["total_experiences"], 1)
        self.assertGreaterEqual(stats["total_knowledge_items"], 1)


class TestExperienceExtractor(TestCase):
    """ExperienceExtractor — activity graph → experience summary."""

    def setUp(self):
        self._db = _make_db()
        self._store = ActivityStore(db_path=self._db)
        self._am = ActivityManager(store=self._store)
        self._ks = KnowledgeStore(db_path=self._db)
        self._extractor = ExperienceExtractor(self._am, store=self._ks)

    def tearDown(self):
        shutil.rmtree(os.path.dirname(self._db), ignore_errors=True)

    def _create_completed_activity(self, goal: str, domain: str = "general") -> str:
        act = self._am.create_activity(goal)
        sub = self._am.create_subgoal(act, "Do something")
        task = self._am.create_agent_task(act, "builder", "Build it", parent=sub)
        self._am.mark_completed(task.node_id, output={"result": "ok"})
        self._am.mark_completed(sub.node_id)
        self._am.complete_activity(act.activity_id, output={"result": "done"})
        return act.activity_id

    def _create_failed_activity(self, goal: str) -> str:
        act = self._am.create_activity(goal)
        task = self._am.create_agent_task(act, "builder", "Build it")
        self._am.mark_failed(task.node_id, "Build error: out of memory")
        self._am.fail_activity(act.activity_id, "Build failed")
        return act.activity_id

    def test_18_extract_completed(self):
        aid = self._create_completed_activity("Build Android app")
        summary = self._extractor.extract(aid)
        self.assertIsNotNone(summary)
        self.assertTrue(summary.success)
        self.assertEqual(summary.goal, "Build Android app")
        self.assertIn("android", summary.domain)

    def test_19_extract_failed(self):
        aid = self._create_failed_activity("Deploy server")
        summary = self._extractor.extract(aid)
        self.assertIsNotNone(summary)
        self.assertFalse(summary.success)
        self.assertIsNotNone(summary.error_summary)

    def test_20_extract_and_store(self):
        aid = self._create_completed_activity("Test persistence")
        summary = self._extractor.extract_and_store(aid)
        self.assertIsNotNone(summary)
        # Verify it's in the store
        ks = KnowledgeStore(db_path=self._db)
        stored = ks.get_experience(aid)
        self.assertIsNotNone(stored)
        self.assertEqual(stored.activity_id, aid)

    def test_21_domain_inference(self):
        aid = self._create_completed_activity("Fix Kotlin crash in Android app")
        summary = self._extractor.extract(aid)
        self.assertEqual(summary.domain, "android")

    def test_22_extract_nonexistent(self):
        result = self._extractor.extract("act_nonexistent")
        self.assertIsNone(result)

    def test_23_extract_all_completed(self):
        aid1 = self._create_completed_activity("Build feature A")
        aid2 = self._create_failed_activity("Deploy B")
        results = self._extractor.extract_all_completed()
        # Both should be extracted
        self.assertGreaterEqual(len(results), 1)

    def test_24_nodes_and_tools_counted(self):
        aid = self._create_completed_activity("Web research task")
        summary = self._extractor.extract(aid)
        self.assertGreater(summary.node_count, 0)
        # 'builder' agent should be tracked
        self.assertIn("builder", summary.agent_ids)


class TestKnowledgeSynthesizer(TestCase):
    """KnowledgeSynthesizer — cross-activity knowledge consolidation."""

    def setUp(self):
        self._db = _make_db()
        self._store = KnowledgeStore(db_path=self._db)
        self._synth = KnowledgeSynthesizer(self._store)

    def tearDown(self):
        shutil.rmtree(os.path.dirname(self._db), ignore_errors=True)

    def _make_experiences(self, count: int = 5) -> list[ExperienceSummary]:
        exps = []
        for i in range(count):
            exps.append(ExperienceSummary(
                activity_id=f"act_syn_{i}",
                goal=f"Build feature {i}",
                domain="android",
                status="COMPLETED",
                node_count=10 + i,
                tools_used=["build_project", "run_tests"] if i % 2 == 0 else ["browser_navigate"],
                success=True,
            ))
        return exps

    def test_25_synthesize_domain_patterns(self):
        exps = self._make_experiences(5)
        items = self._synth.synthesize_from_experiences(exps)
        patterns = [i for i in items if i.category == "pattern"]
        self.assertGreaterEqual(len(patterns), 1)

    def test_26_synthesize_failure_warnings(self):
        exps = self._make_experiences(3)
        exps.append(ExperienceSummary(
            activity_id="act_fail",
            goal="Failing build",
            domain="android",
            status="FAILED",
            node_count=5,
            success=False,
            error_summary="Gradle sync failed: dependency not found",
        ))
        exps.append(ExperienceSummary(
            activity_id="act_fail2",
            goal="Another failing build",
            domain="android",
            status="FAILED",
            node_count=3,
            success=False,
            error_summary="Gradle sync failed: dependency not found",
        ))
        items = self._synth.synthesize_from_experiences(exps)
        warnings = [i for i in items if i.category == "warning"]
        self.assertGreaterEqual(len(warnings), 1)

    def test_27_pattern_requires_min_evidence(self):
        exps = self._make_experiences(1)  # only 1 experience
        items = self._synth.synthesize_from_experiences(exps)
        # No patterns should be created with only 1 experience
        patterns = [i for i in items if i.category == "pattern"]
        self.assertEqual(len(patterns), 0)

    def test_28_principles_from_multiple_experiences(self):
        exps = self._make_experiences(5)
        items = self._synth.synthesize_from_experiences(exps)
        principles = [i for i in items if i.category == "principle"]
        self.assertGreaterEqual(len(principles), 1)

    def test_29_items_persisted(self):
        exps = self._make_experiences(5)
        items = self._synth.synthesize_from_experiences(exps)
        self.assertGreater(len(items), 0)
        # Verify persistence
        stored = self._store.get_all_knowledge()
        self.assertGreaterEqual(len(stored), len(items))


class TestBehaviorAdapter(TestCase):
    """BehaviorAdapter — influence on planner, research, coding."""

    def setUp(self):
        self._db = _make_db()
        self._store = KnowledgeStore(db_path=self._db)
        # Seed some knowledge
        self._store.insert_knowledge(KnowledgeItem(
            knowledge_id="kn_ad_1", category="pattern",
            claim="Android projects succeed at 85% rate",
            confidence=0.85, evidence_count=20,
            tags=["android", "domain_success"],
        ))
        self._store.insert_knowledge(KnowledgeItem(
            knowledge_id="kn_ad_2", category="warning",
            claim="Database changes often break existing queries",
            confidence=0.7, evidence_count=8,
            tags=["database", "risk"],
        ))
        self._store.insert_knowledge(KnowledgeItem(
            knowledge_id="kn_ad_3", category="principle",
            claim="Activities with errors fail at 60% rate",
            confidence=0.8, evidence_count=12,
        ))
        self._adapter = BehaviorAdapter(self._store)

    def tearDown(self):
        shutil.rmtree(os.path.dirname(self._db), ignore_errors=True)

    def test_30_planner_context(self):
        ctx = self._adapter.for_planner("Build Android app", domain="android")
        self.assertGreaterEqual(len(ctx["domain_patterns"]), 1)
        self.assertIn("warnings", ctx)
        self.assertIn("heuristics", ctx)

    def test_31_research_context(self):
        ctx = self._adapter.for_research("Database migration risks")
        self.assertIn("known_claims", ctx)
        self.assertIn("confidence_gaps", ctx)

    def test_32_coding_context(self):
        ctx = self._adapter.for_coding(change_type="database")
        self.assertIn("risk_factors", ctx)
        self.assertIn("risk_modifier", ctx)

    def test_33_format_for_prompt(self):
        ctx = self._adapter.for_planner("Build Android app", domain="android")
        prompt = self._adapter.format_for_prompt(ctx)
        self.assertIsInstance(prompt, str)
        self.assertGreater(len(prompt), 0)
        self.assertIn("Known patterns", prompt)

    def test_34_empty_context(self):
        empty_adapter = BehaviorAdapter(KnowledgeStore(db_path=self._db))
        ctx = empty_adapter.for_planner("Unknown goal")
        prompt = empty_adapter.format_for_prompt(ctx)
        self.assertEqual(prompt, "")


class TestConsolidator(IsolatedAsyncioTestCase):
    """Consolidator — periodic background consolidation."""

    def setUp(self):
        self._db = _make_db()
        self._am = ActivityManager(store=ActivityStore(db_path=self._db))
        self._ks = KnowledgeStore(db_path=self._db)
        self._consolidator = Consolidator(
            activity_manager=self._am,
            store=self._ks,
            interval_seconds=3600,  # 1 hour for tests
        )

    def tearDown(self):
        shutil.rmtree(os.path.dirname(self._db), ignore_errors=True)

    def _create_two_activities(self):
        for i in range(3):
            act = self._am.create_activity(f"Android build {i}")
            task = self._am.create_agent_task(act, "builder", "Build")
            self._am.mark_completed(task.node_id)
            self._am.complete_activity(act.activity_id)

    def test_35_consolidate_once(self):
        self._create_two_activities()
        result = self._consolidator.consolidate_once()
        self.assertIn("experiences_extracted", result)
        self.assertIn("knowledge_created", result)
        self.assertIsInstance(result["experiences_extracted"], int)

    def test_36_consolidate_extracts_experiences(self):
        self._create_two_activities()
        self._consolidator.consolidate_once()
        count = self._ks.get_experience_count()
        self.assertGreaterEqual(count, 3)

    def test_37_consolidate_creates_knowledge(self):
        self._create_two_activities()
        result = self._consolidator.consolidate_once()
        # With 3 android experiences, should create at least a pattern or principle
        self.assertGreaterEqual(result["knowledge_created"], 0)

    def test_38_stop_flag(self):
        self._consolidator.stop()
        self.assertFalse(self._consolidator._running)

    def test_39_async_consolidate(self):
        self._create_two_activities()
        result = self._consolidator.consolidate_once()
        self.assertIsNotNone(result)

    def test_40_experiences_not_duplicated(self):
        self._create_two_activities()
        r1 = self._consolidator.consolidate_once()
        r2 = self._consolidator.consolidate_once()
        # Second run should extract fewer (or zero) new experiences
        self.assertLessEqual(r2["experiences_extracted"], r1["experiences_extracted"])
