from __future__ import annotations

import os
import tempfile

import pytest

from memory.extraction import ExtractedFact
from memory.fact_store import FactStore
from memory.preference_profile import PreferenceProfile


@pytest.fixture
def store():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test_prefs.db")
        fs = FactStore(db_path, disable_embedding=True)
        yield fs


def seed_facts(store: FactStore, user_id: str = "u1"):
    store.store_facts([
        ExtractedFact(subject="user", predicate="preference", object="dark mode",
                      confidence=0.9, category="preference",
                      source_text="I like dark mode.", user_id=user_id),
        ExtractedFact(subject="user", predicate="preference", object="Python",
                      confidence=0.8, category="preference",
                      source_text="I like Python.", user_id=user_id),
        ExtractedFact(subject="user", predicate="preference", object="VS Code",
                      confidence=0.7, category="preference",
                      source_text="My favorite editor is VS Code.", user_id=user_id),
    ], user_id=user_id)


# ═══════════════════════════════════════════════════════════════════════════════
# 1.  Profile building
# ═══════════════════════════════════════════════════════════════════════════════


def test_build_profile(store):
    seed_facts(store)
    profile = PreferenceProfile("u1").build(store)
    assert len(profile.topics) >= 1


def test_profile_returns_preference(store):
    seed_facts(store)
    profile = PreferenceProfile("u1").build(store)
    value = profile.get("dark")
    assert value is not None
    assert "dark mode" in value.lower()


def test_profile_unknown_topic(store):
    seed_facts(store)
    profile = PreferenceProfile("u1").build(store)
    assert profile.get("nonexistent") is None


def test_profile_default_value(store):
    seed_facts(store)
    profile = PreferenceProfile("u1").build(store)
    assert profile.get("nonexistent", "fallback") == "fallback"


# ═══════════════════════════════════════════════════════════════════════════════
# 2.  Confidence and recency tracking
# ═══════════════════════════════════════════════════════════════════════════════


def test_profile_higher_confidence_overrides(store):
    store.store_facts([
        ExtractedFact(subject="user", predicate="preference", object="dark mode",
                      confidence=0.5, category="preference",
                      source_text="I kinda like dark mode.", user_id="u1"),
    ], user_id="u1")
    store.store_facts([
        ExtractedFact(subject="user", predicate="preference", object="dark mode",
                      confidence=0.9, category="preference",
                      source_text="I love dark mode!", user_id="u1"),
    ], user_id="u1", force=True)

    profile = PreferenceProfile("u1").build(store)
    entry = profile.get_entry("dark")
    assert entry is not None
    assert entry.value == "dark mode"
    assert entry.confidence == 0.9
    assert entry.assertion_count >= 2


# ═══════════════════════════════════════════════════════════════════════════════
# 3.  Formatting
# ═══════════════════════════════════════════════════════════════════════════════


def test_format_context_empty(store):
    profile = PreferenceProfile("u1").build(store)
    assert profile.format_context() == ""


def test_format_context_with_preferences(store):
    seed_facts(store)
    profile = PreferenceProfile("u1").build(store)
    formatted = profile.format_context()
    assert "Known User Preferences" in formatted
    assert "dark" in formatted.lower() or "python" in formatted.lower()


# ═══════════════════════════════════════════════════════════════════════════════
# 4.  Per-user isolation
# ═══════════════════════════════════════════════════════════════════════════════


def test_profile_per_user_isolation(store):
    seed_facts(store, user_id="u1")
    seed_facts(store, user_id="u2")

    profile_u1 = PreferenceProfile("u1").build(store)
    profile_u2 = PreferenceProfile("u2").build(store)

    assert len(profile_u1.topics) >= 1
    assert len(profile_u2.topics) >= 1


def test_profile_to_dict(store):
    seed_facts(store)
    profile = PreferenceProfile("u1").build(store)
    d = profile.to_dict()
    assert isinstance(d, dict)
    assert len(d) >= 1
