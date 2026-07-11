"""ResearchReflection — after-activity analysis and pattern learning.

Analyzes completed research activities to discover what strategies
worked, what didn't, and what should change in future activities.

Primary storage: ``research_reflections`` and ``research_patterns`` tables
in ``system.db``, with JSON fallback for backward compatibility.

Deprecated JSON path: ``data/research_reflections.json``
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from core.research.evidence_tracker import ResearchCoverage
from core.storage.registry import SYSTEM_DB, ensure_db_dir

logger = logging.getLogger(__name__)

_DEFAULT_MEMORY_PATH = str(Path("data") / "research_reflections.json")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS research_reflections (
    id          TEXT PRIMARY KEY,
    activity_id TEXT NOT NULL,
    data        TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS research_patterns (
    pattern_id  TEXT PRIMARY KEY,
    data        TEXT NOT NULL
);
"""


@dataclass
class ReflectionResult:
    """Result of reflecting on a completed research activity."""
    reflection_id: str
    activity_id: str
    question: str
    strategies_used: list[str]
    total_facts_collected: int
    total_sources: int
    goals_answered: int
    goals_total: int
    contradictions_found: int
    overall_confidence: float
    iterations_needed: int
    success_rating: float  # 0.0 – 1.0
    lessons: list[str]
    patterns: list[str]
    timestamp: str


@dataclass
class LearnedPattern:
    """A reusable pattern learned from research experience."""
    pattern_id: str
    description: str
    conditions: list[str]  # When this pattern applies
    action: str  # What to do
    success_rate: float
    usage_count: int
    created_at: str


class ResearchReflection:
    """Analyzes completed research and extracts learning patterns.

    Stores reflections in a JSON file for persistence across sessions.
    Patterns accumulate over time and can be queried by the planner.

    Usage:
        reflection = ResearchReflection()
        result = reflection.analyze(activity_id, question, plan, facts, coverage)
        patterns = reflection.get_patterns_for_question("pricing")
    """

    def __init__(self, memory_path: str | None = None):
        self._path = Path(memory_path or _DEFAULT_MEMORY_PATH)
        self._reflections: list[ReflectionResult] = []
        self._patterns: list[LearnedPattern] = []
        self._load()

    # ── Reflection ───────────────────────────────────────────────────

    def analyze(self, activity_id: str,
                question: str,
                plan_summary: dict[str, Any],
                facts_count: int,
                coverage: ResearchCoverage | None = None) -> ReflectionResult:
        """Analyze a completed research activity and extract lessons."""
        contradictions = plan_summary.get("contradictions_found", 0)
        total_facts = coverage.total_facts if coverage else facts_count
        answered = coverage.covered_goals if coverage else 0
        total_goals = coverage.total_goals if coverage else 1
        confidence = coverage.overall_confidence if coverage else 0.5
        iterations = plan_summary.get("iteration", 1)
        sources = self._estimate_sources(plan_summary)

        # Determine strategies used
        strategies = self._detect_strategies(plan_summary)

        # Success rating
        success_rating = self._compute_success_rating(
            answered=answered,
            total=total_goals,
            confidence=confidence,
            contradictions=contradictions,
            sources=sources,
        )

        # Lessons learned
        lessons = self._generate_lessons(
            strategies=strategies,
            success_rating=success_rating,
            contradictions=contradictions,
            sources=sources,
            answered_ratio=answered / max(total_goals, 1),
        )

        # Patterns extracted
        patterns = self._extract_patterns(
            strategies=strategies,
            success_rating=success_rating,
            sources=sources,
        )

        # Store new patterns
        for pattern_desc in patterns:
            self._add_pattern(
                description=pattern_desc,
                conditions=strategies,
                action="Continue using these strategies",
                success=success_rating >= 0.6,
            )

        result = ReflectionResult(
            reflection_id=f"ref_{uuid.uuid4().hex[:12]}",
            activity_id=activity_id,
            question=question,
            strategies_used=strategies,
            total_facts_collected=total_facts,
            total_sources=sources,
            goals_answered=answered,
            goals_total=total_goals,
            contradictions_found=contradictions,
            overall_confidence=round(confidence, 2),
            iterations_needed=iterations,
            success_rating=round(success_rating, 2),
            lessons=lessons,
            patterns=patterns,
            timestamp=datetime.utcnow().isoformat(),
        )

        self._reflections.append(result)
        self._save()
        return result

    def get_patterns(self) -> list[LearnedPattern]:
        """Get all learned patterns."""
        return sorted(self._patterns, key=lambda p: p.success_rate, reverse=True)

    def get_patterns_for_question(self, question_type: str) -> list[LearnedPattern]:
        """Get patterns relevant to a question type."""
        return [p for p in self._patterns
                if any(question_type in c.lower() for c in p.conditions)]

    def get_recent_reflections(self, limit: int = 10) -> list[ReflectionResult]:
        """Get the most recent reflections."""
        return sorted(
            self._reflections,
            key=lambda r: r.timestamp,
            reverse=True,
        )[:limit]

    def get_statistics(self) -> dict[str, Any]:
        """Return reflection statistics."""
        if not self._reflections:
            return {"total_reflections": 0, "total_patterns": len(self._patterns)}

        avg_success = sum(r.success_rating for r in self._reflections) / len(self._reflections)
        return {
            "total_reflections": len(self._reflections),
            "total_patterns": len(self._patterns),
            "average_success_rating": round(avg_success, 2),
            "high_success_count": sum(1 for r in self._reflections if r.success_rating >= 0.7),
            "low_success_count": sum(1 for r in self._reflections if r.success_rating < 0.3),
            "top_patterns": [
                {"description": p.description, "success_rate": p.success_rate}
                for p in sorted(self._patterns, key=lambda x: x.success_rate, reverse=True)[:5]
            ],
        }

    # ── Internals ─────────────────────────────────────────────────────

    def _detect_strategies(self, plan: dict[str, Any]) -> list[str]:
        """Detect what research strategies were used."""
        strategies: list[str] = []

        if plan.get("iteration", 1) > 1:
            strategies.append("multi_iteration")
        if plan.get("total_facts", 0) >= 5:
            strategies.append("high_volume_extraction")
        if plan.get("sources_count", 0) >= 2:
            strategies.append("multi_source")
        if plan.get("contradictions_found", 0) > 0:
            strategies.append("contradiction_detection")

        if not strategies:
            strategies.append("single_pass")

        return strategies

    def _compute_success_rating(self, answered: int, total: int,
                                 confidence: float, contradictions: int,
                                 sources: int) -> float:
        """Compute a success rating from 0.0 to 1.0."""
        if total == 0:
            return 0.0

        goal_ratio = answered / total
        source_bonus = min(0.2, sources * 0.05)
        confidence_weight = confidence * 0.3
        contradiction_penalty = min(0.3, contradictions * 0.1)

        score = (goal_ratio * 0.5) + source_bonus + confidence_weight - contradiction_penalty
        return max(0.0, min(1.0, score))

    def _generate_lessons(self, strategies: list[str],
                           success_rating: float,
                           contradictions: int,
                           sources: int,
                           answered_ratio: float) -> list[str]:
        """Generate human-readable lessons from the analysis."""
        lessons: list[str] = []

        if "multi_source" in strategies and success_rating >= 0.6:
            lessons.append(
                f"Using {sources} sources improved answer quality "
                f"(success: {success_rating:.0%})."
            )

        if "multi_iteration" in strategies and success_rating >= 0.6:
            lessons.append(
                "Multiple research iterations helped fill knowledge gaps."
            )

        if contradictions > 0:
            lessons.append(
                f"Found {contradictions} contradictions — "
                f"needs resolution before finalizing."
            )

        if sources == 1 and answered_ratio < 0.5:
            lessons.append(
                "Single source insufficient for reliable answers — "
                "add more sources next time."
            )

        if "single_pass" in strategies and answered_ratio < 0.5:
            lessons.append(
                "Single-pass research insufficient — "
                "use iterative refinement next time."
            )

        if not lessons:
            lessons.append("Basic research completed without notable issues.")

        return lessons

    def _extract_patterns(self, strategies: list[str],
                           success_rating: float,
                           sources: int) -> list[str]:
        """Extract reusable patterns from the analysis."""
        patterns: list[str] = []

        if sources >= 2 and success_rating >= 0.6:
            patterns.append(
                "Multi-source research correlates with higher success"
            )

        if "multi_iteration" in strategies and success_rating >= 0.6:
            patterns.append(
                "Iterative refinement improves answer completeness"
            )

        if "contradiction_detection" in strategies:
            patterns.append(
                "Contradiction detection prevents premature conclusions"
            )

        return patterns

    def _add_pattern(self, description: str, conditions: list[str],
                     action: str, success: bool) -> None:
        """Add or update a learned pattern."""
        existing = [p for p in self._patterns if p.description == description]

        if existing:
            pattern = existing[0]
            pattern.usage_count += 1
            if success:
                pattern.success_rate = min(1.0, pattern.success_rate + 0.1)
            else:
                pattern.success_rate = max(0.0, pattern.success_rate - 0.1)
        else:
            self._patterns.append(LearnedPattern(
                pattern_id=f"pat_{uuid.uuid4().hex[:8]}",
                description=description,
                conditions=conditions,
                action=action,
                success_rate=0.7 if success else 0.3,
                usage_count=1,
                created_at=datetime.utcnow().isoformat(),
            ))

    def _estimate_sources(self, plan: dict[str, Any]) -> int:
        """Estimate the number of distinct sources from plan data."""
        facts = plan.get("total_facts_collected", 0)
        if facts >= 5:
            return 3
        elif facts >= 3:
            return 2
        return 1

    # ── Persistence ──────────────────────────────────────────────────

    def _load(self) -> None:
        """Load from SQLite, fall back to JSON."""
        ensure_db_dir(SYSTEM_DB)
        try:
            with sqlite3.connect(SYSTEM_DB) as conn:
                conn.executescript(_SCHEMA)
                ref_rows = conn.execute("SELECT data FROM research_reflections").fetchall()
                pat_rows = conn.execute("SELECT data FROM research_patterns").fetchall()
                if ref_rows or pat_rows:
                    self._reflections = [
                        ReflectionResult(**json.loads(r[0])) for r in ref_rows
                    ]
                    self._patterns = [
                        LearnedPattern(**json.loads(p[0])) for p in pat_rows
                    ]
                    return
        except Exception as e:
            logger.warning("Failed to load research reflections from SQLite: %s", e)

        # Fallback: JSON file
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            self._reflections = [
                ReflectionResult(**r) for r in data.get("reflections", [])
            ]
            self._patterns = [
                LearnedPattern(**p) for p in data.get("patterns", [])
            ]
            self._save()  # Migrate to SQLite
        except Exception as e:
            logger.warning("Failed to load research reflections from JSON: %s", e)

    def _save(self) -> None:
        """Persist to SQLite (+ JSON fallback)."""
        try:
            with sqlite3.connect(SYSTEM_DB) as conn:
                conn.executescript(_SCHEMA)
                conn.execute("DELETE FROM research_reflections")
                conn.execute("DELETE FROM research_patterns")
                for r in self._reflections:
                    conn.execute(
                        "INSERT INTO research_reflections (id, activity_id, data) VALUES (?, ?, ?)",
                        (r.reflection_id, r.activity_id, json.dumps(r.__dict__, default=str)),
                    )
                for p in self._patterns:
                    conn.execute(
                        "INSERT INTO research_patterns (pattern_id, data) VALUES (?, ?)",
                        (p.pattern_id, json.dumps(p.__dict__, default=str)),
                    )
                conn.commit()
        except Exception as e:
            logger.warning("ResearchReflection: SQLite save failed, falling back to JSON: %s", e)
            self._path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "reflections": [
                    {k: v for k, v in r.__dict__.items() if not k.startswith("_")}
                    for r in self._reflections
                ],
                "patterns": [
                    {k: v for k, v in p.__dict__.items() if not k.startswith("_")}
                    for p in self._patterns
                ],
            }
            self._path.write_text(
                json.dumps(data, indent=2, default=str),
                encoding="utf-8",
            )
