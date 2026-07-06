from __future__ import annotations

import time

import pytest

from memory.reranker import ReRanker


@pytest.fixture
def reranker() -> ReRanker:
    return ReRanker()


# ═══════════════════════════════════════════════════════════════════════════════
# 1.  Similarity scoring
# ═══════════════════════════════════════════════════════════════════════════════


def test_rerank_orders_by_similarity(reranker):
    items = [
        {"text": "The user likes Python programming.", "id": "1"},
        {"text": "The weather is nice today.", "id": "2"},
        {"text": "Python is a great language.", "id": "3"},
    ]
    result = reranker.rerank("Python", items)
    assert result[0]["id"] in ("1", "3")  # Python-related items first
    assert result[-1]["id"] == "2"  # weather last


def test_rerank_empty_items(reranker):
    assert reranker.rerank("query", []) == []


def test_rerank_no_match(reranker):
    items = [{"text": "nothing relevant here"}]
    result = reranker.rerank("quantum physics", items)
    assert len(result) == 1


# ═══════════════════════════════════════════════════════════════════════════════
# 2.  Recency scoring
# ═══════════════════════════════════════════════════════════════════════════════


def test_rerank_recency_boost(reranker):
    now = time.time()
    recent_hour = now - 3600
    old_week = now - 7 * 86400
    items = [
        {"text": "old item", "id": "old", "timestamp": old_week},
        {"text": "recent item", "id": "recent", "timestamp": recent_hour},
    ]
    result = reranker.rerank("item", items)
    assert result[0]["id"] == "recent"


def test_rerank_different_timestamp_keys(reranker):
    now = time.time()
    items = [
        {"text": "created", "created_at": now - 100},
        {"text": "updated", "updated_at": now - 50},
    ]
    result = reranker.rerank("test", items)
    assert len(result) == 2


# ═══════════════════════════════════════════════════════════════════════════════
# 3.  Confidence scoring
# ═══════════════════════════════════════════════════════════════════════════════


def test_rerank_confidence_boost(reranker):
    items = [
        {"text": "low confidence", "confidence": 0.3},
        {"text": "high confidence", "confidence": 0.9},
    ]
    result = reranker.rerank("confidence", items)
    assert result[0]["confidence"] == 0.9


# ═══════════════════════════════════════════════════════════════════════════════
# 4.  Preference boost
# ═══════════════════════════════════════════════════════════════════════════════


def test_rerank_preference_boost(reranker):
    items = [
        {"text": "I enjoy coding in Python", "id": "python"},
        {"text": "I enjoy coding in Java", "id": "java"},
    ]
    prefs = {"language": "Python"}
    result = reranker.rerank("coding", items, user_preferences=prefs)
    assert result[0]["id"] == "python"


def test_rerank_preference_no_effect_when_no_match(reranker):
    items = [
        {"text": "some random text", "id": "a"},
        {"text": "more random text", "id": "b"},
    ]
    prefs = {"editor": "VS Code"}
    result = reranker.rerank("text", items, user_preferences=prefs)
    assert len(result) == 2  # no boost applied


def test_rerank_preference_empty_prefs(reranker):
    items = [{"text": "Python is great"}]
    result = reranker.rerank("Python", items, user_preferences={})
    assert len(result) == 1


# ═══════════════════════════════════════════════════════════════════════════════
# 5.  Score metadata
# ═══════════════════════════════════════════════════════════════════════════════


def test_rerank_adds_score_key(reranker):
    items = [{"text": "hello world"}]
    result = reranker.rerank("hello", items)
    assert "_score" in result[0]
    assert isinstance(result[0]["_score"], float)


def test_rerank_score_increases_with_more_matches(reranker):
    items = [
        {"text": "single"},
        {"text": "multiple word match here"},
    ]
    result = reranker.rerank("multiple word match", items)
    assert result[0]["_score"] > result[1]["_score"]
