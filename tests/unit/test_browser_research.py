"""Unit tests for the multi-page browser research tool."""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.tools.browser_research import (
    _create_plan,
    _extract_result_links,
    _get_follow_up_queries,
    _get_queries,
    _pick_search_engine,
    _synthesize_report,
    do_browser_research,
)


class TestHelpers:
    def test_pick_search_engine(self):
        url = _pick_search_engine("python 3.14")
        assert url == "https://www.google.com"

    def test_extract_result_links_empty(self):
        assert _extract_result_links({}) == []

    def test_extract_result_links_nested(self):
        snap = {"result": {"links": [{"href": "https://a.com"}, {"href": "https://b.com"}]}}
        links = _extract_result_links(snap)
        assert len(links) == 2
        assert links[0]["href"] == "https://a.com"

    def test_extract_result_links_flat(self):
        snap = {"links": [{"href": "https://c.com", "text": "Example"}]}
        links = _extract_result_links(snap)
        assert len(links) == 1
        assert links[0]["text"] == "Example"

    def test_extract_result_links_filters_nondict(self):
        snap = {"result": {"links": [{"href": "https://a.com"}, "nope", None]}}
        links = _extract_result_links(snap)
        assert len(links) == 1

    def test_get_queries_from_plan_object(self):
        plan = MagicMock()
        plan.question = "Test question?"
        sq = MagicMock()
        sq.query = "test query"
        goal = MagicMock()
        goal.search_queries = [sq]
        plan.goals = [goal]
        queries = _get_queries(plan)
        assert queries == ["test query"]

    def test_get_queries_fallback(self):
        plan = MagicMock()
        plan.question = "Fallback question?"
        plan.goals = []
        queries = _get_queries(plan)
        assert queries == ["Fallback question?"]

    def test_get_queries_none(self):
        assert _get_queries(None) == []

    def test_get_queries_dict_queries(self):
        plan = MagicMock()
        sq = {"query": "dict query"}
        goal = MagicMock()
        goal.search_queries = [sq]
        plan.goals = [goal]
        plan.question = "?"
        queries = _get_queries(plan)
        assert queries == ["dict query"]

    def test_create_plan_returns_plan(self):
        plan = _create_plan("test")
        assert plan is not None
        assert hasattr(plan, "question")
        assert plan.question == "test"


class TestFollowUpGaps:
    def test_get_follow_up_queries_no_plan(self):
        assert _get_follow_up_queries(None, []) == []

    def test_get_follow_up_queries_empty_facts(self):
        plan = MagicMock()
        plan.question = "?"
        plan.goals = []
        queries = _get_follow_up_queries(plan, [])
        assert queries == []


class TestSynthesizeReport:
    def test_no_facts_returns_fallback(self):
        report = _synthesize_report("test question", [], [])
        assert report["total_facts"] == 0
        assert "No facts" in report["summary"]
        assert "test question" in report["question"]

    def test_with_facts_returns_basic_report(self):
        facts = [
            {"fact_id": "f1", "source_url": "https://a.com", "claim": "Claim 1",
             "confidence": 0.8, "category": "technical", "tags": ["python"],
             "entity": "Python", "source_type": "paragraph", "attributes": {}},
        ]
        sources = ["https://a.com"]
        report = _synthesize_report("test", facts, sources)
        assert report["total_facts"] == 1
        assert report["question"] == "test"
        assert "https://a.com" in report["sources_consulted"]

    def test_deduplicates_sources(self):
        facts = [
            {"fact_id": "f1", "source_url": "https://a.com", "claim": "C1",
             "confidence": 0.5, "category": "general", "tags": [],
             "entity": "E", "source_type": "p", "attributes": {}},
            {"fact_id": "f2", "source_url": "https://a.com", "claim": "C2",
             "confidence": 0.5, "category": "general", "tags": [],
             "entity": "E", "source_type": "p", "attributes": {}},
        ]
        sources = ["https://a.com", "https://a.com"]
        report = _synthesize_report("q", facts, sources)
        assert len(report["sources_consulted"]) == 1

    def test_includes_recommendations_when_empty(self):
        report = _synthesize_report("q", [], [])
        assert len(report["recommendations"]) > 0

    def test_recommendations_when_facts(self):
        facts = [
            {"fact_id": "f1", "source_url": "https://a.com", "claim": "C1",
             "confidence": 0.5, "category": "general", "tags": [],
             "entity": "E", "source_type": "p", "attributes": {}},
        ]
        report = _synthesize_report("q", facts, ["https://a.com"])
        assert isinstance(report["recommendations"], list)


class TestDoBrowserResearch:
    @pytest.mark.asyncio
    async def test_no_facts_when_no_pages(self):
        report = await do_browser_research(
            question="test question",
            max_pages=0,
        )
        assert report["question"] == "test question"
        assert report["total_facts"] == 0

    @pytest.mark.asyncio
    async def test_returns_report_dict(self):
        report = await do_browser_research(
            question="what is python",
            max_pages=1,
        )
        assert isinstance(report, dict)
        assert "question" in report
        assert "sources_consulted" in report
        assert "total_facts" in report
        assert "summary" in report
