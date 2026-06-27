"""UnifiedDecisionModel — produces a single normalized score from evidence.

Combines all evidence dimensions into a weighted final score,
with full traceability via DecisionTrace for debugging and
human-readable explainability.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from core.decision.models import (
    CandidateEvidence,
    DecisionResult,
    EvidenceDimension,
    UnifiedScore,
)

logger = logging.getLogger(__name__)


class UnifiedDecisionModel:
    """Produces one normalized score per candidate from collected evidence.

    Scoring formula::

        final_score = sum(dim.score * dim.weight) / sum(dim.weight)

    Where dimensions with weight=0 are excluded from both numerator and
    denominator, and all scores are clamped to [0.0, 1.0].
    """

    def score(self, evidence: CandidateEvidence) -> UnifiedScore:
        """Score a single candidate from its collected evidence.

        Returns a UnifiedScore with the final score, per-dimension
        breakdown, reasons, and concerns.
        """
        start = time.time()
        dims = evidence.dimensions

        total_weight = sum(d.weight for d in dims if d.weight > 0)
        weighted_sum = sum(d.score * d.weight for d in dims if d.weight > 0)
        final_score = weighted_sum / total_weight if total_weight > 0 else 0.0
        final_score = max(0.0, min(1.0, final_score))

        # Aggregate confidence as weighted average of dimension confidences
        conf_weighted = sum(
            d.confidence * d.weight for d in dims if d.weight > 0 and d.confidence > 0
        )
        conf_total = sum(d.weight for d in dims if d.weight > 0 and d.confidence > 0)
        confidence = conf_weighted / conf_total if conf_total > 0 else 0.0

        # Build reasons (scores above threshold) and concerns (scores below)
        reasons: list[str] = []
        concerns: list[str] = []

        for d in sorted(dims, key=lambda x: x.weight, reverse=True):
            if d.weight <= 0:
                continue
            contribution = d.score * d.weight
            if contribution >= 0.5 * d.weight:
                reasons.append(f"✓ {d.reason}")
            else:
                concerns.append(f"✗ {d.reason}")

        elapsed = (time.time() - start) * 1000.0

        return UnifiedScore(
            template_id=evidence.template_id,
            template_version=evidence.template_version,
            final_score=round(final_score, 4),
            dimensions=list(dims),
            confidence=round(confidence, 4),
            reasons=reasons,
            concerns=concerns,
            elapsed_ms=round(elapsed, 2),
        )

    def rank(self, candidates: list[CandidateEvidence]) -> DecisionResult:
        """Score and rank multiple candidates, returning the best.

        Returns a DecisionResult with the selected candidate and all
        alternatives, ordered by final_score descending.
        """
        start = time.time()
        scored = [self.score(c) for c in candidates]
        scored.sort(key=lambda s: s.final_score, reverse=True)

        selected = scored[0] if scored else None
        alternatives = scored[1:] if len(scored) > 1 else []

        elapsed = (time.time() - start) * 1000.0

        return DecisionResult(
            selected=selected,
            alternatives=alternatives,
            total_candidates=len(candidates),
            elapsed_ms=round(elapsed, 2),
        )


class DecisionTrace:
    """Formats decision results for human-readable output.

    Produces structured trace output showing why one candidate was
    selected over alternatives, with per-dimension breakdowns.
    """

    @staticmethod
    def format(result: DecisionResult) -> str:
        """Format a DecisionResult as a human-readable trace string."""
        if result.selected is None:
            return "No candidates available for selection."

        lines: list[str] = []
        s = result.selected

        lines.append(f"Selected: {s.template_id} v{s.template_version}")
        lines.append(f"Score: {s.final_score:.2f}")
        lines.append(f"Confidence: {s.confidence:.0%}")
        lines.append("")

        if s.reasons:
            lines.append("Reasons:")
            for r in s.reasons:
                lines.append(f"  {r}")
            lines.append("")

        if s.concerns:
            lines.append("Concerns:")
            for c in s.concerns:
                lines.append(f"  {c}")
            lines.append("")

        if result.alternatives:
            lines.append("Rejected:")
            for alt in result.alternatives:
                lines.append(
                    f"  {alt.template_id} v{alt.template_version} "
                    f"— Score: {alt.final_score:.2f}"
                )
                top_reason = next(
                    (r for r in alt.reasons if r.startswith("✓")),
                    alt.concerns[0] if alt.concerns else "No data",
                )
                lines.append(f"    {top_reason}")
            lines.append("")

        lines.append(f"Decision computed in {result.elapsed_ms:.0f}ms "
                      f"across {result.total_candidates} candidate(s).")
        return "\n".join(lines)

    @staticmethod
    def format_dimensions(score: UnifiedScore) -> str:
        """Format just the dimension breakdown for debugging."""
        lines: list[str] = []
        lines.append(f"Dimensions for {score.template_id} v{score.template_version}:")
        for d in sorted(score.dimensions, key=lambda x: x.weight, reverse=True):
            if d.weight > 0:
                contrib = d.score * d.weight
                lines.append(
                    f"  {d.name:25s} score={d.score:.2f}  "
                    f"weight={d.weight:.2f}  contrib={contrib:.2f}  "
                    f"conf={d.confidence:.0%}"
                )
        lines.append(f"  {'FINAL':25s} score={score.final_score:.4f}  "
                      f"conf={score.confidence:.0%}")
        return "\n".join(lines)
