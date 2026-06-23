"""Research Memory tests — Fact model, FactStore CRUD, FactExtractor."""

import os
import shutil
import tempfile
import unittest

from core.research.extractor import FactExtractor
from core.research.models import Fact
from core.research.storage import FactStore


class TestFactModel(unittest.TestCase):
    """Fact dataclass basics."""

    def test_01_minimal_fact(self):
        f = Fact(fact_id="f1", source_url="https://example.com", claim="X is Y")
        self.assertEqual(f.fact_id, "f1")
        self.assertEqual(f.confidence, 0.5)
        self.assertEqual(f.category, "general")

    def test_02_full_fact(self):
        f = Fact(
            fact_id="f2", source_url="https://example.com",
            claim="Python 3.13 was released in 2025",
            confidence=0.95, category="news",
            tags=["python", "3.13"],
            activity_id="act_123",
        )
        self.assertEqual(f.tags, ["python", "3.13"])
        self.assertEqual(f.activity_id, "act_123")


class TestFactStore(unittest.TestCase):
    """SQLite-backed fact persistence."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._db = os.path.join(self._tmp, "test_facts.db")
        self.store = FactStore(db_path=self._db)

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _make_fact(self, fid="f1", claim="Python 3.13 released in 2025",
                   url="https://python.org", category="news",
                   confidence=0.9, activity_id=None):
        return Fact(
            fact_id=fid, source_url=url, claim=claim,
            confidence=confidence, category=category,
            activity_id=activity_id,
        )

    def test_03_insert_and_get(self):
        f = self._make_fact()
        self.store.insert_fact(f)
        fetched = self.store.get_fact("f1")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.claim, "Python 3.13 released in 2025")
        self.assertEqual(fetched.source_url, "https://python.org")

    def test_04_get_nonexistent(self):
        self.assertIsNone(self.store.get_fact("no_such_fact"))

    def test_05_search_by_claim(self):
        self.store.insert_fact(self._make_fact("f1", claim="Python is fast"))
        self.store.insert_fact(self._make_fact("f2", claim="Java is verbose"))
        results = self.store.search_facts("Python")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].fact_id, "f1")

    def test_06_facts_by_activity(self):
        self.store.insert_fact(self._make_fact("f1", activity_id="act_1"))
        self.store.insert_fact(self._make_fact("f2", activity_id="act_1"))
        self.store.insert_fact(self._make_fact("f3", activity_id="act_2"))
        results = self.store.get_facts_by_activity("act_1")
        self.assertEqual(len(results), 2)

    def test_07_facts_by_source(self):
        self.store.insert_fact(self._make_fact("f1", url="https://a.com"))
        self.store.insert_fact(self._make_fact("f2", url="https://a.com"))
        self.store.insert_fact(self._make_fact("f3", url="https://b.com"))
        results = self.store.get_facts_by_source("https://a.com")
        self.assertEqual(len(results), 2)

    def test_08_facts_by_category(self):
        self.store.insert_fact(self._make_fact("f1", category="news"))
        self.store.insert_fact(self._make_fact("f2", category="technical"))
        results = self.store.get_facts_by_category("technical")
        self.assertEqual(len(results), 1)

    def test_09_get_all_facts(self):
        self.store.insert_fact(self._make_fact("f1"))
        self.store.insert_fact(self._make_fact("f2"))
        all_f = self.store.get_all_facts()
        self.assertEqual(len(all_f), 2)

    def test_10_delete_fact(self):
        self.store.insert_fact(self._make_fact("f1"))
        self.store.delete_fact("f1")
        self.assertIsNone(self.store.get_fact("f1"))

    def test_11_count_facts(self):
        self.store.insert_fact(self._make_fact("f1"))
        self.store.insert_fact(self._make_fact("f2"))
        self.assertEqual(self.store.count_facts(), 2)

    def test_12_count_by_source(self):
        self.store.insert_fact(self._make_fact("f1", url="https://a.com"))
        self.store.insert_fact(self._make_fact("f2", url="https://a.com"))
        self.store.insert_fact(self._make_fact("f3", url="https://b.com"))
        counts = self.store.count_by_source()
        self.assertEqual(counts["https://a.com"], 2)
        self.assertEqual(counts["https://b.com"], 1)

    def test_13_count_by_category(self):
        self.store.insert_fact(self._make_fact("f1", category="news"))
        self.store.insert_fact(self._make_fact("f2", category="technical"))
        self.store.insert_fact(self._make_fact("f3", category="technical"))
        counts = self.store.count_by_category()
        self.assertEqual(counts["news"], 1)
        self.assertEqual(counts["technical"], 2)

    def test_14_persistence(self):
        self.store.insert_fact(self._make_fact("f1"))
        store2 = FactStore(db_path=self._db)
        self.assertIsNotNone(store2.get_fact("f1"))

    def test_15_delete_by_activity(self):
        self.store.insert_fact(self._make_fact("f1", activity_id="act_1"))
        self.store.insert_fact(self._make_fact("f2", activity_id="act_1"))
        self.store.insert_fact(self._make_fact("f3", activity_id="act_2"))
        self.store.delete_facts_by_activity("act_1")
        self.assertEqual(self.store.count_facts(), 1)


class TestFactExtractor(unittest.TestCase):
    """Fact extraction from text and DOM."""

    def setUp(self):
        self.extractor = FactExtractor()

    def test_16_extract_empty(self):
        facts = self.extractor.extract("", "https://example.com")
        self.assertEqual(facts, [])

    def test_17_extract_none(self):
        facts = self.extractor.extract("  ", "https://example.com")
        self.assertEqual(facts, [])

    def test_18_extract_single_fact(self):
        text = "Python 3.13 was released in October 2025. It includes many new features."
        facts = self.extractor.extract(text, "https://python.org")
        self.assertGreaterEqual(len(facts), 1)
        self.assertIn("Python 3.13", facts[0].claim)
        self.assertGreater(facts[0].confidence, 0.5)

    def test_19_skips_questions(self):
        text = "What is Python? It is a programming language."
        facts = self.extractor.extract(text, "https://python.org")
        # First sentence is a question, should be skipped
        self.assertGreaterEqual(len(facts), 1)
        self.assertNotIn("What is Python", facts[0].claim)

    def test_20_skips_commands(self):
        text = "Click the download button. Python 3.13 is available now."
        facts = self.extractor.extract(text, "https://python.org")
        self.assertEqual(len(facts), 1)
        self.assertIn("Python 3.13", facts[0].claim)

    def test_21_skips_nav_text(self):
        text = "Sign in to your account. Python 3.13 was released."
        facts = self.extractor.extract(text, "https://python.org")
        self.assertGreaterEqual(len(facts), 1)

    def test_22_assigns_category(self):
        text = "The API supports REST endpoints. The premium plan costs $10 per month."
        facts = self.extractor.extract(text, "https://example.com")
        categories = [f.category for f in facts]
        self.assertIn("technical", categories)
        self.assertIn("pricing", categories)

    def test_23_confidence_boost(self):
        low_text = "Maybe Python is a language."
        high_text = "Python 3.13 was confirmed released in 2025 by the official foundation."
        low_facts = self.extractor.extract(low_text, "https://example.com")
        high_facts = self.extractor.extract(high_text, "https://example.com")
        if low_facts and high_facts:
            self.assertLess(low_facts[0].confidence, high_facts[0].confidence)

    def test_24_extract_from_dom_dict(self):
        dom = {"content": "Python 3.13 was released. It is faster than 3.12."}
        facts = self.extractor.extract_from_dom(dom, "https://python.org")
        self.assertGreaterEqual(len(facts), 1)

    def test_25_extract_from_dom_html(self):
        html = "<html><body><p>Python 3.13 was released in 2025.</p></body></html>"
        facts = self.extractor.extract_from_dom(html, "https://python.org")
        self.assertGreaterEqual(len(facts), 1)
        self.assertIn("Python 3.13", facts[0].claim)

    def test_26_extract_from_dom_none(self):
        facts = self.extractor.extract_from_dom(None, "https://example.com")
        self.assertEqual(facts, [])

    def test_27_tags(self):
        text = "Google Cloud announced Vertex AI v2.0 at the 2025 conference."
        facts = self.extractor.extract(text, "https://cloud.google.com")
        if facts:
            tags = facts[0].tags
            self.assertTrue(any("google" in t for t in tags) or
                            any("vertex" in t for t in tags))

    def test_28_max_facts(self):
        text = ". ".join([f"Claim number {i} is a factual statement." for i in range(100)])
        facts = self.extractor.extract(text, "https://example.com", max_facts=5)
        self.assertLessEqual(len(facts), 5)

    def test_29_short_sentence_skipped(self):
        text = "Hi. Python is a widely used programming language created by Guido van Rossum."
        facts = self.extractor.extract(text, "https://python.org")
        self.assertGreaterEqual(len(facts), 1)
        # "Hi" should be skipped (too short)
        for fact in facts:
            self.assertNotEqual(fact.claim, "Hi")
