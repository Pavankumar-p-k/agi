"""
Mythos v7 — Reasoning Trace Memory
=====================================
V6 GAP: V6 has SemanticMemory (TF-IDF for task similarity) and EpisodicMemory
(stores full result dicts). BUT it stores RESULTS, not REASONING CHAINS.

This is a critical gap: the knowledge that "here is how I solved a problem
like this before, step by step" is far more valuable than "here is the
answer I produced before."

V7 adds ReasoningTraceMemory which:
1. Stores FULL reasoning chains (not just answers) from verified successful tasks
2. Retrieves structurally similar reasoning patterns when solving new tasks
3. Injects retrieved strategies as context ("here's how a similar problem was solved")
4. Tracks which reasoning strategies produced verified-correct answers per task TYPE
5. Prunes low-quality traces to prevent overfitting to wrong strategies

V6 GAP ALSO: SemanticMemory uses TF-IDF which misses semantic similarity.
"What is the derivative of x²?" and "Differentiate x squared" are semantically
identical but share almost no trigrams. V7 uses keyword-enriched fingerprints
that work better with offline (no embedding model) constraints.

STORAGE FORMAT: JSONL files — append-only for traces, indexed by fingerprint.
No external database needed. Works fully offline.
"""

import hashlib
import json
import math
import os
import re
import time
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from utils.logger import SystemLogger

logger = SystemLogger(__name__)


# ── Data Types ────────────────────────────────────────────────────

@dataclass
class ReasoningStep:
    """Single step in a reasoning chain."""
    step_id:    str
    step_type:  str      # "hypothesis" | "analysis" | "verification" | "conclusion"
    content:    str
    confidence: float
    model_used: str


@dataclass
class ReasoningTrace:
    """Full reasoning chain from a verified successful task."""
    trace_id:       str
    task:           str
    task_type:      str
    task_fingerprint: str       # canonical fingerprint for retrieval
    strategy_used:  str         # which reasoning strategy produced this
    steps:          List[ReasoningStep]
    final_answer:   str
    verified:       bool        # only store traces that passed verification
    confidence:     float
    debate_verdict: str         # "accept" | "refine" | etc.
    models_used:    List[str]
    elapsed_ms:     float
    timestamp:      float = field(default_factory=time.time)
    reuse_count:    int = 0     # how many times this trace was retrieved and used
    reuse_success:  int = 0     # how many times retrieval led to verified answer


@dataclass
class StrategyRecord:
    """Track per-strategy performance per task type."""
    strategy:       str
    task_type:      str
    attempts:       int = 0
    verified_wins:  int = 0

    @property
    def win_rate(self) -> float:
        return self.verified_wins / max(self.attempts, 1)


@dataclass
class TraceRetrievalResult:
    traces:             List[ReasoningTrace]
    similarity_scores:  List[float]
    strategy_hint:      str          # best strategy for this task type
    context_injection:  str          # formatted text ready to inject into prompt


# ── Fingerprinting ────────────────────────────────────────────────

STOP_WORDS = frozenset({
    "the", "a", "an", "is", "are", "was", "were", "be", "been",
    "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "can", "to", "for", "of",
    "in", "on", "at", "by", "with", "about", "from", "into",
    "and", "or", "but", "not", "this", "that", "it", "its",
    "you", "your", "my", "our", "their", "how", "what", "when",
    "where", "who", "which", "please", "help", "need", "want",
    "make", "create", "build", "write", "generate", "give",
})

DOMAIN_KEYWORDS = {
    "math":     {"equation", "solve", "calculate", "proof", "derivative", "integral",
                  "matrix", "probability", "theorem", "formula", "algebra", "geometry"},
    "code":     {"function", "algorithm", "implement", "debug", "class", "method",
                  "return", "loop", "array", "string", "python", "javascript", "api"},
    "logic":    {"implies", "therefore", "conclude", "premise", "if", "then", "else",
                  "fallacy", "valid", "invalid", "argument", "reasoning"},
    "science":  {"biology", "chemistry", "physics", "energy", "force", "cell",
                  "molecule", "reaction", "experiment", "hypothesis"},
    "general":  set(),
}


def compute_fingerprint(text: str) -> str:
    """
    Compute a canonical fingerprint for similarity retrieval.
    Uses: keyword extraction + domain signals + length bucket.
    Better than raw TF-IDF for small corpora.
    """
    words = re.sub(r'[^a-z0-9\s]', '', text.lower()).split()
    keywords = [w for w in words if w not in STOP_WORDS and len(w) > 2]

    # Top 8 keywords by frequency
    freq = Counter(keywords)
    top8 = [w for w, _ in freq.most_common(8)]

    # Detect domain
    domain = "general"
    for d, kws in DOMAIN_KEYWORDS.items():
        if d == "general":
            continue
        if len(set(keywords) & kws) >= 2:
            domain = d
            break

    # Length bucket
    wc = len(text.split())
    bucket = "short" if wc < 30 else "medium" if wc < 100 else "long"

    fp_str = f"{domain}:{bucket}:{':'.join(sorted(top8[:6]))}"
    return hashlib.md5(fp_str.encode()).hexdigest()[:16]


def keyword_similarity(text_a: str, text_b: str) -> float:
    """
    Keyword-overlap similarity — works better than trigrams for task matching.
    Combines: shared keywords, shared domain signals, length similarity.
    """
    def keywords(text: str):
        words = re.sub(r'[^a-z0-9\s]', '', text.lower()).split()
        return Counter(w for w in words if w not in STOP_WORDS and len(w) > 2)

    ka, kb = keywords(text_a), keywords(text_b)
    if not ka or not kb:
        return 0.0

    # Jaccard on keyword sets
    set_a, set_b = set(ka.keys()), set(kb.keys())
    jaccard = len(set_a & set_b) / len(set_a | set_b) if (set_a | set_b) else 0.0

    # Cosine on keyword frequencies
    all_kw = set_a | set_b
    dot    = sum(ka.get(w, 0) * kb.get(w, 0) for w in all_kw)
    norm_a = math.sqrt(sum(v**2 for v in ka.values()))
    norm_b = math.sqrt(sum(v**2 for v in kb.values()))
    cosine = dot / (norm_a * norm_b) if (norm_a * norm_b) > 0 else 0.0

    return 0.4 * jaccard + 0.6 * cosine


# ── Reasoning Trace Memory ────────────────────────────────────────

class ReasoningTraceMemory:
    """
    Persistent store for verified reasoning traces.
    Enables retrieval-augmented reasoning: "how did we solve something like this before?"
    """

    def __init__(
        self,
        storage_path: str = "./data/traces",
        max_traces: int = 500,
        min_confidence: float = 0.75,
    ):
        self.storage_path  = storage_path
        self.max_traces    = max_traces
        self.min_confidence = min_confidence
        self._traces: List[ReasoningTrace] = []
        self._strategy_records: Dict[str, StrategyRecord] = {}
        self._loaded = False

        os.makedirs(storage_path, exist_ok=True)

    async def initialize(self):
        """Load existing traces from disk."""
        if self._loaded:
            return
        trace_file = os.path.join(self.storage_path, "traces.jsonl")
        strategy_file = os.path.join(self.storage_path, "strategies.json")

        if os.path.exists(trace_file):
            try:
                with open(trace_file) as f:
                    for line in f:
                        if line.strip():
                            d = json.loads(line)
                            # Reconstruct dataclass
                            steps = [ReasoningStep(**s) for s in d.pop("steps", [])]
                            trace = ReasoningTrace(steps=steps, **d)
                            self._traces.append(trace)
                logger.info(f"[TraceMemory] Loaded {len(self._traces)} traces from disk")
            except Exception as e:
                logger.warning(f"[TraceMemory] Failed to load traces: {e}")

        if os.path.exists(strategy_file):
            try:
                with open(strategy_file) as f:
                    data = json.load(f)
                for key, v in data.items():
                    self._strategy_records[key] = StrategyRecord(**v)
            except Exception as e:
                logger.warning(f"[TraceMemory] Failed to load strategy records: {e}")

        self._loaded = True

    async def store_trace(
        self,
        task: str,
        task_type: str,
        strategy: str,
        steps: List[Dict[str, Any]],
        final_answer: str,
        verified: bool,
        confidence: float,
        debate_verdict: str,
        models_used: List[str],
        elapsed_ms: float,
    ):
        """
        Store a reasoning trace. Only stores if verified=True and confidence≥threshold.
        V7 GUARANTEE: We never store unverified traces, preventing the system
        from learning from wrong answers.
        """
        if not verified or confidence < self.min_confidence:
            logger.debug(
                f"[TraceMemory] Skipping trace: verified={verified}, "
                f"confidence={confidence:.2f} < {self.min_confidence}"
            )
            # Still update strategy records
            self._update_strategy(strategy, task_type, success=verified and confidence >= self.min_confidence)
            return

        await self.initialize()

        trace_id = hashlib.md5(f"{task}{time.time()}".encode()).hexdigest()[:12]
        fp       = compute_fingerprint(task)

        reasoning_steps = [
            ReasoningStep(
                step_id=s.get("step_id", str(i)),
                step_type=s.get("step_type", "analysis"),
                content=s.get("content", ""),
                confidence=s.get("confidence", 0.5),
                model_used=s.get("model_used", ""),
            )
            for i, s in enumerate(steps)
        ]

        trace = ReasoningTrace(
            trace_id=trace_id,
            task=task[:500],
            task_type=task_type,
            task_fingerprint=fp,
            strategy_used=strategy,
            steps=reasoning_steps,
            final_answer=final_answer[:2000],
            verified=True,
            confidence=confidence,
            debate_verdict=debate_verdict,
            models_used=models_used,
            elapsed_ms=elapsed_ms,
        )

        self._traces.append(trace)

        # Enforce max capacity — remove lowest confidence traces
        if len(self._traces) > self.max_traces:
            self._traces.sort(key=lambda t: (t.confidence, t.reuse_success), reverse=True)
            removed = self._traces[self.max_traces:]
            self._traces = self._traces[:self.max_traces]
            logger.debug(f"[TraceMemory] Pruned {len(removed)} low-quality traces")

        self._update_strategy(strategy, task_type, success=True)
        await self._persist_trace(trace)
        logger.info(f"[TraceMemory] Stored trace {trace_id} (type={task_type}, conf={confidence:.2f})")

    async def retrieve(
        self,
        task: str,
        task_type: str,
        top_k: int = 3,
        min_similarity: float = 0.25,
    ) -> TraceRetrievalResult:
        """
        Retrieve most similar verified reasoning traces for a new task.
        Returns formatted context injection text for the prompt.
        """
        await self.initialize()

        if not self._traces:
            return TraceRetrievalResult(
                traces=[], similarity_scores=[],
                strategy_hint=self._best_strategy(task_type),
                context_injection="",
            )

        # Score all traces
        scored = []
        for trace in self._traces:
            sim = keyword_similarity(task, trace.task)
            # Boost: same task type
            if trace.task_type == task_type:
                sim = min(1.0, sim * 1.2)
            # Boost: high reuse success
            if trace.reuse_count > 0:
                success_rate = trace.reuse_success / trace.reuse_count
                sim = min(1.0, sim * (1.0 + 0.1 * success_rate))
            scored.append((trace, sim))

        scored.sort(key=lambda x: x[1], reverse=True)
        top_traces = [(t, s) for t, s in scored[:top_k] if s >= min_similarity]

        if not top_traces:
            return TraceRetrievalResult(
                traces=[], similarity_scores=[],
                strategy_hint=self._best_strategy(task_type),
                context_injection="",
            )

        traces     = [t for t, _ in top_traces]
        scores     = [s for _, s in top_traces]
        strategy   = self._best_strategy(task_type)

        # Format context injection
        ctx_lines  = [f"SIMILAR VERIFIED SOLUTIONS FROM MEMORY (use as strategy hints):"]
        for i, (trace, score) in enumerate(top_traces):
            ctx_lines.append(
                f"\n[Memory {i+1}] Similarity={score:.2f} | Strategy={trace.strategy_used} | "
                f"Task type={trace.task_type}"
            )
            ctx_lines.append(f"Previous task (paraphrased): {trace.task[:150]}")
            # Include reasoning approach, not the answer itself (avoid anchoring)
            if trace.steps:
                first_step = trace.steps[0].content[:200]
                ctx_lines.append(f"Reasoning approach used: {first_step}")
            ctx_lines.append(f"Strategy that worked: {trace.strategy_used}")

        context_injection = "\n".join(ctx_lines)

        # Mark traces as retrieved
        for trace in traces:
            trace.reuse_count += 1

        return TraceRetrievalResult(
            traces=traces,
            similarity_scores=scores,
            strategy_hint=strategy,
            context_injection=context_injection,
        )

    def record_reuse_success(self, trace_ids: List[str]):
        """Call when a task that used retrieved traces was verified successful."""
        for trace in self._traces:
            if trace.trace_id in trace_ids:
                trace.reuse_success += 1

    def _best_strategy(self, task_type: str) -> str:
        """Return strategy with highest win rate for task type."""
        relevant = [
            r for r in self._strategy_records.values()
            if r.task_type == task_type and r.attempts >= 3
        ]
        if not relevant:
            return "chain_of_thought"  # default
        return max(relevant, key=lambda r: r.win_rate).strategy

    def _update_strategy(self, strategy: str, task_type: str, success: bool):
        key = f"{strategy}:{task_type}"
        if key not in self._strategy_records:
            self._strategy_records[key] = StrategyRecord(
                strategy=strategy, task_type=task_type
            )
        self._strategy_records[key].attempts += 1
        if success:
            self._strategy_records[key].verified_wins += 1

    async def _persist_trace(self, trace: ReasoningTrace):
        """Append trace to JSONL file."""
        trace_file = os.path.join(self.storage_path, "traces.jsonl")
        strategy_file = os.path.join(self.storage_path, "strategies.json")
        try:
            d = asdict(trace)
            with open(trace_file, "a") as f:
                f.write(json.dumps(d) + "\n")
            with open(strategy_file, "w") as f:
                json.dump(
                    {k: asdict(v) for k, v in self._strategy_records.items()}, f
                )
        except Exception as e:
            logger.warning(f"[TraceMemory] Persist failed: {e}")

    def get_stats(self) -> Dict[str, Any]:
        if not self._traces:
            return {"total_traces": 0}

        by_type: Dict[str, int] = defaultdict(int)
        by_strategy: Dict[str, int] = defaultdict(int)
        total_reuse = sum(t.reuse_count for t in self._traces)
        total_reuse_success = sum(t.reuse_success for t in self._traces)
        avg_conf = sum(t.confidence for t in self._traces) / len(self._traces)

        for t in self._traces:
            by_type[t.task_type] += 1
            by_strategy[t.strategy_used] += 1

        return {
            "total_traces":    len(self._traces),
            "avg_confidence":  round(avg_conf, 3),
            "total_reuses":    total_reuse,
            "reuse_success_rate": round(total_reuse_success / max(total_reuse, 1), 3),
            "by_task_type":    dict(by_type),
            "by_strategy":     dict(by_strategy),
            "strategy_win_rates": {
                k: round(v.win_rate, 3)
                for k, v in self._strategy_records.items()
                if v.attempts >= 3
            },
        }
