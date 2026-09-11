from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import json
import re

MEMORY_PATH = Path.home() / ".jarvis" / "pattern_failures.json"


def _generalize(message: str) -> tuple[str, str]:
    words = re.findall(r"[A-Za-z_][\w.]*", message)
    pattern = message
    for word in words:
        if len(word) > 2 and word.lower() not in {"cannot", "find", "symbol", "types", "converted"}:
            pattern = pattern.replace(word, "*")
    if message.startswith("cannot find symbol:"):
        regex = r"^cannot\ find\ symbol:\ \S+$"
    elif message.startswith("R.layout.") and message.endswith(" not found"):
        regex = r"^R\.layout\.\S+\ not\ found$"
    elif message.startswith("incompatible types:") and " cannot be converted to " in message:
        regex = r"^incompatible\ types:\ \S+\ cannot\ be\ converted\ to\ \S+$"
    elif re.match(r"^error \S+$", message):
        regex = r"^error\ \S+$"
    else:
        regex = re.escape(message)
    return pattern, f"^{regex}$"


@dataclass
class StrategyStats:
    success_count: int = 0
    failure_count: int = 0
    last_used: str = ""

    @property
    def total(self): return self.success_count + self.failure_count
    @property
    def success_rate(self): return self.success_count / self.total if self.total else 0.0


def _score_strategy(stats: StrategyStats) -> float:
    score = stats.success_rate * 0.5
    if stats.last_used:
        score += 0.2
    return score


@dataclass
class ScoredMatch:
    pattern: str
    fix_strategy: str
    score: float
    success_count: int
    failure_count: int
    success_rate: float
    @property
    def is_valid(self): return self.success_rate > 0


@dataclass
class PatternEntry:
    pattern: str
    regex: str
    strategies: dict[str, StrategyStats] = field(default_factory=dict)
    count: int = 0
    first_seen: str = ""
    last_seen: str = ""
    exemplar: str = ""

    def best_strategy(self):
        candidates = [(name, stats) for name, stats in self.strategies.items() if not name.startswith("FAILED:")]
        return max(candidates, key=lambda item: _score_strategy(item[1]))[0] if candidates else None


class PatternFailureMemory:
    def __init__(self):
        self._patterns: dict[str, PatternEntry] = {}
        self._load()

    def _load(self):
        if not MEMORY_PATH.exists(): return
        try:
            data = json.loads(MEMORY_PATH.read_text(encoding="utf-8"))
            for key, raw in data.items():
                strategies = raw.get("strategies", {})
                if not strategies and raw.get("fix_strategy"):
                    strategies = {raw["fix_strategy"]: {"success_count": max(1, raw.get("count", 1))}}
                self._patterns[key] = PatternEntry(
                    pattern=raw.get("pattern", key), regex=raw.get("regex", ".*"),
                    strategies={k: StrategyStats(**v) for k, v in strategies.items()},
                    count=raw.get("count", 0), first_seen=raw.get("first_seen", ""),
                    last_seen=raw.get("last_seen", ""), exemplar=raw.get("exemplar", ""),
                )
        except (OSError, json.JSONDecodeError, TypeError):
            self._patterns = {}

    def _save(self):
        MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = {k: {**vars(v), "strategies": {n: vars(s) for n, s in v.strategies.items()}} for k, v in self._patterns.items()}
        MEMORY_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def clear(self):
        self._patterns.clear()
        self._save()

    def record(self, error, strategy):
        pattern, regex = _generalize(error)
        entry = self._patterns.setdefault(pattern, PatternEntry(pattern, regex, exemplar=error))
        entry.count += 1
        entry.last_seen = datetime.now().isoformat()
        stats = entry.strategies.setdefault(strategy, StrategyStats())
        stats.success_count += 1
        stats.last_used = entry.last_seen
        self._save()

    def record_success(self, error, strategy): self.record(error, strategy)

    def record_failure(self, error, strategy):
        pattern, regex = _generalize(error)
        entry = self._patterns.setdefault(pattern, PatternEntry(pattern, regex, exemplar=error))
        entry.count += 1
        stats = entry.strategies.setdefault(strategy, StrategyStats())
        stats.failure_count += 1
        self._save()

    def match_all(self, error):
        results = []
        for entry in self._patterns.values():
            try: matches = re.search(entry.regex, error)
            except re.error: matches = False
            if matches:
                for strategy, stats in entry.strategies.items():
                    results.append(ScoredMatch(entry.pattern, strategy, _score_strategy(stats), stats.success_count, stats.failure_count, stats.success_rate))
        return sorted(results, key=lambda item: (-item.score, item.fix_strategy))

    def match(self, error):
        results = self.match_all(error)
        return results[0] if results else None

    def get_stats(self):
        total = sum(e.count for e in self._patterns.values())
        successes = sum(s.success_count for e in self._patterns.values() for s in e.strategies.values())
        failures = sum(s.failure_count for e in self._patterns.values() for s in e.strategies.values())
        return {
            "total_patterns": len(self._patterns),
            "total": total,
            "total_fixes_applied": successes,
            "total_successes": successes,
            "total_failures": failures,
        }


pattern_memory = PatternFailureMemory()
