"""ConsensusScorer — measures cross-source corroboration as a belief quality dimension.

The core insight: a claim supported by 5 independent sources should have
higher confidence than the same claim from only 1 source, even if both
show no contradiction.

    confidence = ... × freshness × consensus

The consensus dimension uses a Beta-Binomial model with a Beta(1,1) prior.
The score is the lower bound of the posterior credible interval, which
penalizes:
  - Single-source claims (no corroboration penalty → ~0.55)
  - Contradictory evidence (mixed sources → intermediate scores)
  - Evenly split evidence (equal support/contradict → low scores)

Usage:
    scorer = ConsensusScorer()
    c1 = scorer.score(supporting=["url1", "url2", "url3"])
    c2 = scorer.score(supporting=["url1"], contradicting=["url2", "url3"])
"""

from __future__ import annotations

import logging
import math

logger = logging.getLogger(__name__)

# Controls how much of the Beta posterior's width is subtracted.
# Higher values produce more conservative scores (lower consensus).
# 0.50 = ~25th percentile, 0.67 = ~17th percentile, 0.84 = ~5th percentile
CREDIBLE_INTERVAL_Z = 0.50

# Score for a single supporting source with no contradicting sources.
# Used directly when total sources == 1.
SINGLE_SOURCE_SCORE = 0.55

# Default consensus when no source data exists (neutral — no penalty).
NO_DATA_DEFAULT = 1.0


class ConsensusScorer:
    """Measures cross-source corroboration for a belief or claim.

    Stateless — all parameters are passed to score().
    """

    def score(
        self,
        supporting_sources: list[str] | None = None,
        contradicting_sources: list[str] | None = None,
    ) -> float:
        """Compute consensus score from supporting and contradicting source lists.

        Uses a Beta-Binomial model:
          alpha = N_support + prior_alpha  (prior_alpha = 1.0)
          beta  = N_contradict + prior_beta  (prior_beta = 1.0)
          mean = alpha / (alpha + beta)
          std  = sqrt(alpha * beta / ((alpha + beta)^2 * (alpha + beta + 1)))
          consensus = mean - z * std

        This gives:
          - Single source with no contradict: ~0.55  (penalized — no corroboration)
          - Multiple sources all agreeing:    → 1.0  (strong corroboration)
          - Evenly split:                    → ~0.43 (low — contested evidence)
          - No data:                         → 1.0  (neutral)
        """
        supporting = supporting_sources or []
        contradicting = contradicting_sources or []
        total = len(supporting) + len(contradicting)

        if total == 0:
            return NO_DATA_DEFAULT

        if total == 1:
            return SINGLE_SOURCE_SCORE

        alpha = len(supporting) + 1.0
        beta = len(contradicting) + 1.0

        mean = alpha / (alpha + beta)
        variance = alpha * beta / ((alpha + beta) ** 2 * (alpha + beta + 1))
        std = math.sqrt(variance)

        consensus = mean - CREDIBLE_INTERVAL_Z * std
        return max(0.0, min(1.0, consensus))

    def score_from_fact_sets(
        self,
        supporting_fact_sources: list[list[str]],
        contradicting_fact_sources: list[list[str]] | None = None,
    ) -> float:
        """Compute consensus from grouped fact source lists.

        Each element in supporting_fact_sources is a list of source IDs
        that support a particular claim variant. Non-overlapping sources
        are treated as independent corroboration.

        Args:
            supporting_fact_sources: list of source-ID lists, one per
                claim variant that agrees with the target claim.
            contradicting_fact_sources: list of source-ID lists, one per
                claim variant that contradicts the target claim.

        Returns:
            Consensus score in [0.0, 1.0].
        """
        supporting_ids: set[str] = set()
        for sources in supporting_fact_sources:
            supporting_ids.update(sources)

        contradicting_ids: set[str] = set()
        if contradicting_fact_sources:
            for sources in contradicting_fact_sources:
                contradicting_ids.update(sources)

        # A source can appear on both sides — remove overlap from both
        overlap = supporting_ids & contradicting_ids
        supporting_ids -= overlap
        contradicting_ids -= overlap

        return self.score(
            supporting_sources=list(supporting_ids),
            contradicting_sources=list(contradicting_ids),
        )

    def dimension_name(self) -> str:
        """Human-readable label for this dimension."""
        return "consensus"

    def dimension_summary(self, score: float) -> str:
        if score >= 0.80:
            return "strong cross-source corroboration"
        if score >= 0.55:
            return "moderate cross-source corroboration"
        if score >= 0.30:
            return "weak cross-source corroboration"
        return "contested evidence"
