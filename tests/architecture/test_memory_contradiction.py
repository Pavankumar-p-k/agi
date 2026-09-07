from __future__ import annotations

import os
import tempfile

import pytest

from memory.extraction import ExtractedFact, extract_facts
from memory.fact_store import FactStore


@pytest.fixture
def tmp_store():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test_facts.db")
        fs = FactStore(db_path, disable_embedding=True)
        yield fs


# ═══════════════════════════════════════════════════════════════════════════════
# 1.  Contradiction detection
# ═══════════════════════════════════════════════════════════════════════════════


def test_contradiction_same_subject_predicate_different_object(tmp_store):
    tmp_store.store_facts([
        ExtractedFact(subject="user", predicate="preference", object="dark mode",
                      confidence=0.9, category="preference",
                      source_text="I like dark mode.", user_id="u1"),
    ], user_id="u1")

    contradictions = tmp_store.find_contradictions([
        ExtractedFact(subject="user", predicate="preference", object="light mode",
                      confidence=0.8, category="preference",
                      source_text="I like light mode.", user_id="u1"),
    ], user_id="u1", threshold=0.6)

    assert len(contradictions) == 1
    assert contradictions[0]["existing_fact"]["object"] == "dark mode"
    assert contradictions[0]["new_fact"]["object"] == "light mode"


def test_contradiction_no_match_when_same_object(tmp_store):
    tmp_store.store_facts([
        ExtractedFact(subject="user", predicate="preference", object="dark mode",
                      confidence=0.9, category="preference",
                      source_text="I like dark mode.", user_id="u1"),
    ], user_id="u1")

    contradictions = tmp_store.find_contradictions([
        ExtractedFact(subject="user", predicate="preference", object="dark mode",
                      confidence=0.8, category="preference",
                      source_text="I prefer dark mode.", user_id="u1"),
    ], user_id="u1", threshold=0.6)

    assert len(contradictions) == 0  # same object → not a contradiction


def test_contradiction_below_threshold(tmp_store):
    tmp_store.store_facts([
        ExtractedFact(subject="user", predicate="preference", object="dark mode",
                      confidence=0.3, category="preference",
                      source_text="I like dark mode.", user_id="u1"),
    ], user_id="u1")

    contradictions = tmp_store.find_contradictions([
        ExtractedFact(subject="user", predicate="preference", object="light mode",
                      confidence=0.8, category="preference",
                      source_text="I like light mode.", user_id="u1"),
    ], user_id="u1", threshold=0.6)

    assert len(contradictions) == 0  # existing fact confidence below threshold


def test_contradiction_different_user_no_match(tmp_store):
    tmp_store.store_facts([
        ExtractedFact(subject="user", predicate="preference", object="dark mode",
                      confidence=0.9, category="preference",
                      source_text="I like dark mode.", user_id="u1"),
    ], user_id="u1")

    contradictions = tmp_store.find_contradictions([
        ExtractedFact(subject="user", predicate="preference", object="light mode",
                      confidence=0.8, category="preference",
                      source_text="I like light mode.", user_id="u2"),
    ], user_id="u2", threshold=0.6)

    assert len(contradictions) == 0  # different user


def test_contradiction_multiple_matches(tmp_store):
    tmp_store.store_facts([
        ExtractedFact(subject="user", predicate="preference", object="dark mode",
                      confidence=0.9, category="preference",
                      source_text="I like dark mode.", user_id="u1"),
    ], user_id="u1")

    contradictions = tmp_store.find_contradictions([
        ExtractedFact(subject="user", predicate="preference", object="light mode",
                      confidence=0.8, category="preference",
                      source_text="I like light mode.", user_id="u1"),
    ], user_id="u1", threshold=0.6)

    assert len(contradictions) == 1


# ═══════════════════════════════════════════════════════════════════════════════
# 2.  Consolidation (word overlap merge)
# ═══════════════════════════════════════════════════════════════════════════════


def test_consolidate_identical_objects(tmp_store):
    tmp_store.store_facts([
        ExtractedFact(subject="user", predicate="preference", object="Python",
                      confidence=0.8, category="preference",
                      source_text="I like Python.", user_id="u1"),
        ExtractedFact(subject="user", predicate="preference", object="Python",
                      confidence=0.7, category="preference",
                      source_text="Python is great.", user_id="u1"),
    ], user_id="u1", force=True)

    deactivated = tmp_store.consolidate(user_id="u1", min_similarity=0.5)
    assert deactivated == 1

    remaining = tmp_store.get_user_facts("u1")
    assert len(remaining) == 1
    assert remaining[0]["confidence"] == 0.8


def test_consolidate_similar_objects(tmp_store):
    tmp_store.store_facts([
        ExtractedFact(subject="user", predicate="preference", object="Python programming",
                      confidence=0.8, category="preference",
                      source_text="I like Python programming.", user_id="u1"),
        ExtractedFact(subject="user", predicate="preference", object="Python language",
                      confidence=0.7, category="preference",
                      source_text="I like Python language.", user_id="u1"),
    ], user_id="u1", force=True)

    deactivated = tmp_store.consolidate(user_id="u1", min_similarity=0.3)
    assert deactivated == 1


def test_consolidate_different_objects_not_merged(tmp_store):
    tmp_store.store_facts([
        ExtractedFact(subject="user", predicate="preference", object="Python",
                      confidence=0.8, category="preference",
                      source_text="I like Python.", user_id="u1"),
        ExtractedFact(subject="user", predicate="preference", object="JavaScript",
                      confidence=0.7, category="preference",
                      source_text="I like JavaScript.", user_id="u1"),
    ], user_id="u1", force=True)

    deactivated = tmp_store.consolidate(user_id="u1", min_similarity=0.5)
    assert deactivated == 0  # no common words → not merged

    remaining = tmp_store.get_user_facts("u1")
    assert len(remaining) == 2


def test_consolidate_different_subject_not_merged(tmp_store):
    tmp_store.store_facts([
        ExtractedFact(subject="user", predicate="preference", object="Python",
                      confidence=0.8, category="preference",
                      source_text="I like Python.", user_id="u1"),
        ExtractedFact(subject="assistant", predicate="preference", object="Python",
                      confidence=0.7, category="preference",
                      source_text="The assistant likes Python.", user_id="u1"),
    ], user_id="u1", force=True)

    deactivated = tmp_store.consolidate(user_id="u1", min_similarity=0.5)
    assert deactivated == 0  # different subjects


def test_consolidate_different_predicate_not_merged(tmp_store):
    tmp_store.store_facts([
        ExtractedFact(subject="user", predicate="preference", object="Python",
                      confidence=0.8, category="preference",
                      source_text="I like Python.", user_id="u1"),
        ExtractedFact(subject="user", predicate="attribute", object="Python programmer",
                      confidence=0.7, category="attribute",
                      source_text="I am a Python programmer.", user_id="u1"),
    ], user_id="u1", force=True)

    deactivated = tmp_store.consolidate(user_id="u1", min_similarity=0.5)
    assert deactivated == 0  # different predicates


# ═══════════════════════════════════════════════════════════════════════════════
# 3.  Store force mode
# ═══════════════════════════════════════════════════════════════════════════════


def test_store_force_skips_dedup(tmp_store):
    fact = ExtractedFact(subject="user", predicate="preference", object="Python",
                         confidence=0.8, category="preference",
                         source_text="I like Python.", user_id="u1")

    # Normal store — dedup
    ids1 = tmp_store.store_facts([fact], user_id="u1")
    ids2 = tmp_store.store_facts([fact], user_id="u1")
    assert len(ids2) == 0  # deduplicated

    # Force store — skips dedup
    ids3 = tmp_store.store_facts([fact], user_id="u1", force=True)
    assert len(ids3) == 1  # inserted despite identical content


def test_store_force_with_contradictions(tmp_store):
    """Contradictory facts can both be stored with force=True."""
    tmp_store.store_facts([
        ExtractedFact(subject="user", predicate="preference", object="dark mode",
                      confidence=0.9, category="preference",
                      source_text="I like dark mode.", user_id="u1"),
    ], user_id="u1")

    # force store a contradictory fact
    ids = tmp_store.store_facts([
        ExtractedFact(subject="user", predicate="preference", object="light mode",
                      confidence=0.8, category="preference",
                      source_text="I like light mode.", user_id="u1"),
    ], user_id="u1", force=True)

    assert len(ids) == 1

    all_facts = tmp_store.get_user_facts("u1")
    assert len(all_facts) == 2
