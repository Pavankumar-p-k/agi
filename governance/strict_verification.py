"""
DEPRECATED - Replaced by verification/adversarial_verifier.py

Mythos v7 — Strict Verification Engine
========================================
V6 GAP FIXED: V6 multi-paradigm verifier is theoretically sound but has
two critical bugs:

BUG 1 — Soft rejection: When paradigms FAIL, the system still outputs
the answer with a lower confidence score. There is no HARD REJECT that
forces re-reasoning. A "FAIL" in v6 is just an annotation.

BUG 2 — Re-derivation paradigm reads context: The RederivationParadigm
is supposed to re-derive from scratch, but the prompt still passes the
original answer in the context as "ANSWER_TO_VERIFY". A model cannot
unsee what it has seen — this contaminates independence.

BUG 3 — Math/code verification is regex-based: The MathVerifier uses
regex to extract numbers and compares them, which fails on symbolic math,
units, and reformatted numbers. The CodeSandbox is subprocess-based but
never actually installs dependencies — so any code requiring libraries
silently fails and returns "passed" due to empty output.

V7 FIXES:
1. HARD REJECT enforced: failed verification triggers mandatory re-reasoning
   loop (up to max_retry times) before outputting anything
2. True re-derivation: Rederiver gets ONLY the task, no answer in context
3. Real code execution: actual subprocess with dependency detection and
   pip install --break-system-packages in sandbox
4. Symbolic math via sympy: actual equation solving, not regex
5. Logical consistency: step-by-step contradiction checker

V7 VERIFICATION LEVELS (maps to DeliberationPlan.verify_depth):
  shallow:     syntax check + constitutional check only (fast)
  standard:    logical + factual plausibility + code sandbox
  deep:        all above + independent re-derivation + math solver
  exhaustive:  all above + adversarial failure sim + cross-model agreement
"""

import asyncio
import math
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from utils.logger import SystemLogger

logger = SystemLogger(__name__)


# ── Verdict Types ─────────────────────────────────────────────────

class VerificationVerdict(Enum):
    PASS         = "pass"       # answer is verified correct
    FAIL         = "fail"       # answer has verifiable errors — HARD REJECT
    UNCERTAIN    = "uncertain"  # cannot verify — flag but allow with caveat
    NEEDS_TOOL   = "needs_tool" # requires tool (code/math) to verify


@dataclass
class VerificationCheck:
    name:       str
    verdict:    VerificationVerdict
    confidence: float
    evidence:   List[str]
    issues:     List[str]
    latency_ms: float = 0.0
    is_fatal:   bool = False


@dataclass
class VerificationReport:
    overall_verdict:    VerificationVerdict
    checks:             List[VerificationCheck]
    passed:             bool              # True only if overall=PASS or UNCERTAIN
    fatal_issues:       List[str]
    all_issues:         List[str]
    confidence:         float
    should_rerun:       bool              # True if hard reject triggered
    rerun_guidance:     str               # what to fix on rerun
    verification_depth: str
    elapsed_ms:         float


# ── Constitutional Check ─────────────────────────────────────────

CONSTITUTIONAL_PATTERNS = [
    (r'\bTBD\b|\bFIXME\b|\bincomplete_stub\b', "Incomplete output — incomplete stub text detected", True),
    (r'\bI cannot\b.*\bbut\b', "Evasive non-answer — claims inability while suggesting it", False),
    (r'\b(I guarantee|I promise|100% certain)\b', "Overconfident absolute claim", False),
    (r'(?i)\buntrue\b|\bfabricated\b|\bmade.?up\b', "Self-admitted fabrication", True),
]


def constitutional_check(answer: str) -> VerificationCheck:
    start = time.time()
    issues = []
    is_fatal = False
    for pattern, message, fatal in CONSTITUTIONAL_PATTERNS:
        if re.search(pattern, answer, re.IGNORECASE):
            issues.append(message)
            if fatal:
                is_fatal = True
    verdict = VerificationVerdict.FAIL if issues else VerificationVerdict.PASS
    return VerificationCheck(
        name="constitutional",
        verdict=verdict,
        confidence=0.95,
        evidence=["Pattern scan of output"],
        issues=issues,
        latency_ms=(time.time() - start) * 1000,
        is_fatal=is_fatal,
    )


# ── Code Execution Check (real sandbox) ──────────────────────────

def extract_code_blocks(text: str) -> List[str]:
    """Extract all Python code blocks from markdown text."""
    blocks = re.findall(r'```(?:python|py)?\n(.*?)```', text, re.DOTALL)
    return [b.strip() for b in blocks if b.strip()]


def sandbox_execute_code(code: str, timeout: int = 15) -> Tuple[bool, str, str]:
    """
    Execute Python code in a subprocess sandbox.
    V6 BUG FIXED: V6 just runs code without dependencies.
    V7: auto-detects imports and attempts to install missing ones.
    Returns: (success, stdout, stderr)
    """
    # Detect top-level imports
    imports = re.findall(r'^(?:import|from)\s+(\w+)', code, re.MULTILINE)
    stdlib = {'os', 'sys', 'math', 'json', 're', 'time', 'datetime',
              'collections', 'itertools', 'functools', 'pathlib', 'typing',
              'random', 'string', 'io', 'copy', 'abc', 'enum', 'dataclasses'}
    third_party = [imp for imp in imports if imp not in stdlib
                   and not imp.startswith('_')]

    # Pre-install missing packages
    if third_party:
        for pkg in third_party[:3]:  # limit to 3 auto-installs
            try:
                subprocess.run(
                    [sys.executable, '-m', 'pip', 'install', pkg,
                     '--break-system-packages', '-q'],
                    timeout=30, capture_output=True
                )
            except Exception as err:
                import logging
                logging.getLogger(__name__).error("Exception swallowed: %s", err)
                raise RuntimeError(f"Exception swallowed: {err}")

    # Add assertion wrapper: if code has no print/assert, add one
    wrapped = code + "\n# Execution complete\nprint('__EXECUTION_OK__')\n"

    with tempfile.NamedTemporaryFile(mode='w', suffix='.py',
                                     delete=False) as f:
        f.write(wrapped)
        fname = f.name

    try:
        result = subprocess.run(
            [sys.executable, fname],
            capture_output=True, text=True, timeout=timeout,
            env={k: v for k, v in __import__('os').environ.items()}
        )
        success = (result.returncode == 0 and
                   '__EXECUTION_OK__' in result.stdout)
        return success, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return False, "", f"Timeout after {timeout}s"
    except Exception as e:
        return False, "", str(e)
    finally:
        import os
        try:
            os.unlink(fname)
        except Exception as err:
            import logging
            logging.getLogger(__name__).error("Exception swallowed: %s", err)
            raise RuntimeError(f"Exception swallowed: {err}")


def code_execution_check(answer: str) -> VerificationCheck:
    start = time.time()
    blocks = extract_code_blocks(answer)
    if not blocks:
        return VerificationCheck(
            name="code_execution",
            verdict=VerificationVerdict.PASS,
            confidence=0.5,
            evidence=["No code blocks found to verify"],
            issues=[],
            latency_ms=(time.time() - start) * 1000,
        )

    issues = []
    all_succeeded = True
    evidence = []

    for i, block in enumerate(blocks[:3]):  # check up to 3 blocks
        success, stdout, stderr = sandbox_execute_code(block)
        if success:
            evidence.append(f"Block {i+1}: executed successfully")
        else:
            all_succeeded = False
            error_summary = stderr[:200] if stderr else "Unknown error"
            issues.append(f"Block {i+1} execution failed: {error_summary}")
            evidence.append(f"Block {i+1}: FAILED — {error_summary[:100]}")

    verdict = (VerificationVerdict.PASS if all_succeeded
               else VerificationVerdict.FAIL)
    return VerificationCheck(
        name="code_execution",
        verdict=verdict,
        confidence=0.90 if all_succeeded else 0.85,
        evidence=evidence,
        issues=issues,
        latency_ms=(time.time() - start) * 1000,
        is_fatal=not all_succeeded,
    )


# ── Math Verification Check ───────────────────────────────────────

def math_symbolic_check(answer: str, task: str) -> VerificationCheck:
    """
    V6 BUG FIXED: V6 extracts numbers with regex and compares.
    V7: uses sympy for symbolic verification when available.
    Falls back to plausibility check if sympy unavailable.
    """
    start = time.time()
    issues = []
    evidence = []

    # Try sympy first
    try:
        import sympy
        # Extract equations from answer
        equations = re.findall(r'([A-Za-z0-9\s\+\-\*\/\^\=\.]+=[^\n,]+)', answer)
        for eq_text in equations[:3]:
            try:
                lhs, rhs = eq_text.split('=', 1)
                lhs_sym = sympy.sympify(lhs.strip())
                rhs_sym = sympy.sympify(rhs.strip())
                diff = sympy.simplify(lhs_sym - rhs_sym)
                if diff != 0 and not isinstance(diff, sympy.core.symbol.Symbol):
                    issues.append(f"Math equation invalid: {eq_text.strip()} (diff={diff})")
                else:
                    evidence.append(f"Equation verified: {eq_text.strip()[:50]}")
            except Exception:
                evidence.append(f"Could not parse equation symbolically: {eq_text[:50]}")
    except ImportError:
        evidence.append("sympy not available — using plausibility check only")

    # Plausibility: check for obviously wrong numbers
    numbers = re.findall(r'\b\d+(?:\.\d+)?\b', answer)
    if numbers:
        max_num = max(float(n) for n in numbers)
        # Sanity: if task mentions "probability", no value should exceed 1
        if "probability" in task.lower() and max_num > 1.0:
            issues.append(f"Probability value {max_num} exceeds 1.0 — impossible")
        evidence.append(f"Found {len(numbers)} numeric values in answer")

    verdict = VerificationVerdict.FAIL if issues else VerificationVerdict.PASS
    return VerificationCheck(
        name="math_symbolic",
        verdict=verdict,
        confidence=0.80,
        evidence=evidence,
        issues=issues,
        latency_ms=(time.time() - start) * 1000,
        is_fatal=bool(issues),
    )


# ── LLM-Based Logic Check ─────────────────────────────────────────

LOGIC_CHECK_PROMPT = """You are a logical consistency verifier. Check this answer for logical errors only.

TASK: {task}

ANSWER: {answer}

Check for:
1. Non-sequiturs (conclusion doesn't follow from premises)
2. Circular reasoning (conclusion assumed in premise)
3. False dichotomies (only two options when more exist)
4. Internal contradictions (two statements that cannot both be true)

Respond in this EXACT format:
VERDICT: PASS or FAIL
ISSUES: (numbered list, or "none")
CONFIDENCE: (0.0-1.0)"""


REDERIVATION_PROMPT = """Solve this task completely from scratch. You will NOT see any existing answer.
Do NOT try to guess what a previous answer might have said.

TASK: {task}

Solve independently using your own reasoning. Show all steps.

SOLUTION:"""


# ── Verification Engine ───────────────────────────────────────────

class StrictVerificationEngine:
    """
    V7 strict verification with hard rejection and mandatory re-reasoning.

    KEY V7 GUARANTEE: If verify_depth >= "standard" and a FATAL issue is found,
    the engine DOES NOT return a passing result. It returns should_rerun=True
    and the orchestrator MUST re-run reasoning before outputting.
    """

    def __init__(self, model_router: Any, max_retry: int = 2):
        self.model_router = model_router
        self.max_retry    = max_retry
        self._stats = {"total": 0, "passed": 0, "failed": 0, "reruns": 0}

    async def verify(
        self,
        answer: str,
        task: str,
        verify_depth: str = "standard",
    ) -> VerificationReport:
        """
        Run all applicable verification checks based on depth.
        Returns a VerificationReport with hard pass/fail verdict.
        """
        start = time.time()
        self._stats["total"] += 1
        checks: List[VerificationCheck] = []

        # ── Always run: constitutional check ──────────────────────
        checks.append(constitutional_check(answer))

        if verify_depth in ("standard", "deep", "exhaustive"):
            # Code execution (async wrapper around sync)
            loop = asyncio.get_event_loop()
            code_check = await loop.run_in_executor(
                None, code_execution_check, answer
            )
            checks.append(code_check)

            # Math check
            if any(w in task.lower() for w in
                   ["calculat", "solve", "equation", "proof", "math",
                    "probability", "statistic", "formula"]):
                math_check = await loop.run_in_executor(
                    None, math_symbolic_check, answer, task
                )
                checks.append(math_check)

            # LLM logic check
            logic_check = await self._llm_logic_check(answer, task)
            checks.append(logic_check)

        if verify_depth in ("deep", "exhaustive"):
            # True independent re-derivation
            rederiv_check = await self._rederivation_check(answer, task)
            checks.append(rederiv_check)

        if verify_depth == "exhaustive":
            # Cross-model agreement check
            agreement_check = await self._cross_model_agreement(answer, task)
            checks.append(agreement_check)

        # ── Aggregate ─────────────────────────────────────────────
        fatal_issues = [i for c in checks for i in c.issues if c.is_fatal]
        all_issues   = [i for c in checks for i in c.issues]
        failed_checks = [c for c in checks if c.verdict == VerificationVerdict.FAIL]

        # Hard rejection: any fatal issue → should_rerun=True
        any_fatal = bool(fatal_issues)
        passed = not any_fatal and len(failed_checks) == 0

        overall_verdict = (VerificationVerdict.PASS if passed
                           else VerificationVerdict.FAIL if any_fatal
                           else VerificationVerdict.UNCERTAIN)

        # Aggregate confidence: min of failing checks, or mean of all
        if failed_checks:
            confidence = min(c.confidence for c in failed_checks) * 0.5
        else:
            confidence = (sum(c.confidence for c in checks) / len(checks)
                          if checks else 0.5)

        # Build re-run guidance
        rerun_guidance = ""
        if fatal_issues:
            rerun_guidance = (
                "MUST FIX before output: " +
                "; ".join(fatal_issues[:3])
            )

        if passed:
            self._stats["passed"] += 1
        else:
            self._stats["failed"] += 1
            if any_fatal:
                self._stats["reruns"] += 1

        return VerificationReport(
            overall_verdict=overall_verdict,
            checks=checks,
            passed=passed,
            fatal_issues=fatal_issues,
            all_issues=all_issues,
            confidence=round(confidence, 4),
            should_rerun=any_fatal,
            rerun_guidance=rerun_guidance,
            verification_depth=verify_depth,
            elapsed_ms=(time.time() - start) * 1000,
        )

    async def verify_with_retry(
        self,
        answer: str,
        task: str,
        generate_fn,           # async callable: (task, guidance) -> str
        verify_depth: str = "standard",
    ) -> Tuple[str, VerificationReport]:
        """
        Verify with hard-rejection retry loop.
        If verification fails, calls generate_fn to produce a new answer.
        Returns (final_answer, final_report).
        """
        current_answer = answer
        last_report    = None

        for attempt in range(self.max_retry + 1):
            report = await self.verify(current_answer, task, verify_depth)
            last_report = report

            if not report.should_rerun:
                return current_answer, report

            if attempt < self.max_retry:
                logger.info(
                    f"[Verification] Hard reject #{attempt+1}/{self.max_retry} — "
                    f"re-generating. Issues: {report.fatal_issues[:2]}"
                )
                guidance = report.rerun_guidance
                current_answer = await generate_fn(task, guidance)

        # Max retries reached — return best answer with warning
        logger.warning(
            f"[Verification] Max retries ({self.max_retry}) reached. "
            f"Outputting best available with UNCERTAIN verdict."
        )
        last_report.overall_verdict = VerificationVerdict.UNCERTAIN
        last_report.passed = False
        last_report.should_rerun = False
        return current_answer, last_report

    async def _llm_logic_check(self, answer: str, task: str) -> VerificationCheck:
        start = time.time()
        prompt = LOGIC_CHECK_PROMPT.format(
            task=task[:500], answer=answer[:1500]
        )
        try:
            response = await self.model_router.generate(
                prompt=prompt, role="analysis",
                temperature=0.2, max_tokens=400,
            )
            content = response.get("content", "")
            verdict_match = re.search(r'VERDICT:\s*(PASS|FAIL)', content, re.I)
            conf_match    = re.search(r'CONFIDENCE:\s*([\d.]+)', content)
            issues_match  = re.search(r'ISSUES:\s*(.*?)(?:CONFIDENCE|$)',
                                       content, re.DOTALL | re.I)

            verdict_str = verdict_match.group(1).upper() if verdict_match else "UNCERTAIN"
            confidence  = float(conf_match.group(1)) if conf_match else 0.6
            issues_text = issues_match.group(1).strip() if issues_match else ""

            issues = []
            if issues_text.lower() not in ("none", "no issues", ""):
                issues = [l.strip().lstrip("0123456789.-*• ")
                          for l in issues_text.split("\n")
                          if l.strip() and len(l.strip()) > 10]

            verdict = (VerificationVerdict.PASS if verdict_str == "PASS"
                       else VerificationVerdict.FAIL if verdict_str == "FAIL"
                       else VerificationVerdict.UNCERTAIN)

            return VerificationCheck(
                name="llm_logic",
                verdict=verdict,
                confidence=min(1.0, max(0.0, confidence)),
                evidence=[f"LLM logic check: {verdict_str}"],
                issues=issues[:5],
                latency_ms=(time.time() - start) * 1000,
                is_fatal=(verdict == VerificationVerdict.FAIL and bool(issues)),
            )
        except Exception as e:
            return VerificationCheck(
                name="llm_logic", verdict=VerificationVerdict.UNCERTAIN,
                confidence=0.5, evidence=[f"Check failed: {e}"],
                issues=[], latency_ms=(time.time() - start) * 1000,
            )

    async def _rederivation_check(self, answer: str, task: str) -> VerificationCheck:
        """
        V6 BUG FIXED: V6 passes the answer to the re-derivation model.
        V7: sends ONLY the task — model re-derives blindly.
        """
        start = time.time()
        prompt = REDERIVATION_PROMPT.format(task=task)
        try:
            response = await self.model_router.generate(
                prompt=prompt, role="reasoning",
                temperature=0.5, max_tokens=1500,
            )
            rederived = response.get("content", "")

            # Compare key conclusions (not full text — they may phrase things differently)
            similarity = self._semantic_similarity(answer, rederived)

            if similarity > 0.55:
                verdict = VerificationVerdict.PASS
                issues  = []
                evidence = [f"Re-derivation agrees (similarity={similarity:.2f})"]
            elif similarity > 0.30:
                verdict = VerificationVerdict.UNCERTAIN
                issues  = ["Re-derivation reached a different conclusion — partial agreement"]
                evidence = [f"Partial agreement (similarity={similarity:.2f})"]
            else:
                verdict = VerificationVerdict.FAIL
                issues  = [f"Independent re-derivation DISAGREES (similarity={similarity:.2f})"]
                evidence = [f"Re-derivation diverged significantly"]

            return VerificationCheck(
                name="rederivation",
                verdict=verdict,
                confidence=0.80,
                evidence=evidence,
                issues=issues,
                latency_ms=(time.time() - start) * 1000,
                is_fatal=(verdict == VerificationVerdict.FAIL),
            )
        except Exception as e:
            return VerificationCheck(
                name="rederivation", verdict=VerificationVerdict.UNCERTAIN,
                confidence=0.5, evidence=[f"Re-derivation failed: {e}"],
                issues=[], latency_ms=(time.time() - start) * 1000,
            )

    async def _cross_model_agreement(self, answer: str, task: str) -> VerificationCheck:
        """Ask a DIFFERENT role/model whether this answer looks correct."""
        start = time.time()
        prompt = (
            f"Does this answer correctly solve the task? "
            f"Reply with AGREE or DISAGREE and one sentence why.\n\n"
            f"TASK: {task[:400]}\nANSWER: {answer[:800]}"
        )
        try:
            response = await self.model_router.generate(
                prompt=prompt, role="fast",
                temperature=0.3, max_tokens=150,
            )
            content = response.get("content", "").upper()
            agreed = "AGREE" in content and "DISAGREE" not in content
            verdict = VerificationVerdict.PASS if agreed else VerificationVerdict.UNCERTAIN
            return VerificationCheck(
                name="cross_model_agreement",
                verdict=verdict, confidence=0.65,
                evidence=[f"Model response: {response.get('content','')[:100]}"],
                issues=[] if agreed else ["Cross-model agreement failed"],
                latency_ms=(time.time() - start) * 1000,
            )
        except Exception as e:
            return VerificationCheck(
                name="cross_model_agreement", verdict=VerificationVerdict.UNCERTAIN,
                confidence=0.5, evidence=[str(e)], issues=[],
                latency_ms=(time.time() - start) * 1000,
            )

    @staticmethod
    def _semantic_similarity(a: str, b: str) -> float:
        """Trigram Jaccard similarity between two texts."""
        def trigrams(text: str):
            words = re.sub(r'[^a-z0-9 ]', '', text.lower()).split()
            return {' '.join(words[i:i+3]) for i in range(len(words)-2)}

        ta, tb = trigrams(a), trigrams(b)
        if not ta or not tb:
            return 0.0
        return len(ta & tb) / len(ta | tb)

    def get_stats(self) -> Dict[str, Any]:
        total = self._stats["total"]
        return {
            "total":       total,
            "pass_rate":   round(self._stats["passed"] / max(total, 1), 3),
            "fail_rate":   round(self._stats["failed"] / max(total, 1), 3),
            "rerun_rate":  round(self._stats["reruns"] / max(total, 1), 3),
        }
