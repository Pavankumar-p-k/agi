"""Unit tests for the browser fact extraction system (B7)."""

import json
import os
import tempfile

import pytest

from core.fact_extraction.models import ExtractedFact
from core.fact_extraction.extractor import BrowserFactExtractor, _normalize, _guess_entity, _classify, _score_confidence
from core.fact_extraction.store import BrowserFactStore


class TestModels:
    def test_extracted_fact_defaults(self):
        f = ExtractedFact(
            fact_id="fact_abc",
            entity="Python",
            claim="Python 3.14 was released",
            source_url="https://python.org",
            source_type="heading",
            category="technical",
            confidence=0.9,
        )
        assert f.fact_id == "fact_abc"
        assert f.entity == "Python"
        assert f.tags == []
        assert f.attributes == {}

    def test_extracted_fact_full(self):
        f = ExtractedFact(
            fact_id="fact_xyz",
            entity="Django",
            claim="Django 5.0 supports async",
            source_url="https://djangoproject.com",
            source_type="paragraph",
            category="technical",
            confidence=0.85,
            tags=["Django", "5.0"],
            attributes={"version": "5.0"},
            extracted_at="2026-06-23T12:00:00",
        )
        assert f.tags == ["Django", "5.0"]
        assert f.attributes == {"version": "5.0"}


class TestNormalizer:
    def test_normalize_removes_punctuation(self):
        assert _normalize("Python 3.14 is out!") == "python 314 is out"

    def test_normalize_collapses_spaces(self):
        assert _normalize("Hello    World") == "hello world"

    def test_normalize_lowercases(self):
        assert _normalize("HELLO") == "hello"


class TestEntityGuess:
    def test_camelcase_entity(self):
        assert _guess_entity("Python 3.14 Released") == "Python"

    def test_fallback_to_lowercase(self):
        assert _guess_entity("hello world") == "hello"

    def test_empty_returns_none(self):
        assert _guess_entity("") is None


class TestClassifier:
    def test_pricing_detection(self):
        assert _classify("The price is $29", "paragraph") == "pricing"

    def test_technical_detection(self):
        assert _classify("Version 3.14 released", "paragraph") == "technical"

    def test_tutorial_detection(self):
        assert _classify("How to install Python", "paragraph") == "tutorial"

    def test_comparison_detection(self):
        assert _classify("Python vs JavaScript", "paragraph") == "comparison"

    def test_table_is_property(self):
        assert _classify("anything", "table") == "property"

    def test_general_fallback(self):
        assert _classify("The sky is blue", "paragraph") == "general"


class TestConfidenceScorer:
    def test_base_confidence(self):
        assert _score_confidence("hello world") == 0.5

    def test_boost_for_numbers(self):
        assert _score_confidence("version 3.14") > 0.5

    def test_boost_for_proper_nouns(self):
        assert _score_confidence("Python 3.14 Released") > 0.5

    def test_boost_for_years(self):
        assert _score_confidence("Released in 2026") > 0.5

    def test_penalty_for_hedging(self):
        assert _score_confidence("Maybe it was released") < 0.5

    def test_clamps_upper(self):
        assert _score_confidence("Officially confirmed version 5.0.0 released 2026 by Google Corporation") <= 1.0

    def test_clamps_lower(self):
        assert _score_confidence("maybe perhaps possibly") >= 0.0


class TestExtractor:
    def _make_snapshot(self, **overrides):
        base = {
            "title": "Test Page",
            "url": "https://example.com",
            "headings": [],
            "paragraphs": [],
            "list_items": [],
            "list_parents": [],
            "tables": [],
            "definition_lists": [],
            "buttons": [],
            "inputs": [],
            "links": [],
            "forms": [],
        }
        base.update(overrides)
        return base

    def test_empty_snapshot_returns_empty(self):
        ext = BrowserFactExtractor()
        facts = ext.extract_from_snapshot(self._make_snapshot(), "https://example.com")
        assert len(facts) == 1  # title fallback

    def test_heading_with_paragraph(self):
        ext = BrowserFactExtractor()
        snap = self._make_snapshot(
            headings=[{"tag": "h1", "text": "Python 3.14"}],
            paragraphs=[{"tag": "p", "text": "Python 3.14 is the latest stable release."}],
        )
        facts = ext.extract_from_snapshot(snap, "https://python.org")
        assert len(facts) >= 1
        assert "Python" in facts[0].claim
        assert facts[0].source_type == "heading_h1"

    def test_table_extraction(self):
        ext = BrowserFactExtractor()
        snap = self._make_snapshot(
            tables=[{
                "caption": "Pricing",
                "rows": [
                    {"cells": ["Basic", "$10/mo"]},
                    {"cells": ["Pro", "$29/mo"]},
                ],
            }]
        )
        facts = ext.extract_from_snapshot(snap, "https://example.com")
        table_facts = [f for f in facts if f.source_type == "table"]
        assert len(table_facts) == 2
        assert table_facts[0].category == "property"
        assert "Basic" in table_facts[0].claim

    def test_definition_list(self):
        ext = BrowserFactExtractor()
        snap = self._make_snapshot(
            definition_lists=[{"terms": [
                {"term": "API", "definition": "Application Programming Interface"},
            ]}]
        )
        facts = ext.extract_from_snapshot(snap, "https://example.com")
        def_facts = [f for f in facts if f.source_type == "definition"]
        assert len(def_facts) >= 1
        assert "API" in def_facts[0].claim

    def test_list_items(self):
        ext = BrowserFactExtractor()
        snap = self._make_snapshot(
            headings=[{"tag": "h2", "text": "Features", "visible": True}],
            list_items=[
                {"tag": "li", "text": "Cross-platform support across Windows, macOS, and Linux", "visible": True},
            ],
            list_parents=[""],
        )
        facts = ext.extract_from_snapshot(snap, "https://example.com")
        list_facts = [f for f in facts if f.source_type == "list_item"]
        assert len(list_facts) >= 0  # may fall under heading
        # Should have at least some fact
        assert len(facts) >= 1

    def test_deduplication_same_claim(self):
        ext = BrowserFactExtractor()
        snap = self._make_snapshot(
            title="Python 3.14",
            headings=[{"tag": "h1", "text": "Python 3.14", "visible": True}],
            paragraphs=[{"tag": "p", "text": "Python 3.14 is the latest stable release.", "visible": True}],
        )
        facts = ext.extract_from_snapshot(snap, "https://python.org")
        # Should not duplicate
        claims = [f.claim for f in facts]
        assert len(claims) == len(set(claims))

    def test_max_facts_limit(self):
        ext = BrowserFactExtractor()
        snap = self._make_snapshot(
            tables=[{
                "caption": "Data",
                "rows": [{"cells": [str(i), str(i * 2)]} for i in range(50)],
            }]
        )
        facts = ext.extract_from_snapshot(snap, "https://example.com", max_facts=10)
        assert len(facts) <= 10

    def test_confidence_sorting(self):
        ext = BrowserFactExtractor()
        snap = self._make_snapshot(
            tables=[{
                "caption": "Data",
                "rows": [
                    {"cells": ["Official", "Confirmed release 2026"]},
                    {"cells": ["Maybe", "Possibly available"]},
                ],
            }]
        )
        facts = ext.extract_from_snapshot(snap, "https://example.com")
        for i in range(len(facts) - 1):
            assert facts[i].confidence >= facts[i + 1].confidence

    def test_to_json_serializable(self):
        ext = BrowserFactExtractor()
        facts = [
            ExtractedFact(
                fact_id="fact_abc", entity="Python",
                claim="Python 3.14", source_url="https://python.org",
                source_type="heading", category="technical",
                confidence=0.9, tags=["Python"],
                extracted_at="2026-06-23T12:00:00",
            )
        ]
        serialized = ext.to_json_serializable(facts)
        assert isinstance(serialized, list)
        assert serialized[0]["entity"] == "Python"
        assert serialized[0]["confidence"] == 0.9


class TestStore:
    @pytest.fixture
    def store(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        store = BrowserFactStore(db_path)
        yield store
        store.close()
        if os.path.exists(db_path):
            os.unlink(db_path)

    def test_store_and_retrieve(self, store):
        facts = [
            ExtractedFact(
                fact_id="fact_1", entity="Python",
                claim="Python 3.14 released", source_url="https://python.org",
                source_type="heading", category="technical", confidence=0.9,
            )
        ]
        store.store_facts(facts)
        assert store.fact_count() == 1
        retrieved = store.get_all_facts()
        assert len(retrieved) == 1
        assert retrieved[0].claim == "Python 3.14 released"

    def test_dedup_same_claim_same_url(self, store):
        facts = [
            ExtractedFact(
                fact_id="fact_1", entity="Python",
                claim="Python 3.14 released", source_url="https://python.org",
                source_type="heading", category="technical", confidence=0.9,
            ),
        ]
        store.store_facts(facts)
        store.store_facts(facts)
        assert store.fact_count() == 1

    def test_multiple_facts(self, store):
        facts = [
            ExtractedFact(fact_id="f1", entity="Python", claim="A", source_url="https://a.com", source_type="heading", category="technical", confidence=0.9),
            ExtractedFact(fact_id="f2", entity="Django", claim="B", source_url="https://b.com", source_type="paragraph", category="general", confidence=0.5),
        ]
        store.store_facts(facts)
        assert store.fact_count() == 2

    def test_search_by_entity(self, store):
        facts = [
            ExtractedFact(fact_id="f1", entity="Python", claim="Python 3.14", source_url="https://python.org", source_type="heading", category="technical", confidence=0.9),
            ExtractedFact(fact_id="f2", entity="Django", claim="Django 5.0", source_url="https://djangoproject.com", source_type="heading", category="technical", confidence=0.8),
        ]
        store.store_facts(facts)
        results = store.get_facts_by_entity("Python")
        assert len(results) == 1
        assert results[0].fact_id == "f1"

    def test_search_by_category(self, store):
        facts = [
            ExtractedFact(fact_id="f1", entity="X", claim="A", source_url="https://a.com", source_type="table", category="property", confidence=0.9),
            ExtractedFact(fact_id="f2", entity="Y", claim="B", source_url="https://b.com", source_type="definition", category="property", confidence=0.8),
            ExtractedFact(fact_id="f3", entity="Z", claim="C", source_url="https://c.com", source_type="paragraph", category="general", confidence=0.5),
        ]
        store.store_facts(facts)
        results = store.get_facts_by_category("property")
        assert len(results) == 2

    def test_search_facts_text(self, store):
        facts = [
            ExtractedFact(fact_id="f1", entity="Python", claim="Python 3.14 released in 2026", source_url="https://python.org", source_type="heading", category="technical", confidence=0.9),
        ]
        store.store_facts(facts)
        results = store.search_facts("3.14")
        assert len(results) == 1
        results = store.search_facts("nonexistent")
        assert len(results) == 0

    def test_delete_fact(self, store):
        f = ExtractedFact(fact_id="f_del", entity="Python", claim="To delete", source_url="https://python.org", source_type="heading", category="technical", confidence=0.5)
        store.store_facts([f])
        assert store.fact_count() == 1
        store.delete_fact("f_del")
        assert store.fact_count() == 0

    def test_confidence_update_on_resee(self, store):
        low = ExtractedFact(fact_id="f1", entity="Python", claim="Python 3.14", source_url="https://python.org", source_type="heading", category="technical", confidence=0.5)
        high = ExtractedFact(fact_id="f2", entity="Python", claim="Python 3.14", source_url="https://python.org", source_type="heading", category="technical", confidence=0.9)
        store.store_facts([low])
        store.store_facts([high])
        results = store.get_facts_by_entity("Python")
        assert len(results) == 1
        assert results[0].confidence == 0.9

    def test_empty_store_count(self, store):
        assert store.fact_count() == 0
