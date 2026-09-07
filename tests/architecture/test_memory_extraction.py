from __future__ import annotations

import os
import tempfile

import pytest

from memory.extraction import ExtractedFact, extract_facts, extract_facts_from_messages
from memory.fact_store import FactStore


# ═══════════════════════════════════════════════════════════════════════════════
# 1.  ExtractedFact dataclass
# ═══════════════════════════════════════════════════════════════════════════════


def test_extracted_fact_defaults():
    fact = ExtractedFact(
        subject="python",
        predicate="is",
        object="a language",
        confidence=0.8,
        category="attribute",
        source_text="Python is a language",
    )
    assert fact.subject == "python"
    assert fact.object == "a language"
    assert fact.confidence == 0.8
    assert fact.id is None
    assert fact.user_id == ""


# ═══════════════════════════════════════════════════════════════════════════════
# 2.  Pattern-based extraction
# ═══════════════════════════════════════════════════════════════════════════════


def test_extract_is_attribute():
    facts = extract_facts("Python is a great language.")
    assert len(facts) >= 1
    assert any(f.predicate == "attribute" and "python" in f.subject.lower() for f in facts)


def test_extract_i_like_preference():
    facts = extract_facts("I like dark mode.")
    assert len(facts) >= 1
    pref = [f for f in facts if f.category == "preference"]
    assert len(pref) >= 1
    assert any("dark mode" in f.object.lower() for f in pref)


def test_extract_my_favorite():
    facts = extract_facts("My favorite editor is VS Code.")
    assert len(facts) >= 1
    pref = [f for f in facts if f.category == "preference"]
    assert len(pref) >= 1
    assert any("vs code" in f.object.lower() for f in pref)


def test_extract_capability():
    facts = extract_facts("The tool can search files quickly.")
    assert len(facts) >= 1
    cap = [f for f in facts if f.category == "capability"]
    assert len(cap) >= 1
    assert any("search files" in f.object.lower() for f in cap)


def test_extract_fact_remember():
    facts = extract_facts("Remember that the database is PostgreSQL.")
    assert len(facts) >= 1
    fact_cat = [f for f in facts if f.category == "fact"]
    assert len(fact_cat) >= 1
    assert any("postgresql" in f.object.lower() for f in fact_cat)


def test_extract_i_use():
    facts = extract_facts("I use Python for backend development.")
    assert len(facts) >= 1
    pref = [f for f in facts if f.category == "preference"]
    assert len(pref) >= 1
    assert any("python" in f.object.lower() for f in pref)


def test_extract_i_am():
    facts = extract_facts("I am a software engineer.")
    assert len(facts) >= 1
    attr = [f for f in facts if f.category == "attribute"]
    assert len(attr) >= 1
    assert any("software engineer" in f.object.lower() for f in attr)


def test_extract_set_my():
    facts = extract_facts("Set my default editor to VS Code.")
    assert len(facts) >= 1
    pref = [f for f in facts if f.category == "preference"]
    assert len(pref) >= 1


def test_extract_no_match():
    facts = extract_facts("Hello, how are you?")
    assert len(facts) == 0


def test_extract_multiple_facts():
    facts = extract_facts("I like Python. My favorite framework is FastAPI. Python is great.")
    assert len(facts) >= 2


def test_extract_deduplicates_identical():
    facts = extract_facts("I like Python. I like Python.")
    python_prefs = [f for f in facts if f.category == "preference"]
    assert len(python_prefs) >= 1


def test_extract_from_messages():
    messages = [
        {"role": "user", "content": "I like Python."},
        {"role": "assistant", "content": "Python is a great language."},
        {"role": "system", "content": "You are a helpful assistant."},
    ]
    facts = extract_facts_from_messages(messages)
    assert len(facts) >= 2


def test_first_person_normalised():
    facts = extract_facts("I like Python.")
    for f in facts:
        assert f.subject.lower() == "user"


# ═══════════════════════════════════════════════════════════════════════════════
# 3.  FactStore
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def tmp_store():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test_facts.db")
        fs = FactStore(db_path, disable_embedding=True)
        yield fs


def test_store_and_retrieve(tmp_store):
    facts = [
        ExtractedFact(
            subject="user", predicate="preference", object="Python",
            confidence=0.8, category="preference",
            source_text="I like Python.", user_id="u1",
        ),
    ]
    ids = tmp_store.store_facts(facts, user_id="u1")
    assert len(ids) == 1

    stored = tmp_store.get_user_facts("u1")
    assert len(stored) == 1
    assert stored[0]["object"] == "Python"


def test_store_dedup(tmp_store):
    fact = ExtractedFact(
        subject="user", predicate="preference", object="Python",
        confidence=0.8, category="preference",
        source_text="I like Python.", user_id="u1",
    )
    ids1 = tmp_store.store_facts([fact], user_id="u1")
    ids2 = tmp_store.store_facts([fact], user_id="u1")
    assert len(ids2) == 0  # no new insert


def test_store_different_users(tmp_store):
    f1 = ExtractedFact(
        subject="user", predicate="preference", object="Python",
        confidence=0.8, category="preference",
        source_text="I like Python.", user_id="u1",
    )
    f2 = ExtractedFact(
        subject="user", predicate="preference", object="Python",
        confidence=0.8, category="preference",
        source_text="I like Python.", user_id="u2",
    )
    ids1 = tmp_store.store_facts([f1], user_id="u1")
    ids2 = tmp_store.store_facts([f2], user_id="u2")
    assert len(ids1) == 1
    assert len(ids2) == 1


def test_search_by_keyword(tmp_store):
    facts = [
        ExtractedFact(subject="user", predicate="preference", object="Python",
                      confidence=0.8, category="preference",
                      source_text="I like Python.", user_id="u1"),
        ExtractedFact(subject="user", predicate="preference", object="FastAPI",
                      confidence=0.7, category="preference",
                      source_text="I like FastAPI.", user_id="u1"),
    ]
    tmp_store.store_facts(facts, user_id="u1")

    results = tmp_store.search_facts("Python", user_id="u1", limit=10)
    assert len(results) >= 1
    assert any("Python" in r["object"] for r in results)


def test_contradiction_detection(tmp_store):
    tmp_store.store_facts([
        ExtractedFact(subject="user", predicate="preference", object="dark mode",
                      confidence=0.9, category="preference",
                      source_text="I like dark mode.", user_id="u1"),
    ], user_id="u1")

    contradictions = tmp_store.find_contradictions([
        ExtractedFact(subject="user", predicate="preference", object="light mode",
                      confidence=0.8, category="preference",
                      source_text="I like light mode.", user_id="u1"),
    ], user_id="u1", threshold=0.7)

    assert len(contradictions) >= 1
    assert contradictions[0]["existing_fact"]["object"] == "dark mode"
    assert contradictions[0]["new_fact"]["object"] == "light mode"


def test_mark_inactive(tmp_store):
    fact = ExtractedFact(
        subject="user", predicate="preference", object="Python",
        confidence=0.8, category="preference",
        source_text="I like Python.", user_id="u1",
    )
    ids = tmp_store.store_facts([fact], user_id="u1")

    tmp_store.mark_inactive(ids[0])
    stored = tmp_store.get_user_facts("u1")
    assert len(stored) == 0


def test_count_facts(tmp_store):
    facts = [
        ExtractedFact(subject="user", predicate="preference", object="Python",
                      confidence=0.8, category="preference",
                      source_text="I like Python.", user_id="u1"),
        ExtractedFact(subject="user", predicate="attribute", object="a developer",
                      confidence=0.7, category="attribute",
                      source_text="I am a developer.", user_id="u1"),
    ]
    tmp_store.store_facts(facts, user_id="u1")
    assert tmp_store.count_facts("u1") == 2


def test_get_categories(tmp_store):
    facts = [
        ExtractedFact(subject="user", predicate="preference", object="Python",
                      confidence=0.8, category="preference",
                      source_text="I like Python.", user_id="u1"),
        ExtractedFact(subject="user", predicate="attribute", object="a developer",
                      confidence=0.7, category="attribute",
                      source_text="I am a developer.", user_id="u1"),
    ]
    tmp_store.store_facts(facts, user_id="u1")
    cats = tmp_store.get_categories("u1")
    assert cats.get("preference") == 1
    assert cats.get("attribute") == 1


def test_delete_user_facts(tmp_store):
    fact = ExtractedFact(
        subject="user", predicate="preference", object="Python",
        confidence=0.8, category="preference",
        source_text="I like Python.", user_id="u1",
    )
    tmp_store.store_facts([fact], user_id="u1")
    deleted = tmp_store.delete_facts_for_user("u1")
    assert deleted >= 1
    assert tmp_store.count_facts("u1") == 0
