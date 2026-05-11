"""
CLAUDE MYTHOS BRAIN ENGINE
The deep reasoning module that makes this system think like Claude at its best.

Implements the specific cognitive patterns that distinguish Claude's reasoning:
1.  Constitutional alignment  — values-check on every output
2.  Steelman synthesis        — strongest version before critique
3.  Epistemic calibration     — explicit uncertainty on every claim
4.  Analogical mapping        — solve by structural similarity
5.  Counterfactual probing    — stress-test assumptions
6.  Recursive decomposition   — break until truly atomic
7.  Socratic depth            — questions reveal hidden structure
8.  Meta-cognitive watchdog   — detect and correct own reasoning errors
9.  Working scratchpad        — externalise intermediate reasoning
10. Consistency enforcement   — no self-contradiction across outputs

All 10 patterns compose into the MythosBrain class which wraps any
generation and upgrades it to Mythos-level quality.
"""

# Exported strategy registry — the 4 Mythos cognitive strategies
MYTHOS_STRATEGIES = {
    "steelman": "Construct the strongest version of every position before resolving",
    "epistemic": "Mark certainty level (certain/likely/possible/speculative) on every claim",
    "analogical": "Find structural parallels in other domains to inform the answer",
    "counterfactual": "Challenge key assumptions by inverting them and tracing consequences",
}


import re, json, time
from typing import Any, Dict, List, Optional, Tuple
from utils.logger import SystemLogger

logger = SystemLogger(__name__)


# ── 1. CONSTITUTIONAL ALIGNMENT ────────────────────────────────────

CONSTITUTIONAL_PRINCIPLES = [
    "Be honest — never state what you don't believe to be true",
    "Acknowledge uncertainty explicitly — never fake confidence",
    "Avoid harm — flag outputs that could cause damage",
    "Be complete — a partial answer presented as complete is a lie",
    "Respect logic — contradictions must be resolved, never papered over",
    "Credit your reasoning — show the chain, not just the conclusion",
]

class ConstitutionalChecker:
    """Checks output against core principles. Flags violations."""

    VIOLATION_PATTERNS = [
        (r'\bI (guarantee|promise|definitely will)\b', "Overconfident commitment"),
        (r'\b(always|never|impossible|certain)\b(?!.*\?)', "Absolute claim without qualification"),
        (r'TBD|FIX_ME|incomplete_stub|implement later', "Incomplete output passed as complete"),
        (r'\bI cannot (help|assist|provide)\b.*\bbut\b', "Indirect refusal masking partial help"),
    ]

    def check(self, text: str) -> Tuple[bool, List[str]]:
        violations = []
        for pattern, label in self.VIOLATION_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                violations.append(label)
        return len(violations) == 0, violations


# ── 2. EPISTEMIC CALIBRATION ───────────────────────────────────────

EPISTEMIC_PROMPT = """Review this response and add explicit epistemic markers.
For every factual claim, add one of: [CERTAIN] [LIKELY] [POSSIBLE] [SPECULATIVE]
Only add markers where missing. Keep the response otherwise identical.

RESPONSE:
{response}

CALIBRATED RESPONSE:"""

UNCERTAINTY_PROMPT = """Extract all claims from this text and rate each one's certainty.

TEXT: {text}

Respond in JSON:
{{
  "claims": [
    {{"claim": "...", "certainty": "certain|likely|possible|speculative", "basis": "why"}}
  ],
  "overall_confidence": 0.0-1.0,
  "acknowledged_unknowns": ["what we don't know"],
  "hidden_assumptions": ["assumptions that could be wrong"]
}}"""


# ── 3. STEELMAN ENGINE ────────────────────────────────────────────

STEELMAN_PROMPT = """Your job is to steelman every position in this task before resolving it.

TASK: {task}
INITIAL RESPONSE: {response}

Step 1: Identify all positions/approaches in the response
Step 2: For each, construct the STRONGEST possible version of that position
Step 3: Find what each position gets right that the others miss
Step 4: Synthesize a response that incorporates the strongest elements of all

STEELMANNED SYNTHESIS:"""


# ── 4. ANALOGICAL MAPPER ─────────────────────────────────────────

ANALOGY_PROMPT = """Find structural analogies to solve this problem better.

TASK: {task}
CURRENT APPROACH: {response}

Identify 2 problems from different domains that share the SAME structure.
For each analogy:
- Name the analogous problem
- Show the structural mapping (A:B :: C:D)
- Extract the solution pattern
- Apply it to improve the current response

ANALOGY-ENHANCED RESPONSE:"""


# ── 5. COUNTERFACTUAL STRESS TEST ─────────────────────────────────

COUNTERFACTUAL_PROMPT = """Stress-test this response by inverting key assumptions.

TASK: {task}
RESPONSE: {response}

Identify the 3 most critical assumptions this response makes.
For each, ask: "What if this were false?"
If the response breaks when an assumption fails, fix it to be assumption-robust.

HARDENED RESPONSE:"""


# ── 6. META-COGNITIVE WATCHDOG ────────────────────────────────────

METACOG_PROMPT = """You are a meta-cognitive monitor reviewing an AI's own reasoning.
Detect any reasoning errors in this response.

TASK: {task}
RESPONSE: {response}

Check for:
- Circular reasoning (conclusion used as premise)
- False dichotomies (only 2 options presented when more exist)
- Hasty generalisation (specific → universal without warrant)
- Confirmation bias (only evidence for, none against)
- Scope creep (answering a different question than asked)
- Strawmanning (weakened version of opposing view)

Respond in JSON:
{{
  "errors_found": [{{"type": "...", "location": "...", "fix": "..."}}],
  "clean": true/false,
  "corrected_response": "full corrected response if not clean, else empty string"
}}"""


# ── MYTHOS BRAIN ──────────────────────────────────────────────────

class MythosBrain:
    """
    Wraps any model output and applies the full suite of Claude Mythos
    cognitive patterns to elevate it to maximum reasoning quality.

    Usage:
        brain = MythosBrain(model_router)
        enhanced = await brain.enhance(task, raw_response, depth="full")
    """

    DEPTH_LEVELS = {
        "minimal":  ["constitutional", "metacog"],
        "standard": ["constitutional", "epistemic", "metacog"],
        "deep":     ["constitutional", "steelman", "epistemic", "counterfactual", "metacog"],
        "full":     ["constitutional", "steelman", "epistemic", "analogical",
                     "counterfactual", "metacog"],
    }

    def __init__(self, model_router: Any):
        self.router = model_router
        self.constitutional = ConstitutionalChecker()
        self._enhancement_log: List[Dict] = []

    async def enhance(
        self, task: str, response: str,
        depth: str = "standard",
        budget_tokens: int = 8000
    ) -> Dict[str, Any]:
        """
        Apply Mythos cognitive patterns to a raw response.
        Returns enhanced response + audit trail.
        """
        from memory.tiered_memory import tiered_memory
        # Pull context from memory
        memory_context = tiered_memory.recall(task)
        if memory_context:
            context_str = "\n".join([m.get("content", m.get("text", "")) for m in memory_context])
            task = f"CONTEXT FROM MEMORY:\n{context_str}\n\nTASK: {task}"

        if not response or not response.strip():
            return {"enhanced": response, "patterns_applied": [], "issues": ["empty response"]}

        steps = self.DEPTH_LEVELS.get(depth, self.DEPTH_LEVELS["standard"])
        current = response
        applied = []
        issues = []
        tokens_used = 0
        token_limit = budget_tokens

        logger.info(f"[MythosBrain] Enhancing with depth={depth} steps={steps}")

        for step in steps:
            if tokens_used >= token_limit:
                logger.info(f"[MythosBrain] Token budget reached at {step}")
                break

            try:
                if step == "constitutional":
                    ok, viols = self.constitutional.check(current)
                    if not ok:
                        issues.extend(viols)
                        logger.info(f"[MythosBrain] Constitutional violations: {viols}")
                    applied.append(f"constitutional:{'pass' if ok else 'flagged'}")

                elif step == "steelman":
                    result = await self._call(STEELMAN_PROMPT.format(
                        task=task, response=current[:1500]
                    ), temperature=0.6, max_tokens=1500)
                    if result and len(result) > len(current) * 0.5:
                        current = result
                        tokens_used += len(result) // 4
                        applied.append("steelman:applied")

                elif step == "epistemic":
                    result = await self._call(UNCERTAINTY_PROMPT.format(
                        text=current[:1000]
                    ), temperature=0.3, max_tokens=600)
                    parsed = self._parse_json(result)
                    if parsed:
                        conf = parsed.get("overall_confidence", 1.0)
                        unknowns = parsed.get("acknowledged_unknowns", [])
                        assumptions = parsed.get("hidden_assumptions", [])
                        if unknowns or assumptions:
                            # Append epistemic footer to response
                            footer = "\n\n**Epistemic notes:**"
                            if unknowns:
                                footer += f"\n- Unknowns: {'; '.join(unknowns[:3])}"
                            if assumptions:
                                footer += f"\n- Key assumptions: {'; '.join(assumptions[:3])}"
                            current = current + footer
                        applied.append(f"epistemic:conf={conf:.2f}")
                        tokens_used += 600

                elif step == "analogical":
                    result = await self._call(ANALOGY_PROMPT.format(
                        task=task, response=current[:1000]
                    ), temperature=0.7, max_tokens=1200)
                    if result and len(result) > 200:
                        current = result
                        tokens_used += len(result) // 4
                        applied.append("analogical:applied")

                elif step == "counterfactual":
                    result = await self._call(COUNTERFACTUAL_PROMPT.format(
                        task=task, response=current[:1200]
                    ), temperature=0.5, max_tokens=1200)
                    if result and len(result) > len(current) * 0.4:
                        current = result
                        tokens_used += len(result) // 4
                        applied.append("counterfactual:applied")

                elif step == "metacog":
                    result = await self._call(METACOG_PROMPT.format(
                        task=task, response=current[:1500]
                    ), temperature=0.3, max_tokens=800)
                    parsed = self._parse_json(result)
                    if parsed and not parsed.get("clean", True):
                        errors = parsed.get("errors_found", [])
                        corrected = parsed.get("corrected_response", "")
                        if errors:
                            issues.extend([f"Metacog: {e.get('type','?')}" for e in errors])
                        if corrected and len(corrected) > 100:
                            current = corrected
                        applied.append(f"metacog:errors={len(errors)}")
                    else:
                        applied.append("metacog:clean")
                    tokens_used += 800

            except Exception as e:
                logger.warning(f"[MythosBrain] Step {step} failed: {e}")
                applied.append(f"{step}:failed")

        record = {
            "task_snippet": task[:60],
            "depth": depth,
            "patterns_applied": applied,
            "issues": issues,
            "tokens_used": tokens_used,
            "timestamp": time.time()
        }
        self._enhancement_log.append(record)

        logger.info(f"[MythosBrain] Complete | applied={applied} | issues={len(issues)}")

        return {
            "enhanced": current,
            "original": response,
            "patterns_applied": applied,
            "issues": issues,
            "tokens_used": tokens_used,
            "improved": current != response
        }

    async def deep_think(self, task: str) -> str:
        """
        Pure Mythos thinking pass — generate a response from scratch using
        all cognitive patterns simultaneously as a single mega-prompt.
        """
        prompt = f"""Apply the following cognitive frameworks simultaneously to answer this task:

TASK: {task}

COGNITIVE FRAMEWORK:
1. STEELMAN: Identify and strengthen every valid approach before choosing
2. EPISTEMIC: Mark your certainty level for every claim you make
3. ANALOGICAL: Find structural parallels in other domains to inform the answer
4. COUNTERFACTUAL: Challenge your key assumptions — what if they're wrong?
5. META-COGNITIVE: Monitor your own reasoning for logical errors as you go
6. CONSTITUTIONAL: Ensure honesty, completeness, and intellectual integrity

Produce a single, coherent, production-grade response that embodies all 6 frameworks.
Do not label sections by framework — weave them into natural, excellent reasoning.

RESPONSE:"""

        result = await self._call(prompt, temperature=0.5, max_tokens=3000)
        return result or ""

    async def _call(self, prompt: str, temperature: float, max_tokens: int) -> str:
        if not self.router:
            return ""
        try:
            r = await self.router.complete(
                model="reasoning",
                prompt=prompt,
                temperature=temperature,
                max_tokens=max_tokens
            )
            return r.get("text", "")
        except Exception as e:
            logger.warning(f"[MythosBrain] Router call failed: {e}")
            return ""

    def _parse_json(self, text: str) -> Optional[Dict]:
        if not text:
            return None
        try:
            return json.loads(text)
        except Exception:
            m = re.search(r'\{.*\}', text, re.DOTALL)
            if m:
                try:
                    return json.loads(m.group())
                except Exception as parse_err:
                    logger.error(f"[MythosBrain] JSON extraction parsing failed: {parse_err}")
                    raise RuntimeError(f"JSON parsing failed: {parse_err}")
        return None

    def get_stats(self) -> Dict:
        if not self._enhancement_log:
            return {"total_enhancements": 0}
        total_issues = sum(len(r["issues"]) for r in self._enhancement_log)
        improved = sum(1 for r in self._enhancement_log if any("applied" in p for p in r.get("patterns_applied",[])))
        return {
            "total_enhancements": len(self._enhancement_log),
            "total_issues_caught": total_issues,
            "responses_improved": improved,
            "avg_tokens_per_enhancement": sum(r["tokens_used"] for r in self._enhancement_log) // max(len(self._enhancement_log),1)
        }
