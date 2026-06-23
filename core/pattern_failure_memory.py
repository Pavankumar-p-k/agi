"""core/pattern_failure_memory.py
Generalized pattern failure memory.
Stores generalized error patterns so one fix solves many future errors.
Stored as: generalized_pattern → { fix_strategy, count, first_seen, last_seen }
"""
import json
import logging
import re
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

MEMORY_FILE = Path.home() / ".jarvis" / "pattern_failures.json"


@dataclass
class PatternEntry:
    pattern: str
    regex: str
    fix_strategy: str
    count: int = 1
    first_seen: str = ""
    last_seen: str = ""
    exemplar: str = ""


def _generalize(failure_text: str) -> tuple[str, str]:
    """Generalize a concrete failure into a pattern and its regex.
    'cannot resolve symbol Button' → ('cannot resolve symbol *', r'cannot resolve symbol \w+')
    """
    text = failure_text.strip()

    replacements = [
        (r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', '*'),
        (r'\b[a-z_][a-z0-9_]*\b', '*'),
        (r'\b\d+\b', 'N'),
        (r'["\'][^"\']*["\']', '"..."'),
        (r'(https?://|/)[^\s,;)]+', '*'),
    ]

    generalized = text
    for pattern, replacement in replacements:
        generalized = re.sub(pattern, replacement, generalized)

    deduped_parts = []
    prev = None
    for part in generalized.split():
        if part != prev:
            deduped_parts.append(part)
        prev = part
    generalized = ' '.join(deduped_parts)

    regex_parts = []
    for word in generalized.split():
        if word == '*':
            regex_parts.append(r'\S+')
        elif word == 'N':
            regex_parts.append(r'\d+')
        elif word == '"..."':
            regex_parts.append(r'["\'][^"\']*["\']')
        else:
            regex_parts.append(re.escape(word))

    return generalized, '^' + r'\s+'.join(regex_parts) + '$'


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
                    self._patterns[k] = PatternEntry(**v)
        except Exception as e:
            logger.warning(f"[PFM] Failed to load pattern memory: {e}")
        self._loaded = True

    def _save(self):
        try:
            MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
            data = {k: asdict(v) for k, v in self._patterns.items()}
            MEMORY_FILE.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        except Exception as e:
            logger.warning(f"[PFM] Failed to save pattern memory: {e}")

    def match(self, failure_text: str) -> PatternEntry | None:
        self._ensure_loaded()
        for entry in self._patterns.values():
            try:
                if re.search(entry.regex, failure_text, re.IGNORECASE):
                    return entry
            except re.error:
                continue
        return None

    def record(self, failure_text: str, fix_strategy: str):
        self._ensure_loaded()
        generalized, regex = _generalize(failure_text)

        if generalized in self._patterns:
            entry = self._patterns[generalized]
            entry.count += 1
            entry.last_seen = datetime.now().isoformat()
            # Don't overwrite a successful strategy with a FAILED one
            if not (fix_strategy.startswith("FAILED:") and not entry.fix_strategy.startswith("FAILED:")):
                entry.fix_strategy = fix_strategy
        else:
            self._patterns[generalized] = PatternEntry(
                pattern=generalized,
                regex=regex,
                fix_strategy=fix_strategy,
                first_seen=datetime.now().isoformat(),
                last_seen=datetime.now().isoformat(),
                exemplar=failure_text[:200],
            )
            logger.info(f"[PFM] New pattern: {generalized} -> {fix_strategy}")

        self._save()

    def record_success(self, failure_text: str, fix_strategy: str):
        self.record(failure_text, fix_strategy)

    def record_failure(self, failure_text: str, fix_strategy: str):
        self.record(failure_text, f"FAILED:{fix_strategy}")
        self._save()

    def get_stats(self) -> dict:
        self._ensure_loaded()
        total = len(self._patterns)
        total_fixes = sum(e.count for e in self._patterns.values())
        top = sorted(self._patterns.values(), key=lambda e: e.count, reverse=True)[:10]
        return {
            "total_patterns": total,
            "total_fixes_applied": total_fixes,
            "top_patterns": [{"pattern": e.pattern, "count": e.count, "fix": e.fix_strategy[:40]} for e in top],
        }

    def clear(self):
        self._patterns = {}
        self._save()
        logger.info("[PFM] Pattern memory cleared")


pattern_memory = PatternFailureMemory()
