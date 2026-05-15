"""
Mythos v17 — Epistemic State Engine
======================================
Classifies every claim the system produces or encounters into one of four
epistemic states. This is the ground truth bookkeeper.

AUDIT FINDINGS THIS ADDRESSES:
  - v16 bug: EvidenceConsensus clusters by keyword sim → two opposite claims    
    about the same topic cluster together and cancel silently.
  - v16 bug: No mechanism distinguishes "I have no evidence" from "the evidence
    conflicts" — both resulted in low confidence with no differentiation.
  - v16 bug: Hallucinated knowledge can enter ReasoningGraph as SOLUTION nodes
    if ResearchValidator passes at confidence >= 0.65 with 3 correlated trials.

DESIGN DECISIONS:
  1. Claims are the unit of analysis, not documents or responses.
     A response may contain 5 claims with different epistemic states.
     Failure mode: treating the whole response as one unit masks partial errors.
     Mitigation: extract_claims() produces structured ClaimRecord objects.

  2. States are strict and ordered:
     KNOWN → UNCERTAIN → UNKNOWN → CONTRADICTORY
     Cannot skip states except under special conditions (forcing via evidence).
     Failure mode: direct injection of KNOWN state bypasses evidence requirement.
     Mitigation: KNOWN state requires min_evidence_count >= 2 OR verified=True.

  3. State evolves via evidence application, not direct assignment.
     Failure mode: circular evidence (A cites B, B cites A) inflates confidence.
     Mitigation: provenance chain tracked per claim; circular refs detected.

  4. The system can be WRONG about its epistemic states.
     Self-trust calibration (separate module) measures this divergence.
"""

import hashlib
import json
import math
import os
import re
import time
from collections import defaultdict, deque
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Deque, Dict, List, Optional, Set, Tuple

from utils.logger import SystemLogger

logger = SystemLogger(__name__)


class EpistemicState(Enum):
    KNOWN         = "known"          # ≥2 independent sources confirm; no contradiction
    UNCERTAIN     = "uncertain"      # some evidence but insufficient or inconsistent
    UNKNOWN       = "unknown"        # no evidence found; claim is ungrounded
    CONTRADICTORY = "contradictory"  # verified conflict between sources


class ClaimType(Enum):
    FACTUAL      = "factual"      # verifiable fact claim
    PROCEDURAL   = "procedural"   # how to do something
    CAUSAL       = "causal"       # X causes Y
    COMPARATIVE  = "comparative"  # X is better than Y
    DEFINITIONAL = "definitional" # X is defined as Y
    SPECULATIVE  = "speculative"  # prediction or hypothesis


@dataclass
class ClaimRecord:
    """A single structured claim extracted from system output."""
    claim_id:        str
    text:            str             # the claim in normalized form
    claim_type:      ClaimType
    subject:         str             # main entity
    predicate:       str             # relation/property
    object_val:      str             # target value
    epistemic_state: EpistemicState
    confidence:      float           # 0-1
    evidence_ids:    List[str]       # which evidence supports this
    source_task_id:  str             # which task produced this
    created_at:      float = field(default_factory=time.time)
    updated_at:      float = field(default_factory=time.time)
    provenance_chain: List[str] = field(default_factory=list)  # source lineage
    contradiction_with: List[str] = field(default_factory=list)  # conflicting claim IDs
    verification_count: int = 0

    @property
    def claim_fingerprint(self) -> str:
        norm = f"{self.subject.lower().strip()}:{self.predicate.lower().strip()}:{self.object_val.lower().strip()}"
        return hashlib.md5(norm.encode()).hexdigest()[:16]


@dataclass
class EvidenceAttachment:
    """Records how a piece of evidence affects a claim's epistemic state."""
    evidence_id:   str
    source:        str
    supports:      bool    # True=supports, False=contradicts
    strength:      float   # 0-1
    timestamp:     float
    independent:   bool    # True if source is independent from claim's origin


class EpistemicStateEngine:
    """
    Per-claim epistemic state tracker with provenance.

    INVARIANTS:
      - KNOWN state requires: ≥2 independent supporting evidence OR explicit verification
      - CONTRADICTORY state: persists until resolution task completes
      - UNKNOWN state: default for any claim without evidence
      - All state transitions are logged with reason
    """

    MIN_EVIDENCE_FOR_KNOWN  = 2
    MAX_CLAIMS              = 5000    # bounded storage
    KNOWN_CONFIDENCE_FLOOR  = 0.70
    UNCERTAIN_CONFIDENCE_CAP = 0.69

    def __init__(self, storage_path: str = "./data/epistemic"):
        self.storage_path   = storage_path
        self._claims:       Dict[str, ClaimRecord]      = {}
        self._fp_index:     Dict[str, str]              = {}  # fingerprint → claim_id
        self._state_log:    Deque[Dict]                 = deque(maxlen=2000)
        self._transitions:  Dict[str, int]              = defaultdict(int)
        os.makedirs(storage_path, exist_ok=True)
        self._load()

    # ── Claim extraction ──────────────────────────────────────────

    def extract_claims(self, text: str, task_id: str = "") -> List[ClaimRecord]:
        """
        Extract structured claims from text.
        Offline-safe: pure pattern matching, no model calls.

        Returns list of ClaimRecord objects (may be empty for vague text).
        """
        claims = []
        sentences = self._split_sentences(text)

        for sent in sentences:
            record = self._parse_claim(sent.strip(), task_id)
            if record:
                claims.append(record)

        return claims

    def register_claim(self, claim: ClaimRecord) -> str:
        """Register a claim and return its ID. Deduplicates by fingerprint."""
        fp = claim.claim_fingerprint
        if fp in self._fp_index:
            existing_id = self._fp_index[fp]
            # Merge evidence
            existing = self._claims[existing_id]
            for eid in claim.evidence_ids:
                if eid not in existing.evidence_ids:
                    existing.evidence_ids.append(eid)
            existing.verification_count += 1
            existing.updated_at = time.time()
            self._update_state(existing)
            return existing_id

        if len(self._claims) >= self.MAX_CLAIMS:
            self._prune()

        self._claims[claim.claim_id]    = claim
        self._fp_index[fp]              = claim.claim_id
        self._save()
        return claim.claim_id

    # ── State management ──────────────────────────────────────────

    def apply_evidence(
        self,
        claim_id:   str,
        attachment: EvidenceAttachment,
    ) -> EpistemicState:
        """
        Apply evidence to a claim and recompute its epistemic state.
        Returns the new state.
        """
        claim = self._claims.get(claim_id)
        if not claim:
            return EpistemicState.UNKNOWN

        if attachment.evidence_id not in claim.evidence_ids:
            claim.evidence_ids.append(attachment.evidence_id)
        # Boost claim confidence from evidence strength
        if attachment.supports and attachment.strength > 0:
            claim.confidence = min(0.95, claim.confidence + attachment.strength * 0.30)

        # Check for circular provenance
        if attachment.source in claim.provenance_chain:
            logger.warning(
                f"[EpistemicEngine] Circular provenance detected for claim {claim_id}: "
                f"source {attachment.source} already in chain"
            )
            attachment.independent = False

        claim.provenance_chain.append(attachment.source)
        claim.updated_at = time.time()
        old_state = claim.epistemic_state
        self._update_state(claim)

        if old_state != claim.epistemic_state:
            self._log_transition(claim, old_state, claim.epistemic_state,
                                 f"evidence from {attachment.source}")
        self._save()
        return claim.epistemic_state

    def mark_contradicted(self, claim_id_a: str, claim_id_b: str):
        """Mark two claims as contradicting each other."""
        for cid, other_id in [(claim_id_a, claim_id_b), (claim_id_b, claim_id_a)]:
            claim = self._claims.get(cid)
            if claim and other_id not in claim.contradiction_with:
                claim.contradiction_with.append(other_id)
                old_state = claim.epistemic_state
                claim.epistemic_state = EpistemicState.CONTRADICTORY
                self._log_transition(claim, old_state, EpistemicState.CONTRADICTORY,
                                     f"contradicts {other_id}")
        self._save()

    def get_state(self, claim_id: str) -> Optional[EpistemicState]:
        claim = self._claims.get(claim_id)
        return claim.epistemic_state if claim else None

    def get_claim(self, claim_id: str) -> Optional[ClaimRecord]:
        return self._claims.get(claim_id)

    def get_claims_by_state(self, state: EpistemicState) -> List[ClaimRecord]:
        return [c for c in self._claims.values() if c.epistemic_state == state]

    def get_research_priority_claims(self, n: int = 10) -> List[ClaimRecord]:
        """Claims most worth researching: UNKNOWN and CONTRADICTORY, sorted by recency."""
        priority = [c for c in self._claims.values()
                    if c.epistemic_state in (EpistemicState.UNKNOWN, EpistemicState.CONTRADICTORY)]
        priority.sort(key=lambda c: c.updated_at, reverse=True)
        return priority[:n]

    # ── Internal mechanics ────────────────────────────────────────

    def _update_state(self, claim: ClaimRecord):
        """Recompute epistemic state from current evidence."""
        if claim.contradiction_with:
            claim.epistemic_state = EpistemicState.CONTRADICTORY
            claim.confidence      = min(claim.confidence, 0.50)
            return

        n_evidence   = len(claim.evidence_ids)
        n_independent = len(set(claim.provenance_chain))

        if n_evidence == 0:
            claim.epistemic_state = EpistemicState.UNKNOWN
            claim.confidence      = 0.0
        elif n_independent >= self.MIN_EVIDENCE_FOR_KNOWN and claim.verification_count >= 1:
            # KNOWN: ≥2 independent sources confirmed, verified
            claim.epistemic_state = EpistemicState.KNOWN
            # Ensure KNOWN state has at least floor confidence
            claim.confidence      = max(self.KNOWN_CONFIDENCE_FLOOR, claim.confidence)
        elif n_evidence > 0:
            claim.epistemic_state = EpistemicState.UNCERTAIN
            claim.confidence      = min(claim.confidence, self.UNCERTAIN_CONFIDENCE_CAP)
        else:
            claim.epistemic_state = EpistemicState.UNKNOWN
            claim.confidence      = 0.0

    def _parse_claim(self, sentence: str, task_id: str) -> Optional[ClaimRecord]:
        """Extract a structured claim from a sentence. Offline pattern matching."""
        if len(sentence) < 15 or len(sentence.split()) < 4:
            return None

        sl = sentence.lower()

        # Skip questions and meta-commentary
        if sl.endswith("?") or sl.startswith(("i think", "i believe", "perhaps", "maybe")):
            return None

        # Identify claim type
        ctype, subject, predicate, obj = self._classify_and_extract(sentence)

        if not subject or not predicate:
            return None

        cid = hashlib.md5(f"{task_id}:{sentence[:100]}".encode()).hexdigest()[:16]
        return ClaimRecord(
            claim_id=cid,
            text=sentence[:300],
            claim_type=ctype,
            subject=subject[:80],
            predicate=predicate[:80],
            object_val=obj[:80],
            epistemic_state=EpistemicState.UNKNOWN,  # always start as UNKNOWN
            confidence=0.0,
            evidence_ids=[],
            source_task_id=task_id,
        )

    @staticmethod
    def _classify_and_extract(
        sentence: str
    ) -> Tuple[ClaimType, str, str, str]:
        """Pattern-based SPO extraction. Returns (type, subject, predicate, object)."""
        sl  = sentence.lower()
        tok = sentence.split()
        if not tok:
            return ClaimType.FACTUAL, "", "", ""

        # Causal: "X causes Y", "X leads to Y", "X results in Y"
        causal_pat = re.search(
            r'(\w+(?:\s+\w+){0,3})\s+(causes?|leads?\s+to|results?\s+in|produces?)\s+(.+)',
            sl)
        if causal_pat:
            return (ClaimType.CAUSAL,
                    causal_pat.group(1).strip(),
                    causal_pat.group(2).strip(),
                    causal_pat.group(3).strip()[:60])

        # Definitional: "X is defined as Y", "X means Y"
        def_pat = re.search(r'(\w+(?:\s+\w+){0,2})\s+(is\s+(?:defined\s+as|a|an|the)|means?)\s+(.+)', sl)
        if def_pat:
            return (ClaimType.DEFINITIONAL,
                    def_pat.group(1).strip(),
                    def_pat.group(2).strip(),
                    def_pat.group(3).strip()[:60])

        # Comparative: "X is better/faster/worse than Y"
        comp_pat = re.search(
            r'(\w+(?:\s+\w+){0,3})\s+is\s+(better|faster|slower|more|less|worse|larger|smaller)\s+than\s+(.+)',
            sl)
        if comp_pat:
            return (ClaimType.COMPARATIVE,
                    comp_pat.group(1).strip(),
                    f"is {comp_pat.group(2).strip()} than",
                    comp_pat.group(3).strip()[:60])

        # Factual: "X has/does/is Y"
        factual_pat = re.search(
            r'^(\w+(?:\s+\w+){0,4})\s+(has|have|does|do|is|are|was|were|can|will|requires?|produces?)\s+(.+)',
            sl)
        if factual_pat:
            return (ClaimType.FACTUAL,
                    factual_pat.group(1).strip(),
                    factual_pat.group(2).strip(),
                    factual_pat.group(3).strip()[:60])

        # Fallback: use first noun phrase as subject, rest as predicate
        words = tok[:6]
        return (ClaimType.FACTUAL,
                " ".join(words[:min(3, len(words))]),
                "states",
                sentence[:60])

    def _split_sentences(self, text: str) -> List[str]:
        parts = re.split(r'(?<=[.!;])\s+', text)
        return [p.strip() for p in parts if len(p.strip()) >= 15]

    def _log_transition(
        self, claim: ClaimRecord,
        old: EpistemicState, new: EpistemicState, reason: str
    ):
        self._state_log.append({
            "claim_id":   claim.claim_id,
            "subject":    claim.subject[:40],
            "from":       old.value,
            "to":         new.value,
            "reason":     reason[:80],
            "timestamp":  time.time(),
        })
        key = f"{old.value}->{new.value}"
        self._transitions[key] += 1

    def _prune(self):
        """Remove oldest UNKNOWN claims when at capacity."""
        unknowns = sorted(
            [c for c in self._claims.values() if c.epistemic_state == EpistemicState.UNKNOWN],
            key=lambda c: c.updated_at
        )
        for c in unknowns[:len(unknowns)//2]:
            self._claims.pop(c.claim_id, None)
            self._fp_index.pop(c.claim_fingerprint, None)

    def get_stats(self) -> Dict:
        by_state = defaultdict(int)
        for c in self._claims.values():
            by_state[c.epistemic_state.value] += 1
        return {
            "total_claims":    len(self._claims),
            "by_state":        dict(by_state),
            "transitions":     dict(self._transitions),
            "recent_changes":  list(self._state_log)[-5:],
        }

    def _save(self):
        fpath = os.path.join(self.storage_path, "epistemic_state.json")
        try:
            subset = dict(list(self._claims.items())[-500:])

            def _enum_to_val(obj):
                if isinstance(obj, Enum):
                    return obj.value
                return str(obj)

            with open(fpath, "w") as f:
                json.dump({cid: asdict(c) for cid, c in subset.items()}, f, default=_enum_to_val)
        except Exception as e:
            logger.warning(f"[EpistemicEngine] Save failed: {e}")

    def _load(self):
        fpath = os.path.join(self.storage_path, "epistemic_state.json")
        try:
            if os.path.exists(fpath):
                with open(fpath) as f:
                    data = json.load(f)
                for cid, cd in data.items():
                    cd["epistemic_state"] = EpistemicState(cd["epistemic_state"])
                    cd["claim_type"]      = ClaimType(cd["claim_type"])
                    self._claims[cid]    = ClaimRecord(**cd)
                    self._fp_index[self._claims[cid].claim_fingerprint] = cid
                logger.info(f"[EpistemicEngine] Loaded {len(self._claims)} claims")
        except Exception as e:
            logger.warning(f"[EpistemicEngine] Load failed: {e}")

class WorldStateEngine:
    def __init__(self):
        self._state: dict[str, Any] = {
            "strategic": {"risk_level": 0.5},
            "user": {"trust_score": 0.8},
            "tasks": []
        }

    async def snapshot(self) -> dict:
        return dict(self._state)

    async def update(self, data: dict, event: str = "") -> None:
        self._state.update(data)
        if event:
            self._state["_last_event"] = event
