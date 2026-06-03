"""Self-grading pipeline with auto-correction loop and constitutional memory."""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import logging
from typing import Callable, Optional


@dataclass
class CriterionResult:
    id: str
    description: str
    passed: bool
    score: float
    evidence: str
    weight: float


@dataclass
class GradeResult:
    criteria: list[CriterionResult]
    aggregate_score: float
    output_type: str

    @property
    def passed(self) -> bool:
        return self.aggregate_score >= QualityGrader.THRESHOLD

    def failed_criteria(self) -> list[CriterionResult]:
        return [c for c in self.criteria if not c.passed]


logger = logging.getLogger(__name__)


class QualityGrader:
    THRESHOLD = 85.0
    MAX_CONTENT_CHARS = 4000

    def __init__(self, constitution_path: str, llm_router,
                 cm: Optional["ConstitutionalMemory"] = None):
        with open(constitution_path) as f:
            self.constitution = json.load(f)
        self.router = llm_router
        self.cm = cm

    async def grade(self, output_type: str, content: str) -> GradeResult:
        criteria = self.constitution.get(output_type, [])
        if not criteria:
            raise ValueError(f"Unknown output_type: {output_type}")

        max_chars = self.MAX_CONTENT_CHARS
        truncated = content if len(content) <= max_chars else content[:max_chars] + "\n...[truncated]"

        prompt = (
            f"Grade this {output_type} against each criterion. "
            f"Return ONLY valid JSON with no preamble:\n"
            f'{{criterion_id: {{"pass": bool, "score": 0-100, "evidence": "..."}}}}\n\n'
            f"Criteria:\n{json.dumps(criteria, indent=2)}\n\n"
            f"Content to grade:\n{truncated}"
        )

        raw_r = await self.router.complete(
            "grader",
            [{"role": "user", "content": prompt}]
        )
        raw = raw_r.unwrap_or("{}")

        try:
            grades = json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            grades = json.loads(match.group()) if match else {}

        results = []
        for c in criteria:
            g = grades.get(c["id"], {})
            results.append(CriterionResult(
                id=c["id"],
                description=c["description"],
                passed=g.get("pass", False),
                score=float(g.get("score", 0)),
                evidence=g.get("evidence", "No evidence"),
                weight=c["weight"]
            ))

        aggregate = sum(r.score * r.weight for r in results)
        result = GradeResult(criteria=results, aggregate_score=aggregate,
                              output_type=output_type)
        if self.cm:
            self.cm.log(result)
        return result

    async def grade_and_correct(self,
                                 output_type: str,
                                 content: str,
                                 generator_fn: Callable,
                                 input_query: str = "") -> str:
        MAX_CORRECTIONS = 3
        corrections = []
        for attempt in range(MAX_CORRECTIONS):
            grade = await self.grade(output_type, content)
            if grade.aggregate_score >= self.THRESHOLD:
                try:
                    from learning.training_collector import TrainingCollector
                    TrainingCollector().log(
                        input=input_query or content[:200],
                        output=content,
                        grade=grade.aggregate_score,
                        accepted=True,
                        domain=output_type,
                        corrections=corrections or None,
                    )
                except Exception as e:
                    logger.exception("[Grader] TrainingCollector.log failed: %s", e)
                return content
            failed = grade.failed_criteria()
            fix_instructions = [
                f"- {c.id} ({c.description}): {c.evidence}" for c in failed
            ]
            corrections.append(f"Attempt {attempt + 1}: {len(failed)} failures")
            content = await generator_fn(
                fix_instructions=fix_instructions,
                previous_content=content,
                attempt=attempt + 1
            )

        try:
            from learning.training_collector import TrainingCollector
            final_grade = (await self.grade(output_type, content)).aggregate_score
            TrainingCollector().log(
                input=input_query or content[:200],
                output=content,
                grade=final_grade,
                accepted=final_grade >= self.THRESHOLD,
                domain=output_type,
                corrections=corrections or None,
            )
        except Exception as e:
            logger.exception("[Grader] Final training log failed: %s", e)
        return content


class ConstitutionalMemory:
    DB_PATH = Path.home() / ".jarvis" / "constitutional_memory.db"

    def __init__(self):
        self.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.DB_PATH) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS grade_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    output_type TEXT,
                    criterion_id TEXT,
                    passed BOOLEAN,
                    score REAL,
                    correction_applied TEXT,
                    created_at TEXT
                )
            """)

    def log(self, grade: GradeResult,
             correction: str = None) -> None:
        now = datetime.utcnow().isoformat()
        with sqlite3.connect(self.DB_PATH) as conn:
            for c in grade.criteria:
                conn.execute("""
                    INSERT INTO grade_history
                    (output_type, criterion_id, passed, score, correction_applied, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (grade.output_type, c.id, c.passed, c.score,
                      correction, now))

    def failure_patterns(self, output_type: str,
                          min_entries: int = 100) -> dict[str, float]:
        with sqlite3.connect(self.DB_PATH) as conn:
            total = conn.execute(
                "SELECT COUNT(*) FROM grade_history WHERE output_type=?",
                (output_type,)
            ).fetchone()[0]
            if total < min_entries:
                return {}
            rows = conn.execute("""
                SELECT criterion_id, AVG(CASE WHEN passed=0 THEN 1.0 ELSE 0.0 END)
                FROM grade_history WHERE output_type=?
                GROUP BY criterion_id
            """, (output_type,)).fetchall()
        return {cid: rate for cid, rate in rows if rate > 0.3}
