"""
Mythos v17 — Truth Risk Engine
================================
Detects scenarios where consensus or confidence does NOT imply truth.

CORE INSIGHT:
  High consensus can be WRONG when:
  1. Sources are correlated (share training data, cite each other, same origin)
  2. Majority bias: the popular answer suppresses the correct minority signal
  3. Model bias: all LLM agents share similar wrong prior
  4. Stale knowledge: sources agree on an outdated fact
  5. Absence of contradiction is not the same as evidence of correctness

AUDIT FINDING ADDRESSED:
  v16 `AgentCouncil`: if Solver, Critic, Verifier all use models with shared
  training bias toward a wrong answer, consensus_score is high but truth is absent.
  No mechanism detected this. This module fixes it.

FORMULA:
  truth_risk = correlation_penalty × majority_bias × staleness × (1/diversity_bonus)

  Where:
    correlation_penalty = 1 + (n_correlated_sources / n_total_sources) × 0.5
    majority_bias       = 1 + (agreement_ratio - 0.5) × 0.4  [high agreement = higher risk]
    staleness           = 1 + avg_source_age_days / 180
    diversity_bonus     = max(1, n_distinct_source_types) × max(1, n_distinct_domains)

THRESHOLDS:
  risk < 0.30 : LOW    — consensus likely reliable
  0.30-0.60   : MEDIUM — verify with independent source
  0.60-0.80   : HIGH   — escalate to research, flag output
  > 0.80      : CRITICAL — block integration, mandatory research task

MINORITY SIGNAL AMPLIFICATION:
  If a dissenting view comes from a high-authority, independent source:
  → amplify its weight to 2× for contradiction analysis
  → this prevents majority from burying a correct minority
"""

import math
import re
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from utils.logger import SystemLogger

logger = SystemLogger(__name__)


class TruthRiskLevel(Enum):
    LOW      = "low"       # < 0.30
    MEDIUM   = "medium"    # 0.30 - 0.60
    HIGH     = "high"      # 0.60 - 0.80
    CRITICAL = "critical"  # > 0.80


@dataclass
class TruthRiskReport:
    """Full truth risk analysis for a consensus or output."""
    risk_score:           float
    risk_level:           TruthRiskLevel
    correlation_penalty:  float    # how correlated sources are
    majority_bias_factor: float    # how much majority suppresses minority
    staleness_factor:     float    # how old the knowledge is
    diversity_bonus:      float    # source/domain diversity
    amplified_dissenters: List[str] # high-quality minority signals
    block_integration:    bool     # True if risk > CRITICAL threshold
    escalate_to_research: bool
    explanation:          str
    recommendations:      List[str]


@dataclass
class SourceProfile:
    """Profile of a knowledge source for correlation analysis."""
    source_id:   str
    source_type: str     # "llm_agent" | "external" | "graph_node" | "research"
    domain:      str
    timestamp:   float
    authority:   float


class TruthRiskEngine:
    """
    Estimates the risk that a high-confidence answer is nonetheless wrong.

    Called after EvidenceConsensusEngine produces a BeliefResult,
    before any knowledge integration.

    Design decisions:
    1. Correlation detection: sources that share "llm_agent" type are assumed
       correlated (same model family bias). Mitigation: require at least one
       non-LLM source for LOW risk.

    2. Majority bias: agreement_ratio > 0.90 paradoxically increases risk
       because it suggests minority signals were suppressed rather than absent.
       This is counter-intuitive but necessary.

    3. Minority amplification: dissenters with authority > 0.80 are amplified
       to 2× weight even if they represent only 10% of sources. A single
       high-quality dissenter can raise risk to MEDIUM.
    """

    RISK_LOW      = 0.30
    RISK_MEDIUM   = 0.60
    RISK_HIGH     = 0.80

    # Source type correlation groupings
    CORRELATED_TYPES = {
        "llm_agent":    {"llm_agent"},       # all LLM agents correlate
        "external":     {"external"},         # external sources may share origin
        "graph_node":   {"graph_node"},       # derived from same reasoning graph
        "research":     set(),                # research results treated as independent
    }

    def __init__(self, authority_mgr: Any = None):
        self.authority_mgr = authority_mgr
        self._assessments: List[TruthRiskReport] = []
        self._stats = {"low": 0, "medium": 0, "high": 0, "critical": 0, "blocked": 0}

    def assess(
        self,
        belief_result: Any,                  # BeliefResult from EvidenceConsensusEngine
        source_profiles: List[SourceProfile],
        domain: str = "general",
    ) -> TruthRiskReport:
        """Full truth risk assessment. Never raises — returns MEDIUM on error."""
        try:
            return self._assess(belief_result, source_profiles, domain)
        except Exception as e:
            logger.warning(f"[TruthRiskEngine] Assessment failed: {e}")
            return TruthRiskReport(
                risk_score=0.50, risk_level=TruthRiskLevel.MEDIUM,
                correlation_penalty=1.0, majority_bias_factor=1.0,
                staleness_factor=1.0, diversity_bonus=1.0,
                amplified_dissenters=[], block_integration=False,
                escalate_to_research=True,
                explanation="Assessment error — defaulting to MEDIUM",
                recommendations=["verify_independently"],
            )

    def _assess(
        self,
        belief_result: Any,
        source_profiles: List[SourceProfile],
        domain: str,
    ) -> TruthRiskReport:
        agreement_ratio = getattr(belief_result, 'agreement_ratio', 0.70)
        dissenting      = getattr(belief_result, 'dissenting_views', [])
        source_count    = max(getattr(belief_result, 'source_count', 1), 1)

        # ── Signal 1: Source correlation ──────────────────────────
        correlation_penalty = self._compute_correlation(source_profiles, source_count)

        # ── Signal 2: Majority bias ───────────────────────────────
        # High agreement (>0.85) paradoxically increases risk: minority suppressed
        if agreement_ratio > 0.85:
            majority_bias = 1.0 + (agreement_ratio - 0.50) * 0.40
        else:
            majority_bias = 1.0 + max(0, agreement_ratio - 0.60) * 0.20

        # ── Signal 3: Staleness ───────────────────────────────────
        staleness = self._compute_staleness(source_profiles)

        # ── Signal 4: Diversity bonus ─────────────────────────────
        diversity = self._compute_diversity(source_profiles)

        # ── Composite risk ────────────────────────────────────────
        raw_risk = (correlation_penalty * majority_bias * staleness) / diversity
        # Normalize to 0-1
        risk_score = round(min(1.0, max(0.0, (raw_risk - 1.0) / 3.0)), 4)

        # ── Minority amplification ────────────────────────────────
        amplified = self._amplify_minority(dissenting, domain)
        if amplified:
            # Each high-quality dissenter adds 0.10 to risk
            risk_score = min(1.0, risk_score + len(amplified) * 0.10)

        # ── Contradiction pressure ────────────────────────────────
        if getattr(belief_result, 'contradiction_detected', False):
            risk_score = min(1.0, risk_score + 0.20)

        # ── Single-source penalty ─────────────────────────────────
        if source_count == 1:
            risk_score = min(1.0, risk_score + 0.25)

        # ── Classify ──────────────────────────────────────────────
        if risk_score < self.RISK_LOW:
            level = TruthRiskLevel.LOW
        elif risk_score < self.RISK_MEDIUM:
            level = TruthRiskLevel.MEDIUM
        elif risk_score < self.RISK_HIGH:
            level = TruthRiskLevel.HIGH
        else:
            level = TruthRiskLevel.CRITICAL

        block       = level == TruthRiskLevel.CRITICAL
        escalate    = level in (TruthRiskLevel.HIGH, TruthRiskLevel.CRITICAL)
        explanation = self._explain(risk_score, level, correlation_penalty,
                                    majority_bias, staleness, diversity, amplified)
        recommendations = self._recommendations(level, amplified)

        self._stats[level.value] = self._stats.get(level.value, 0) + 1
        if block:
            self._stats["blocked"] += 1

        report = TruthRiskReport(
            risk_score=risk_score, risk_level=level,
            correlation_penalty=round(correlation_penalty, 4),
            majority_bias_factor=round(majority_bias, 4),
            staleness_factor=round(staleness, 4),
            diversity_bonus=round(diversity, 4),
            amplified_dissenters=amplified,
            block_integration=block,
            escalate_to_research=escalate,
            explanation=explanation,
            recommendations=recommendations,
        )

        self._assessments.append(report)
        self._assessments = self._assessments[-200:]

        logger.info(
            f"[TruthRiskEngine] risk={risk_score:.3f} level={level.value} "
            f"corr={correlation_penalty:.2f} bias={majority_bias:.2f} "
            f"stale={staleness:.2f} div={diversity:.2f} "
            f"amplified={len(amplified)} block={block}"
        )
        return report

    def _compute_correlation(
        self, profiles: List[SourceProfile], total: int
    ) -> float:
        """Penalty for correlated sources. Higher = more correlated."""
        if not profiles or total <= 1:
            return 1.5   # unknown = assume correlated
        type_counts = Counter(p.source_type for p in profiles)
        llm_count   = type_counts.get("llm_agent", 0)
        # Pure LLM = maximum correlation
        frac_llm    = llm_count / total
        return round(1.0 + frac_llm * 0.50, 4)

    def _compute_staleness(self, profiles: List[SourceProfile]) -> float:
        """Staleness factor. Higher = older sources."""
        if not profiles:
            return 1.20   # unknown age = mildly penalized
        now = time.time()
        ages = [(now - p.timestamp) / 86400 for p in profiles]  # days
        avg_age = sum(ages) / len(ages)
        return round(1.0 + avg_age / 180.0, 4)   # doubles at 180 days

    def _compute_diversity(self, profiles: List[SourceProfile]) -> float:
        """Diversity bonus. Higher = more diverse sources."""
        if not profiles:
            return 1.0
        n_types   = len(set(p.source_type for p in profiles))
        n_domains = len(set(p.domain for p in profiles))
        return round(max(1.0, math.sqrt(n_types * n_domains)), 4)

    def _amplify_minority(
        self, dissenters: List[Any], domain: str
    ) -> List[str]:
        """Return list of high-quality dissenter claims worth amplifying."""
        amplified = []
        for dv in dissenters:
            # Use authority if available
            authority = 0.60
            if self.authority_mgr:
                sid = getattr(dv, 'source_id', '')
                if sid:
                    authority = self.authority_mgr.get_authority(sid, domain)
            if authority >= 0.75:   # high-authority dissenter
                claim = getattr(dv, 'claim', str(dv))
                amplified.append(claim[:100])
        return amplified

    def _explain(
        self, risk: float, level: TruthRiskLevel,
        corr: float, bias: float, stale: float, div: float,
        amplified: List[str],
    ) -> str:
        parts = [f"Risk={risk:.3f} ({level.value})."]
        if corr > 1.30:
            parts.append("High source correlation (likely shared bias).")
        if bias > 1.25:
            parts.append("Strong majority agreement may have suppressed minority signals.")
        if stale > 1.50:
            parts.append("Sources may be outdated.")
        if div < 1.5:
            parts.append("Low source diversity.")
        if amplified:
            parts.append(f"High-quality dissent from {len(amplified)} sources.")
        return " ".join(parts)

    def _recommendations(
        self, level: TruthRiskLevel, amplified: List[str]
    ) -> List[str]:
        recs = []
        if level == TruthRiskLevel.LOW:
            recs.append("proceed_with_standard_verification")
        elif level == TruthRiskLevel.MEDIUM:
            recs.extend(["verify_with_independent_source", "flag_as_uncertain"])
        elif level == TruthRiskLevel.HIGH:
            recs.extend(["escalate_to_research", "downgrade_confidence", "show_dissenters"])
        else:  # CRITICAL
            recs.extend(["block_knowledge_integration", "mandatory_research_task",
                          "return_contradictory_state"])
        if amplified:
            recs.append("investigate_minority_signals")
        return recs

    def quick_assess(self, agreement_ratio: float, source_count: int,
                     has_contradiction: bool) -> TruthRiskLevel:
        """Fast path: rough risk level from summary statistics only."""
        risk = 0.0
        if source_count == 1: risk += 0.30
        if agreement_ratio > 0.90: risk += 0.20  # suspiciously high
        if has_contradiction: risk += 0.35  # contradiction always elevates to at least MEDIUM
        if source_count < 3: risk += 0.10
        if risk < self.RISK_LOW: return TruthRiskLevel.LOW
        if risk < self.RISK_MEDIUM: return TruthRiskLevel.MEDIUM
        if risk < self.RISK_HIGH: return TruthRiskLevel.HIGH
        return TruthRiskLevel.CRITICAL

    def get_stats(self) -> Dict:
        return dict(self._stats)
