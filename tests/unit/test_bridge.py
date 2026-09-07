"""Unit tests for the ExtractedFact→Fact bridge."""
import json
import tempfile

import pytest

from core.fact_extraction.models import ExtractedFact
from core.fact_extraction.bridge import to_research_fact, bridge_batch


class TestBridge:
    def test_converts_basic_fields(self):
        ef = ExtractedFact(
            fact_id="fact_abc",
            entity="Python",
            claim="Python 3.14 was released in 2026",
            source_url="https://python.org",
            source_type="heading",
            category="technical",
            confidence=0.9,
        )
        f = to_research_fact(ef)
        assert f.fact_id == "fact_abc"
        assert f.source_url == "https://python.org"
        assert f.claim == "Python 3.14 was released in 2026"
        assert f.confidence == 0.9
        assert f.category == "technical"

    def test_preserves_tags(self):
        ef = ExtractedFact(
            fact_id="fact_xyz",
            entity="Django",
            claim="Django 5.0 supports async",
            source_url="https://djangoproject.com",
            source_type="paragraph",
            category="technical",
            confidence=0.85,
            tags=["Django", "5.0"],
        )
        f = to_research_fact(ef)
        assert f.tags == ["Django", "5.0"]

    def test_metadata_contains_entity_and_source_type(self):
        ef = ExtractedFact(
            fact_id="fact_123",
            entity="TypeScript",
            claim="TypeScript 5.5 improves type inference",
            source_url="https://typescriptlang.org",
            source_type="paragraph",
            category="technical",
            confidence=0.8,
        )
        f = to_research_fact(ef)
        assert f.metadata["entity"] == "TypeScript"
        assert f.metadata["source_type"] == "paragraph"

    def test_activity_id_and_node_id(self):
        ef = ExtractedFact(
            fact_id="fact_456",
            entity="Rust",
            claim="Rust 1.80 is stable",
            source_url="https://rust-lang.org",
            source_type="heading",
            category="technical",
            confidence=0.9,
        )
        f = to_research_fact(ef, activity_id="act_001", node_id="node_002")
        assert f.activity_id == "act_001"
        assert f.node_id == "node_002"

    def test_attributes_are_passed_to_metadata(self):
        ef = ExtractedFact(
            fact_id="fact_789",
            entity="AWS",
            claim="AWS Lambda costs $0.20 per million requests",
            source_url="https://aws.amazon.com",
            source_type="table",
            category="pricing",
            confidence=0.85,
            attributes={"price": "$0.20", "unit": "per million requests"},
        )
        f = to_research_fact(ef)
        assert f.metadata["attributes"]["price"] == "$0.20"

    def test_bridge_batch(self):
        facts = [
            ExtractedFact(
                fact_id=str(i),
                entity=f"Entity{i}",
                claim=f"Claim {i}",
                source_url="https://example.com",
                source_type="paragraph",
                category="general",
                confidence=0.5,
            )
            for i in range(3)
        ]
        result = bridge_batch(facts, activity_id="act_batch")
        assert len(result) == 3
        assert all(r.activity_id == "act_batch" for r in result)
        assert [r.fact_id for r in result] == ["0", "1", "2"]

    def test_empty_batch(self):
        assert bridge_batch([]) == []

    def test_handles_missing_extracted_at(self):
        ef = ExtractedFact(
            fact_id="f1",
            entity="AI",
            claim="AI is evolving",
            source_url="https://ai.com",
            source_type="paragraph",
            category="general",
            confidence=0.7,
            extracted_at=None,
        )
        f = to_research_fact(ef)
        assert f.timestamp is not None
