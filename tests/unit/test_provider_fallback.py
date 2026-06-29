from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from core.providers.feedback.models import ProviderResult
from core.providers.memory import (
    _FALLBACK_CHAIN,
    _match_keys,
    _MEMORY_FILE,
    ProviderMemory,
    evidence_key,
)


@pytest.fixture(autouse=True)
def _isolate_memory():
    """Backup and restore provider memory file between tests."""
    backup = None
    if _MEMORY_FILE.exists():
        backup = _MEMORY_FILE.read_bytes()
    yield
    if backup is not None:
        _MEMORY_FILE.write_bytes(backup)
    elif _MEMORY_FILE.exists():
        _MEMORY_FILE.unlink()


class TestEvidenceFallbackChain:
    """Gate 2 B1 fix: evidence recorded with empty fields matches populated lookups."""

    # ── Static fallback chain tests ────────────────────────────────────────

    def test_fallback_has_9_patterns(self):
        assert len(_FALLBACK_CHAIN) >= 9, "B1 fix must have 9+ fallback patterns"

    def test_fallback_includes_critical_pattern(self):
        assert (3, 0, 2, 0) in _FALLBACK_CHAIN, "Missing critical pattern: (3,0,2,0)"

    def test_match_keys_drops_task_type_and_lang(self):
        base = ("forge", "coding", "implement", "qwen2.5:7b", "python")
        result = _match_keys(base, (3, 0, 2, 0))
        assert result == ("forge", "coding", "", "qwen2.5:7b", "")

    # ── B1: Record with empty fields, lookup with populated ────────────────

    def test_b1_distribution_found_with_tt_lang_mismatch(self):
        """Pattern 6 (3,0,2,0) matches: record tt='',lang='', lookup tt!='',lang!=''."""
        mem = ProviderMemory()
        mem.record(
            ProviderResult(
                provider_id="forge",
                capability="coding",
                success=True,
                duration_ms=1500,
                metrics={"task_type": "", "model": "qwen2.5:7b", "language": ""},
            )
        )
        dist = mem.get_distribution(
            "forge", "coding", task_type="implement", model="qwen2.5:7b", language="python",
        )
        assert dist is not None, "B1 FAIL: distribution is None"
        assert dist.executions >= 1, "B1 FAIL: distribution needs >=1 execution"

    def test_b1_score_differs_from_prior(self):
        """get_performance_score() returns the conservative 10th percentile bound.
        For a single success, this is ~0.36 — the key is that evidence IS found
        (prior would be 0.5)."""
        mem = ProviderMemory()
        mem.record(
            ProviderResult(
                provider_id="forge",
                capability="coding",
                success=True,
                duration_ms=1500,
                metrics={"task_type": "", "model": "qwen2.5:7b", "language": ""},
            )
        )
        score = mem.get_performance_score(
            "forge",
            {"capability": "coding", "task_type": "implement", "model": "qwen2.5:7b", "language": "python"},
        )
        # Before B1 fix, this would be 0.5 (no evidence found → prior)
        # After B1 fix, evidence matches via fallback pattern 6
        assert score != 0.5, f"B1 FAIL: score={score} — still using prior (evidence not found)"

    # ── Distribution lookups ───────────────────────────────────────────────

    # ── Provider isolation ─────────────────────────────────────────────────

    def test_different_providers_isolated(self):
        mem = ProviderMemory()
        mem.record(
            ProviderResult(
                provider_id="forge",
                capability="coding",
                success=True,
                duration_ms=1000,
                metrics={"task_type": "", "model": "qwen2.5:7b", "language": ""},
            )
        )
        mem.record(
            ProviderResult(
                provider_id="claude_code",
                capability="coding",
                success=False,
                duration_ms=5000,
                metrics={"task_type": "implement", "model": "claude-4", "language": "python"},
            )
        )
        # Fallback chain walks lookup→stored (not stored→lookup) — lookup
        # must match all stored fields or drop them via wildcard.
        # forge: stored has model="qwen2.5:7b" with empty tt/lang
        # claude_code: stored has tt="implement", model="claude-4", lang="python"
        f_dist = mem.get_distribution("forge", "coding", model="qwen2.5:7b")
        cc_dist = mem.get_distribution(
            "claude_code", "coding", task_type="implement", model="claude-4", language="python",
        )
        assert f_dist is not None and f_dist.successes >= 1
        assert cc_dist is not None and cc_dist.successes == 0

    # ── No evidence ────────────────────────────────────────────────────────

    def test_no_evidence_returns_prior(self):
        mem = ProviderMemory()
        score = mem.get_performance_score("unknown", {"capability": "anything"})
        assert score == 0.5

    # ── Record without crash ───────────────────────────────────────────────

    def test_record_without_retrieve_does_not_crash(self):
        mem = ProviderMemory()
        mem.record(
            ProviderResult(
                provider_id="test",
                capability="test",
                success=True,
                duration_ms=100,
                metrics={},
            )
        )

    # ── Evidence key function ──────────────────────────────────────────────

    def test_evidence_key_5_tuple(self):
        k = evidence_key("forge", "coding", "implement", "qwen2.5:7b", "python")
        assert k == ("forge", "coding", "implement", "qwen2.5:7b", "python")

    def test_evidence_key_empty_defaults(self):
        k = evidence_key("forge")
        assert k == ("forge", "", "", "", "")

    # ── Multiple recordings with fallback ──────────────────────────────────

    def test_multiple_recordings_accumulate(self):
        mem = ProviderMemory()
        for i in range(3):
            mem.record(
                ProviderResult(
                    provider_id="forge",
                    capability="coding",
                    success=(i % 2 == 0),
                    duration_ms=1000,
                    metrics={"task_type": "", "model": "qwen2.5:7b", "language": ""},
                )
            )
        dist = mem.get_distribution(
            "forge", "coding", task_type="implement", model="qwen2.5:7b", language="python",
        )
        assert dist is not None
        assert dist.executions >= 3
