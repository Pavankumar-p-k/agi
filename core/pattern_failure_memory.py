"""core/pattern_failure_memory.py
Generalized pattern failure memory with scoring and ranking.

Stores generalized error patterns so one fix solves many future errors.
Each pattern can have multiple fix strategies with per-strategy success/failure tracking.

Scoring (for ranking multiple matching strategies):
    score = (success_rate * 0.5) + (recency * 0.2) + (cost_bonus * 0.1)
"""
import json
import logging
import re
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

MEMORY_FILE = Path.home() / ".jarvis" / "pattern_failures.json"

# Strategy cost categories: cheap strategies get a bonus
_CHEAP_STRATEGIES = {
    "add_import", "fix_syntax", "add_string_resource", "add_color_resource",
    "create_drawable", "create_mipmap", "add_view_id",
    "fix_duplicate_override", "fix_invalid_override",
}


@dataclass
class StrategyStats:
    """Per-strategy statistics for a pattern."""
    success_count: int = 0
    failure_count: int = 0
    last_used: str = ""
    avg_iterations_saved: float = 0.0

    @property
    def success_rate(self) -> float:
        total = self.success_count + self.failure_count
        if total == 0:
            return 0.0
        return self.success_count / total

    @property
    def total(self) -> int:
        return self.success_count + self.failure_count


@dataclass
class PatternEntry:
    pattern: str
    regex: str
    fix_strategy: str = ""
    count: int = 1
    first_seen: str = ""
    last_seen: str = ""
    exemplar: str = ""
    strategies: dict[str, StrategyStats] = field(default_factory=dict)

    def best_strategy(self) -> str | None:
        """Return the highest-scoring non-FAILED strategy, or None."""
        candidates = [
            (sname, stats)
            for sname, stats in self.strategies.items()
            if not sname.startswith("FAILED:")
        ]
        if not candidates:
            if self.fix_strategy and not self.fix_strategy.startswith("FAILED:"):
                return self.fix_strategy
            return None
        scored = sorted(
            ((sname, _score_strategy(stats)) for sname, stats in candidates),
            key=lambda x: x[1], reverse=True,
        )
        return scored[0][0] if scored else None


# ── Scoring ────────────────────────────────────────────────────────

def _score_strategy(stats: StrategyStats) -> float:
    """Compute a score from 0.0 to 1.0 for ranking."""
    if stats.total == 0:
        return 0.0
    success_rate = stats.success_count / max(stats.total, 1)
    recency = 0.0
    if stats.last_used:
        try:
            last = datetime.fromisoformat(stats.last_used)
            now = datetime.now()
            if last.tzinfo is None:
                days_ago = (now - last).days
            else:
                days_ago = (now.astimezone() - last).days
            recency = max(0.0, min(1.0, 1.0 / max(days_ago + 1, 1)))
        except (ValueError, TypeError):
            recency = 0.0
    return (success_rate * 0.5) + (recency * 0.2)


def _is_cheap_strategy(strategy: str) -> bool:
    base = strategy.split(":")[0] if ":" in strategy else strategy
    return base in _CHEAP_STRATEGIES


# ── Scored Match ───────────────────────────────────────────────────

@dataclass
class ScoredMatch:
    """A strategy matched with its score."""
    pattern: str
    fix_strategy: str
    score: float = 0.0
    success_count: int = 0
    failure_count: int = 0
    success_rate: float = 0.0

    @property
    def is_valid(self) -> bool:
        return not self.fix_strategy.startswith("FAILED:")


# ── Generalization ────────────────────────────────────────────────

def _generalize(failure_text: str) -> tuple[str, str]:
    """Generalize a concrete failure into a pattern and its regex.
    
    Only replaces variable parts (capitalized identifiers, numbers, strings, paths)
    while keeping structural keywords (lowercase words) as-is.
    
    'cannot find symbol: Button' -> 'cannot find symbol : *'
    'R.layout.main not found' -> 'R.layout.* not found'
    """
    text = failure_text.strip()

    replacements = [
        # Dotted chains starting with a capital letter (e.g. R.layout.activity_main)
        # Must run BEFORE the general capitalized-word rule so the chain is
        # consumed as a single wildcard instead of fragmenting on the dot.
        (r'\b[A-Z][a-zA-Z0-9]*(?:\.[a-zA-Z_]\w*)+\b', ' * '),
        # Capitalized words (class names, types, etc.)
        (r'\b[A-Z][a-zA-Z0-9]*(?:\s+[A-Z][a-zA-Z0-9]*)*\b', ' * '),
        # Numbers
        (r'\b\d+\b', ' N '),
        # String literals
        (r'["\'][^"\']*["\']', ' "..." '),
        # URLs and file paths
        (r'(https?://|/|\.\./)[^\s,;)]+', ' * '),
        (r'[\w/\\:.]+\.(?:java|kt|xml|gradle)\b', ' * '),
    ]

    generalized = text
    for pattern, replacement in replacements:
        generalized = re.sub(pattern, replacement, generalized)

    # Normalize whitespace: collapse multiple spaces, trim
    generalized = re.sub(r'\s+', ' ', generalized).strip()

    # Deduplicate consecutive * tokens (multiple wildcards collapse to one)
    tokens = generalized.split()
    deduped = []
    for tok in tokens:
        if tok == '*' and deduped and deduped[-1] == '*':
            continue
        deduped.append(tok)
    generalized = ' '.join(deduped)

    regex_parts = []
    for word in generalized.split():
        if word == '*':
            regex_parts.append(r'\S+')
        elif word == 'N':
            regex_parts.append(r'\d+')
        elif word == '"..."':
            regex_parts.append(r'["\'][^"\']*["\']')
        else:
            # Escape the word; if it contains punctuation (like "symbol:"),
            # allow optional whitespace before the punctuation
            escaped = re.escape(word)
            if word and word[-1] in ':;,.[](){}':
                # "symbol:" -> "symbol\s*:"
                punct = re.escape(word[-1])
                body = re.escape(word[:-1])
                escaped = body + r'\s*' + punct
            regex_parts.append(escaped)

    return generalized, '^' + r'\s+'.join(regex_parts) + '$'


# ── Strategy helpers ───────────────────────────────────────────────

def _update_strategy_stats(entry: PatternEntry, fix_strategy: str):
    """Update per-strategy success/failure stats for an existing entry."""
    if fix_strategy.startswith("FAILED:"):
        base = fix_strategy.replace("FAILED:", "", 1)
        if base not in entry.strategies:
            entry.strategies[base] = StrategyStats()
        entry.strategies[base].failure_count += 1
        entry.strategies[base].last_used = datetime.now().isoformat()
        if fix_strategy not in entry.strategies:
            entry.strategies[fix_strategy] = StrategyStats(failure_count=1)
        else:
            entry.strategies[fix_strategy].failure_count += 1
        entry.strategies[fix_strategy].last_used = datetime.now().isoformat()
    else:
        if fix_strategy not in entry.strategies:
            entry.strategies[fix_strategy] = StrategyStats()
        entry.strategies[fix_strategy].success_count += 1
        entry.strategies[fix_strategy].last_used = datetime.now().isoformat()


def _create_strategies_for_new(fix_strategy: str) -> dict:
    """Create per-strategy stats for a new pattern entry."""
    strategies = {}
    if fix_strategy.startswith("FAILED:"):
        base = fix_strategy.replace("FAILED:", "", 1)
        strategies[base] = StrategyStats(failure_count=1, last_used=datetime.now().isoformat())
        strategies[fix_strategy] = StrategyStats(failure_count=1, last_used=datetime.now().isoformat())
    else:
        strategies[fix_strategy] = StrategyStats(success_count=1, last_used=datetime.now().isoformat())
    return strategies


# ── Memory Class ──────────────────────────────────────────────────

class PatternFailureMemory:
    def __init__(self):
        self._patterns: dict[str, PatternEntry] = {}
        self._loaded = False

    def _ensure_loaded(self):
        if not self._loaded:
            self._load()

    def _load(self):
        self._patterns = {}
        try:
            if MEMORY_FILE.exists():
                data = json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
                for k, v in data.items():
                    strategies_raw = v.get("strategies", {})
                    strategies = {}
                    for sk, sv in strategies_raw.items():
                        if isinstance(sv, dict):
                            strategies[sk] = StrategyStats(**sv)
                        else:
                            strategies[sk] = sv
                    if not strategies and v.get("fix_strategy"):
                        sname = v["fix_strategy"]
                        strategies[sname] = StrategyStats(
                            success_count=max(v.get("count", 1), 1),
                            last_used=v.get("last_seen", ""),
                        )
                    v["strategies"] = strategies
                    self._patterns[k] = PatternEntry(**v)
        except Exception as e:
            logger.warning(f"[PFM] Failed to load pattern memory: {e}")
        self._loaded = True

    def _save(self):
        try:
            MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
            data = {}
            for k, v in self._patterns.items():
                d = asdict(v)
                d["strategies"] = {k: asdict(s) for k, s in v.strategies.items()}
                data[k] = d
            MEMORY_FILE.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        except Exception as e:
            logger.warning(f"[PFM] Failed to save pattern memory: {e}")

    def match(self, failure_text: str) -> ScoredMatch | None:
        """Return the single best matching strategy, or None."""
        matches = self.match_all(failure_text)
        return matches[0] if matches else None

    def match_all(self, failure_text: str) -> list[ScoredMatch]:
        """Return all matching strategies sorted by score descending."""
        self._ensure_loaded()
        results: list[ScoredMatch] = []

        for entry in self._patterns.values():
            try:
                if not re.search(entry.regex, failure_text, re.IGNORECASE):
                    continue
            except re.error:
                continue

            best_sname = entry.best_strategy()
            if not best_sname:
                continue

            stats = entry.strategies.get(best_sname, StrategyStats())
            base_score = _score_strategy(stats)
            cost_bonus = 0.1 if _is_cheap_strategy(best_sname) else 0.0
            final_score = base_score + (cost_bonus * 0.1)

            results.append(ScoredMatch(
                pattern=entry.pattern,
                fix_strategy=best_sname,
                score=round(final_score, 4),
                success_count=stats.success_count,
                failure_count=stats.failure_count,
                success_rate=stats.success_rate,
            ))

        results.sort(key=lambda m: m.score, reverse=True)
        return results

    def record(self, failure_text: str, fix_strategy: str):
        self._ensure_loaded()
        generalized, regex = _generalize(failure_text)

        if generalized in self._patterns:
            entry = self._patterns[generalized]
            entry.count += 1
            entry.last_seen = datetime.now().isoformat()
            _update_strategy_stats(entry, fix_strategy)
        else:
            strategies = _create_strategies_for_new(fix_strategy)
            entry = PatternEntry(
                pattern=generalized,
                regex=regex,
                fix_strategy=fix_strategy,
                first_seen=datetime.now().isoformat(),
                last_seen=datetime.now().isoformat(),
                exemplar=failure_text[:200],
                strategies=strategies,
            )
            logger.info(f"[PFM] New pattern: {generalized} -> {fix_strategy}")

        self._patterns[generalized] = entry
        self._save()

    def record_success(self, failure_text: str, fix_strategy: str):
        self.record(failure_text, fix_strategy)

    def record_failure(self, failure_text: str, fix_strategy: str):
        self.record(failure_text, f"FAILED:{fix_strategy}")

    def get_stats(self) -> dict:
        self._ensure_loaded()
        total = len(self._patterns)
        total_fixes = sum(e.count for e in self._patterns.values())
        total_successes = sum(
            sum(s.success_count for s in e.strategies.values())
            for e in self._patterns.values()
        )
        total_failures = sum(
            sum(s.failure_count for s in e.strategies.values())
            for e in self._patterns.values()
        )
        top = sorted(self._patterns.values(), key=lambda e: e.count, reverse=True)[:10]
        return {
            "total_patterns": total,
            "total_fixes_applied": total_fixes,
            "total_successes": total_successes,
            "total_failures": total_failures,
            "overall_success_rate": round(
                total_successes / max(total_successes + total_failures, 1), 3
            ),
            "top_patterns": [
                {
                    "pattern": e.pattern,
                    "count": e.count,
                    "strategies": list(e.strategies.keys())[:5],
                    "best_strategy": e.best_strategy(),
                }
                for e in top
            ],
        }

    def clear(self):
        self._patterns = {}
        self._save()
        logger.info("[PFM] Pattern memory cleared")


pattern_memory = PatternFailureMemory()
