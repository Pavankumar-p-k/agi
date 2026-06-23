"""Tests for PatternFailureMemory with ranking."""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import pytest
from pathlib import Path
from datetime import datetime, timezone

from core.pattern_failure_memory import (
    PatternFailureMemory,
    PatternEntry,
    StrategyStats,
    ScoredMatch,
    _generalize,
    _score_strategy,
)


@pytest.fixture(autouse=True)
def isolated_memory():
    """Each test gets a fresh memory with no file persistence."""
    mem = PatternFailureMemory()
    mem.clear()
    return mem


# ── Generalization ───────────────────────────────────────────────

def test_generalize_import_error():
    pat, regex = _generalize("cannot find symbol: class Button")
    assert "*" in pat  # words are generalized to *
    assert bool(regex)  # regex is non-empty

def test_generalize_layout_error():
    pat, regex = _generalize("R.layout.activity_main not found")
    assert "*" in pat  # layout name generalized

def test_generalize_type_mismatch():
    pat, regex = _generalize("incompatible types: String cannot be converted to int")
    assert "*" in pat  # types generalized


# ── StrategyStats ───────────────────────────────────────────────

def test_strategy_stats_success_rate():
    s = StrategyStats(success_count=9, failure_count=1)
    assert s.success_rate == 0.9

def test_strategy_stats_empty():
    s = StrategyStats()
    assert s.success_rate == 0.0
    assert s.total == 0


# ── Scoring ─────────────────────────────────────────────────────

def test_score_strategy_perfect():
    s = StrategyStats(success_count=10, failure_count=0, last_used=datetime.now().isoformat())
    score = _score_strategy(s)
    assert score > 0.0, f"Expected positive score, got {score}"
    assert score <= 0.7  # success_rate*0.5 + recency*0.2

def test_score_strategy_all_failures():
    s = StrategyStats(success_count=0, failure_count=10)
    score = _score_strategy(s)
    assert score == 0.0  # success_rate 0.0

def test_score_strategy_empty_stats():
    score = _score_strategy(StrategyStats())
    assert score == 0.0

def test_score_strategy_no_last_used():
    s = StrategyStats(success_count=5, failure_count=0)
    score = _score_strategy(s)
    assert score > 0.0  # success_rate alone gives positive score


# ── PatternEntry ────────────────────────────────────────────────

def test_best_strategy_single():
    entry = PatternEntry(
        pattern="test", regex=".",
        strategies={"add_import": StrategyStats(success_count=5)},
    )
    assert entry.best_strategy() == "add_import"

def test_best_strategy_prefers_highest_score():
    entry = PatternEntry(
        pattern="test", regex=".",
        strategies={
            "add_import": StrategyStats(success_count=2, failure_count=8),
            "create_file": StrategyStats(success_count=9, failure_count=1),
        },
    )
    assert entry.best_strategy() == "create_file"

def test_best_strategy_skips_failed():
    entry = PatternEntry(
        pattern="test", regex=".",
        strategies={
            "FAILED:add_import": StrategyStats(failure_count=3),
            "create_file": StrategyStats(success_count=1),
        },
    )
    assert entry.best_strategy() == "create_file"

def test_best_strategy_all_failed():
    entry = PatternEntry(
        pattern="test", regex=".",
        strategies={"FAILED:add_import": StrategyStats(failure_count=3)},
    )
    assert entry.best_strategy() is None


# ── Legacy Migration ────────────────────────────────────────────

def test_legacy_migration(isolated_memory, tmp_path):
    """Old format has fix_strategy string but no strategies dict."""
    legacy_data = {
        "cannot find symbol *": {
            "pattern": "cannot find symbol *",
            "regex": r"^cannot find symbol \S+$",
            "fix_strategy": "add_import",
            "count": 5,
            "first_seen": "2026-01-01",
            "last_seen": "2026-06-01",
            "exemplar": "cannot find symbol: Button",
        }
    }
    mem_file = Path.home() / ".jarvis" / "pattern_failures.json"
    mem_file.parent.mkdir(parents=True, exist_ok=True)
    mem_file.write_text(json.dumps(legacy_data))

    try:
        m = PatternFailureMemory()
        m._load()
        assert len(m._patterns) == 1, f"Expected 1 pattern, got {len(m._patterns)}"
        entry = list(m._patterns.values())[0]
        assert "add_import" in entry.strategies, (
            f"Expected add_import in strategies, got {list(entry.strategies.keys())}"
        )
        assert entry.strategies["add_import"].success_count >= 1
    finally:
        mem_file.unlink(missing_ok=True)


# ── record / record_success / record_failure ────────────────────

def test_record_new_pattern(isolated_memory):
    isolated_memory.record("cannot find symbol: Button", "add_import")
    assert len(isolated_memory._patterns) == 1
    entry = list(isolated_memory._patterns.values())[0]
    assert "add_import" in entry.strategies
    assert entry.strategies["add_import"].success_count == 1

def test_record_existing_increments_count(isolated_memory):
    isolated_memory.record("cannot find symbol: Button", "add_import")
    isolated_memory.record("cannot find symbol: TextView", "add_import")
    entry = list(isolated_memory._patterns.values())[0]
    assert entry.count == 2
    assert entry.strategies["add_import"].success_count == 2

def test_record_success(isolated_memory):
    isolated_memory.record_success("cannot find symbol: Button", "add_import")
    entry = list(isolated_memory._patterns.values())[0]
    assert entry.strategies["add_import"].success_count == 1
    assert entry.strategies["add_import"].failure_count == 0

def test_record_failure(isolated_memory):
    isolated_memory.record_failure("cannot find symbol: Button", "add_import")
    entry = list(isolated_memory._patterns.values())[0]
    assert "add_import" in entry.strategies, (
        f"Expected base strategy, got {list(entry.strategies.keys())}"
    )
    assert entry.strategies["add_import"].failure_count >= 1, (
        "failure_count should be >= 1 after recording a failure"
    )

def test_record_multiple_strategies(isolated_memory):
    isolated_memory.record("R.layout.main not found", "create_layout")
    isolated_memory.record("R.layout.main not found", "create_layout")
    isolated_memory.record("R.layout.main not found", "create_drawable")
    entry = list(isolated_memory._patterns.values())[0]
    assert "create_layout" in entry.strategies
    assert "create_drawable" in entry.strategies
    assert entry.strategies["create_layout"].success_count == 2
    assert entry.strategies["create_drawable"].success_count == 1


# ── match ───────────────────────────────────────────────────────

def test_match_single(isolated_memory):
    isolated_memory.record("cannot find symbol: Button", "add_import")
    result = isolated_memory.match("cannot find symbol: Button")
    assert result is not None, f"Expected match, patterns={isolated_memory._patterns}"
    assert result.fix_strategy == "add_import"
    assert result.is_valid

def test_match_by_regex(isolated_memory):
    isolated_memory.record("cannot find symbol: Button", "add_import")
    result = isolated_memory.match("cannot find symbol: RecyclerView")
    assert result is not None, "Expected match by regex"
    assert result.fix_strategy == "add_import"

def test_match_no_match(isolated_memory):
    result = isolated_memory.match("something completely different")
    assert result is None


# ── match_all (ranking) ────────────────────────────────────────

def test_match_all_returns_sorted_candidates(isolated_memory):
    isolated_memory.record("cannot find symbol: Button", "add_import")
    isolated_memory.record("cannot find symbol: Button", "create_file")
    isolated_memory.record_success("cannot find symbol: Button", "add_import")
    isolated_memory.record_success("cannot find symbol: Button", "add_import")
    isolated_memory.record_failure("cannot find symbol: Button", "create_file")
    isolated_memory.record_failure("cannot find symbol: Button", "create_file")

    results = isolated_memory.match_all("cannot find symbol: EditText")
    assert len(results) >= 1, f"Expected >=1 matches, got {len(results)}"
    top = results[0]
    assert top.fix_strategy == "add_import"
    assert top.success_count >= 2
    assert top.success_rate > 0.5

def test_match_all_skips_failed_strategies(isolated_memory):
    isolated_memory.record_failure("cannot find symbol: X", "add_import")
    results = isolated_memory.match_all("cannot find symbol: Y")
    # After only failures, base strategy still exists with 0 success rate
    # It should be included but with a very low score
    assert len(results) == 1
    assert results[0].success_rate == 0.0
    assert results[0].success_count == 0
    assert results[0].failure_count >= 1

def test_match_all_multi_pattern(isolated_memory):
    isolated_memory.record("cannot find symbol: Button", "add_import")
    isolated_memory.record("R.layout.main not found", "create_layout")
    results = isolated_memory.match_all("something else entirely")
    assert len(results) == 0


# ── get_stats ──────────────────────────────────────────────────

def test_get_stats_empty(isolated_memory):
    stats = isolated_memory.get_stats()
    assert stats["total_patterns"] == 0
    assert stats["total_fixes_applied"] == 0

def test_get_stats_after_records(isolated_memory):
    isolated_memory.record_success("error X", "fix_a")
    isolated_memory.record_failure("error Y", "fix_b")
    isolated_memory.record_success("error X", "fix_a")
    stats = isolated_memory.get_stats()
    assert stats["total_patterns"] >= 1
    assert stats["total_successes"] >= 2


# ── clear ──────────────────────────────────────────────────────

def test_clear(isolated_memory):
    isolated_memory.record("test", "fix")
    isolated_memory.clear()
    assert len(isolated_memory._patterns) == 0
    assert isolated_memory.match("test") is None


# ── Integration: ranking in engine context ─────────────────────

def test_ranking_prefers_successful_strategies(isolated_memory):
    """Error matches multiple strategies — picks highest success rate."""
    isolated_memory.record("incompatible types: String cannot be converted to int", "fix_code")
    isolated_memory.record_success("incompatible types: String cannot be converted to int", "fix_code")
    isolated_memory.record_success("incompatible types: String cannot be converted to int", "fix_code")
    isolated_memory.record_failure("incompatible types: String cannot be converted to int", "fix_code")
    # Same pattern with different strategy (lower success rate)
    isolated_memory.record("incompatible types: String cannot be converted to int", "fix_resources")
    isolated_memory.record_failure("incompatible types: String cannot be converted to int", "fix_resources")

    results = isolated_memory.match_all("incompatible types: Boolean cannot be converted to int")
    assert len(results) >= 1, f"Expected >=1 matches, got {len(results)}"
    top = results[0]
    assert top.fix_strategy == "fix_code", (
        f"Expected fix_code (higher success rate), got {top.fix_strategy}"
    )
    assert top.success_count >= 2

def test_ranking_with_cost_bonus(isolated_memory):
    """Cheap strategies get a small bonus in ranking."""
    # Two strategies with ~same success rate, one is cheap (add_import)
    isolated_memory.record("cannot find symbol: Button", "add_import")
    isolated_memory.record("cannot find symbol: Button", "create_file")
    isolated_memory.record_success("cannot find symbol: Button", "add_import")
    isolated_memory.record_success("cannot find symbol: Button", "create_file")

    results = isolated_memory.match_all("cannot find symbol: EditText")
    assert len(results) >= 1
    top = results[0]
    assert top.fix_strategy == "add_import", (
        f"Expected add_import (cheaper), got {top.fix_strategy}"
    )
