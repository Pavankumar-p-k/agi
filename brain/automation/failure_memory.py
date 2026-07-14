from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class KnownFix:
    error_signature: str
    cause: str
    fix_type: str
    fix_params: dict
    count: int = 1


class FailureMemory:
    """Pattern-based failure memory with automatic generalization.

    On store: normalizes error -> stores exact match -> auto-generalizes by
    replacing capitalized identifiers and numbers with wildcard patterns.

    On lookup: exact match -> prefix match -> pattern match (most specific first).

    Over time, 'cannot resolve symbol Button' + 'cannot resolve symbol TextView'
    merge into one learned pattern: 'cannot resolve symbol \\w+' -> add_import.
    """

    def __init__(self, db_path: str = ""):
        if db_path:
            self.db_path = db_path
        else:
            from core.storage import SYSTEM_DB
            self.db_path = SYSTEM_DB
        _db_dir = os.path.dirname(self.db_path)
        if _db_dir:
            os.makedirs(_db_dir, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS failure_memory (
                error_signature TEXT PRIMARY KEY,
                pattern TEXT,
                cause TEXT,
                fix_type TEXT,
                fix_params TEXT,
                count INTEGER DEFAULT 1,
                last_seen REAL
            )
        """)
        self._conn.commit()
        self._exact: dict[str, KnownFix] = {}
        self._patterns: list[tuple[re.Pattern, KnownFix]] = []
        self._load_cache()

    def _load_cache(self):
        try:
            rows = self._conn.execute(
                "SELECT error_signature, pattern, cause, fix_type, fix_params, count FROM failure_memory"
            ).fetchall()
            for sig, pattern_str, cause, fix_type, fix_params_json, count in rows:
                fix = KnownFix(sig, cause, fix_type, json.loads(fix_params_json), count)
                if pattern_str:
                    try:
                        self._patterns.append((re.compile(pattern_str), fix))
                    except re.error:
                        self._exact[sig] = fix
                else:
                    self._exact[sig] = fix
        except Exception:
            pass

    def lookup(self, error_text: str) -> KnownFix | None:
        """Find known fix -- exact -> prefix -> pattern (most specific first)."""
        sig = self._normalize(error_text)
        if sig in self._exact:
            return self._exact[sig]
        for known_sig, fix in self._exact.items():
            if sig.startswith(known_sig) or known_sig.startswith(sig):
                return fix
        sorted_pats = sorted(
            self._patterns,
            key=lambda p: (p[0].pattern.count(r'\w+') + p[0].pattern.count(r'\d+'),
                           -len(p[0].pattern)),
        )
        for pattern, fix in sorted_pats:
            m = pattern.search(error_text)
            if m:
                filled = dict(fix.fix_params)
                for k, v in m.groupdict().items():
                    filled[k] = v
                return KnownFix(fix.error_signature, fix.cause, fix.fix_type, filled, fix.count)
        return None

    def store(self, error_text: str, cause: str, fix_type: str, fix_params: dict):
        sig = self._normalize(error_text)
        existing = self._exact.get(sig)
        if existing:
            existing.count += 1
            self._update_db(sig, None, existing)
            return

        fix = KnownFix(sig, cause, fix_type, fix_params)
        self._exact[sig] = fix
        self._update_db(sig, None, fix)

        pattern_info = self._generalize(sig, fix_params)
        if pattern_info:
            pattern_str, compiled = pattern_info
            dup = any(p.pattern == pattern_str for p, _ in self._patterns)
            if not dup:
                self._patterns.append((compiled, fix))
                self._update_db(sig, pattern_str, fix)
                FailureMemory._generalization_count += 1
                logger.info("[PatternMemory] generalized: %s -> %s", sig[:60], pattern_str)

    _generalization_count = 0

    def _generalize(self, normalized_sig: str, fix_params: dict) -> tuple[str, re.Pattern] | None:
        """Replace variable parts (from fix_params) with named regex groups."""
        generalized = normalized_sig
        for key, value in fix_params.items():
            if isinstance(value, str) and len(value) >= 2:
                vlow = value.lower()
                if vlow in generalized:
                    if re.match(r'^[a-zA-Z][\w.]*$', value):
                        generalized = generalized.replace(vlow, rf'(?P<{key}>[\w.]+)', 1)
                    elif re.match(r'^\d+$', value):
                        generalized = generalized.replace(vlow, rf'(?P<{key}>\d+)', 1)
        if generalized != normalized_sig and len(generalized) > 15:
            try:
                return (generalized, re.compile(generalized, re.I))
            except re.error:
                pass
        generalized = re.sub(r'\b[A-Z][a-zA-Z0-9]*\b', r'\\w+', normalized_sig)
        generalized = re.sub(r'\b\d+\b', r'\\d+', generalized)
        if generalized != normalized_sig and len(generalized) > 15:
            try:
                return (generalized, re.compile(generalized, re.I))
            except re.error:
                pass
        return None

    def _update_db(self, sig: str, pattern_str: str | None, fix: KnownFix):
        try:
            self._conn.execute(
                "INSERT OR REPLACE INTO failure_memory (error_signature, pattern, cause, fix_type, fix_params, count, last_seen) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (sig, pattern_str or "", fix.cause, fix.fix_type, json.dumps(fix.fix_params), fix.count, time.time()),
            )
            self._conn.commit()
        except Exception:
            pass

    def _normalize(self, text: str) -> str:
        t = text.lower().strip()
        t = re.sub(r'\bline\s+\d+\b', 'line N', t)
        t = re.sub(r':\d+:', ':N:', t)
        t = re.sub(r'\s+', ' ', t)
        return t[:200]

    def close(self):
        if self._conn:
            self._conn.close()
