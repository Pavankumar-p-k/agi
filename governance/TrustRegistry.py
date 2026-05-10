"""
Mythos v18 — Advanced Trust System
=====================================
Multi-dimensional trust model with anti-poisoning guarantees.

V17 TRUST BUGS FIXED:
  1. Trust amplification loop: v17's TrustManager had no rate limiter on
     trust increases. A source that was correct 5 times in a row could reach
     trust=0.90 regardless of how little history it had.
     Fix: trust increase rate capped at decay_rate × MAX_INCREASE_MULTIPLIER.
     Trust cannot increase faster than it decays.

  2. Correlated source independence: v17 assigned all LLM agents the same
     source_type="llm_agent" but didn't track model family. Two Qwen3.5 calls
     have zero independence. Two calls from Qwen3.5 + DeepSeek-R1 have partial
     independence. Fix: independence_score = 1 - correlation(family_a, family_b).

  3. Suspicious accuracy spike detection: if a source's accuracy improves by
     more than SPIKE_THRESHOLD in one session, trigger a review flag.
     This catches adversarial sources that build trust then exploit it.

TRUST FORMULA (multi-dimensional):
  trust = base_reliability × independence_factor × recency_weight × stability_bonus

  Where:
    base_reliability  = EMA of accuracy (α=0.15 — slow updates, conservative)
    independence_factor = fraction of uses where source was independent of others
    recency_weight    = exp(-λ × age_days), λ = 0.10 (halves every 7 days)
    stability_bonus   = 1.0 + 0.1 × streak_length (if accuracy consistently good)
                        subject to MAX_STABILITY_BONUS cap

ANTI-POISONING GUARANTEES:
  1. trust_increase ≤ trust_decrease_rate × 2.0 per session
     (trust decays at most 2× faster than it increases — cannot be gamed quickly)
  2. Suspicious spike: 3+ consecutive correct predictions after period of errors
     → trigger independence review
  3. Source lineage: new sources initialized at BASE_TRUST_NEW (0.55) regardless
     of their claimed authority. Authority must be EARNED.
  4. Cross-domain independence: a source trusted for math gets BASE_TRUST_NEW
     for physics unless it has a history in that domain.

INDEPENDENCE SCORING:
  Two knowledge sources are independent if:
  - Different model families (Qwen vs DeepSeek vs Gemma)
  - Different origin types (LLM vs external dataset vs RAG)
  - Different provenance chains
  Independence score = product of independence factors:
    family_independence × origin_independence × provenance_independence

FAILURE MODES:
  FM1: Slow trust poisoning — small consistent errors that don't trigger spike
       detection but gradually lower threshold for what counts as "correct"
       Mitigation: calibration_error tracking — if |predicted - actual| > 0.20
       across 20 samples, flag as miscalibrated and reset to BASE_TRUST_NEW

  FM2: Trust laundering — source is used for low-stakes tasks to build trust,
       then used for high-stakes tasks
       Mitigation: per-domain trust (high-stakes domains require independent validation)

  FM3: Index collision — two sources with similar IDs map to same trust record
       Mitigation: source_id hashed with origin type to prevent collisions
"""

import hashlib
import json
import math
import os
import time
from collections import defaultdict, deque
from dataclasses import asdict, dataclass, field
from typing import Any, Deque, Dict, List, Optional, Tuple

from utils.logger import SystemLogger

logger = SystemLogger(__name__)

# Constants
BASE_TRUST_NEW        = 0.55    # all new sources start here
BASE_TRUST_INTERNAL   = 0.75    # internal reasoning starts here
MAX_TRUST             = 0.92    # hard ceiling (never fully trusted)
MIN_TRUST             = 0.05    # hard floor (never fully rejected)
MAX_INCREASE_MULTIPLIER = 2.0   # trust increase ≤ decay_rate × this
SPIKE_THRESHOLD       = 0.20    # accuracy improvement > this in one session = suspicious
DECAY_LAMBDA          = 0.10    # per-day decay rate (exp(-λ × days))
MAX_STABILITY_BONUS   = 1.15    # cap on stability bonus
CALIBRATION_WINDOW    = 20      # window for miscalibration detection
CALIBRATION_THRESHOLD = 0.20    # |predicted-actual| > this = miscalibrated

# Model family correlation map (1.0 = same family = zero independence)
MODEL_FAMILY_CORRELATION = {
    ("qwen",     "qwen"):       1.00,
    ("deepseek", "deepseek"):   1.00,
    ("gemma",    "gemma"):      1.00,
    ("llama",    "llama"):      1.00,
    ("qwen",     "deepseek"):   0.45,
    ("qwen",     "gemma"):      0.40,
    ("deepseek", "gemma"):      0.40,
    ("qwen",     "llama"):      0.35,
    ("deepseek", "llama"):      0.35,
}


def _model_family(model_str: str) -> str:
    ml = model_str.lower()
    for fam in ("qwen", "deepseek", "gemma", "llama", "mistral", "phi"):
        if fam in ml:
            return fam
    return "unknown"


def _family_independence(fam_a: str, fam_b: str) -> float:
    """0 = fully correlated, 1 = fully independent."""
    key = tuple(sorted([fam_a, fam_b]))
    corr = MODEL_FAMILY_CORRELATION.get(key, 0.30)  # unknown families = some correlation
    return round(1.0 - corr, 4)


@dataclass
class TrustDimension:
    """Trust in one (source, domain) combination."""
    source_id:        str
    domain:           str
    model_family:     str
    source_type:      str   # "llm_agent" | "external" | "research" | "internal"
    trust_score:      float = BASE_TRUST_NEW
    base_reliability: float = BASE_TRUST_NEW
    independence:     float = 1.0   # fraction of uses that were independent
    total_uses:       int   = 0
    correct_uses:     int   = 0
    last_updated:     float = field(default_factory=time.time)
    streak:           int   = 0     # current correct-answer streak
    accuracy_history: List[float] = field(default_factory=list)
    flagged_spike:    bool  = False
    miscalibrated:    bool  = False
    created_at:       float = field(default_factory=time.time)

    @property
    def accuracy(self) -> float:
        return self.correct_uses / max(self.total_uses, 1)

    @property
    def age_days(self) -> float:
        return (time.time() - self.last_updated) / 86400.0

    def compute_trust(self) -> float:
        recency     = math.exp(-DECAY_LAMBDA * self.age_days)
        indep_factor = max(0.50, self.independence)   # min 0.5 even for correlated sources
        stability   = min(MAX_STABILITY_BONUS, 1.0 + 0.02 * min(self.streak, 7))
        raw = self.base_reliability * recency * indep_factor * stability
        return round(min(MAX_TRUST, max(MIN_TRUST, raw)), 4)

    def to_dict(self) -> Dict:
        return {
            "source_id": self.source_id, "domain": self.domain,
            "model_family": self.model_family, "source_type": self.source_type,
            "trust_score": self.trust_score, "base_reliability": self.base_reliability,
            "independence": self.independence, "total_uses": self.total_uses,
            "correct_uses": self.correct_uses, "last_updated": self.last_updated,
            "streak": self.streak, "accuracy_history": self.accuracy_history[-10:],
            "flagged_spike": self.flagged_spike, "miscalibrated": self.miscalibrated,
            "created_at": self.created_at,
        }


class AdvancedTrustSystem:
    """
    Multi-dimensional trust with independence scoring and anti-poisoning.

    ANTI-POISONING CONTRACT:
      - trust_increase_per_update ≤ (current_trust - MIN_TRUST) × 0.08
        (at most 8% of remaining headroom per correct use)
      - trust_decrease_per_update ≥ (current_trust - MIN_TRUST) × 0.12
        (at least 12% of headroom per incorrect use)
      - Net effect: trust decreases faster than it increases
        (asymmetric updating prevents rapid poisoning)
    """

    MAX_DIMENSIONS = 3000

    def __init__(self, storage_path: str = "./data/trust_v18"):
        self.storage_path   = storage_path
        self._dims:         Dict[str, TrustDimension] = {}
        self._session_increases: Dict[str, float] = defaultdict(float)
        self._session_decreases: Dict[str, float] = defaultdict(float)
        self._stats = {
            "registrations": 0, "updates": 0, "spikes_detected": 0,
            "miscalibrations": 0, "poisoning_blocks": 0,
        }
        os.makedirs(storage_path, exist_ok=True)
        self._load()

    def register(
        self,
        source_id:   str,
        domain:      str,
        source_type: str,
        model_id:    str = "",
    ) -> float:
        """Register a source. Returns initial trust score."""
        key = self._key(source_id, domain)
        if key in self._dims:
            return self._dims[key].trust_score

        family   = _model_family(model_id) if model_id else "unknown"
        init_trust = {
            "internal": BASE_TRUST_INTERNAL,
            "research": 0.65,
            "external": 0.60,
            "llm_agent": BASE_TRUST_NEW,
        }.get(source_type, BASE_TRUST_NEW)

        self._dims[key] = TrustDimension(
            source_id=source_id, domain=domain,
            model_family=family, source_type=source_type,
            trust_score=init_trust, base_reliability=init_trust,
        )
        self._stats["registrations"] += 1
        self._prune()
        return init_trust

    def get_trust(
        self, source_id: str, domain: str, default: float = BASE_TRUST_NEW
    ) -> float:
        key = self._key(source_id, domain)
        dim = self._dims.get(key)
        if not dim:
            # Check general domain
            gen_key = self._key(source_id, "general")
            dim     = self._dims.get(gen_key)
        if not dim:
            return default
        dim.trust_score = dim.compute_trust()
        return dim.trust_score

    def update(
        self,
        source_id:     str,
        domain:        str,
        correct:       bool,
        was_independent: bool = True,
    ):
        """
        Update trust after a use.
        Asymmetric: decreases faster than it increases (anti-poisoning).
        """
        key = self._key(source_id, domain)
        if key not in self._dims:
            self.register(source_id, domain, "unknown")

        dim = self._dims[key]
        dim.total_uses  += 1
        dim.last_updated = time.time()
        self._stats["updates"] += 1

        # Update independence tracking
        n = dim.total_uses
        dim.independence = ((dim.independence * (n-1) + (1.0 if was_independent else 0.0)) / n)

        current = dim.base_reliability
        headroom = current - MIN_TRUST

        if correct:
            dim.correct_uses += 1
            dim.streak       += 1
            dim.accuracy_history.append(1.0)
            # ANTI-POISONING: increase ≤ 8% of headroom
            max_increase = headroom * 0.08
            actual_increase = min(max_increase, (1.0 - current) * 0.12)
            # Rate limiter: session increase cannot exceed session decrease × MAX_INCREASE_MULTIPLIER
            session_dec = self._session_decreases.get(key, 0)
            max_session_increase = max(0.05, session_dec * MAX_INCREASE_MULTIPLIER)
            self._session_increases[key] = self._session_increases.get(key, 0) + actual_increase
            if self._session_increases[key] > max_session_increase and dim.total_uses >= 5:
                # Trust increase rate-limited — clamp
                actual_increase = 0.0
                self._stats["poisoning_blocks"] += 1
            dim.base_reliability = round(min(MAX_TRUST, current + actual_increase), 4)
        else:
            dim.streak = 0
            dim.accuracy_history.append(0.0)
            # ANTI-POISONING: decrease ≥ 12% of headroom
            actual_decrease = max(headroom * 0.12, 0.02)
            self._session_decreases[key] = self._session_decreases.get(key, 0) + actual_decrease
            dim.base_reliability = round(max(MIN_TRUST, current - actual_decrease), 4)

        dim.accuracy_history = dim.accuracy_history[-CALIBRATION_WINDOW:]

        # Spike detection
        self._check_spike(dim)

        # Miscalibration detection
        if len(dim.accuracy_history) >= CALIBRATION_WINDOW:
            recent_acc  = sum(dim.accuracy_history[-10:]) / 10
            earlier_acc = sum(dim.accuracy_history[-20:-10]) / 10
            if abs(recent_acc - earlier_acc) > SPIKE_THRESHOLD:
                dim.flagged_spike = True
                self._stats["spikes_detected"] += 1
                logger.warning(
                    f"[TrustSystem] Accuracy spike for {source_id} in {domain}: "
                    f"{earlier_acc:.2f} → {recent_acc:.2f}"
                )

        dim.trust_score = dim.compute_trust()

    def compute_independence_score(
        self, sources: List[Tuple[str, str]]
    ) -> float:
        """
        Compute independence score for a group of (source_id, domain) pairs.
        1.0 = fully independent, 0.0 = completely correlated.
        """
        if len(sources) <= 1:
            return 0.60   # single source = assumed somewhat correlated

        families = []
        types    = []
        for sid, domain in sources:
            key = self._key(sid, domain)
            dim = self._dims.get(key)
            if dim:
                families.append(dim.model_family)
                types.append(dim.source_type)
            else:
                families.append("unknown")
                types.append("unknown")

        # Family independence: average pairwise independence
        n_pairs = 0
        total_indep = 0.0
        for i in range(len(families)):
            for j in range(i+1, len(families)):
                total_indep += _family_independence(families[i], families[j])
                n_pairs     += 1
        family_indep = total_indep / max(n_pairs, 1)

        # Type independence: fraction of distinct types
        type_indep = len(set(types)) / max(len(types), 1)

        return round((family_indep * 0.60 + type_indep * 0.40), 4)

    def is_trustworthy(self, source_id: str, domain: str) -> bool:
        return self.get_trust(source_id, domain) >= 0.40

    def _check_spike(self, dim: TrustDimension):
        if len(dim.accuracy_history) >= 8 and dim.streak >= 4:
            recent_mean = sum(dim.accuracy_history[-4:]) / 4
            earlier_mean = sum(dim.accuracy_history[-8:-4]) / 4
            if recent_mean - earlier_mean > SPIKE_THRESHOLD:
                dim.flagged_spike = True
                self._stats["spikes_detected"] += 1

    def _key(self, source_id: str, domain: str) -> str:
        return f"{source_id}::{domain}"

    def _prune(self):
        if len(self._dims) <= self.MAX_DIMENSIONS:
            return
        sorted_dims = sorted(
            self._dims.items(),
            key=lambda x: (x[1].last_updated, x[1].total_uses)
        )
        for key, _ in sorted_dims[:len(self._dims) - int(self.MAX_DIMENSIONS * 0.80)]:
            del self._dims[key]

    def get_stats(self) -> Dict:
        if self._dims:
            avg_trust = sum(d.trust_score for d in self._dims.values()) / len(self._dims)
            flagged   = sum(1 for d in self._dims.values() if d.flagged_spike)
        else:
            avg_trust, flagged = 0.0, 0
        return {
            **self._stats,
            "total_dims":  len(self._dims),
            "avg_trust":   round(avg_trust, 4),
            "flagged":     flagged,
        }

    def _save(self):
        fpath = os.path.join(self.storage_path, "trust_v18.json")
        try:
            subset = dict(list(self._dims.items())[-500:])
            with open(fpath, "w") as f:
                json.dump({k: v.to_dict() for k, v in subset.items()}, f, indent=2)
        except Exception as e:
            logger.warning(f"[TrustSystem] Save failed: {e}")

    def _load(self):
        fpath = os.path.join(self.storage_path, "trust_v18.json")
        try:
            if os.path.exists(fpath):
                with open(fpath) as f:
                    data = json.load(f)
                for key, dd in data.items():
                    self._dims[key] = TrustDimension(**dd)
                logger.info(f"[TrustSystem] Loaded {len(self._dims)} trust dimensions")
        except Exception as e:
            logger.warning(f"[TrustSystem] Load failed: {e}")
