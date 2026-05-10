"""
Mythos Multi-Agent System — Full Mandatory Suite
=================================================
Implements all agents specified in the architecture mandate:

  ┌─────────────────────────────────────────────────────────────────┐
  │  Planner → Solver(s) → AdversarialCritic → IndependentVerifier │
  │                                        ↓                        │
  │                                   JudgeAgent                    │
  └─────────────────────────────────────────────────────────────────┘

Design principles:
- AdversarialCritic: MUST disagree. Breaks, not confirms.
  Truth > agreement. Echo chambers are failure modes.
- IndependentVerifier: Re-derives the answer from SCRATCH.
  Does NOT read the Solver's solution. Independent path.
- JudgeAgent: Weighs adversarial critique vs verification.
  Weighted: Verification(0.40) > Adversarial(0.30) > Agreement(0.30)
- Disagreement enforcer: Agents are seeded with opposing stances
  to prevent convergence on a false consensus.
"""

import asyncio
import json
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from utils.logger import SystemLogger

logger = SystemLogger(__name__)


# ══════════════════════════════════════════════════════════════════
# DATA TYPES
# ══════════════════════════════════════════════════════════════════

@dataclass
class AgentVerdict:
    agent:       str
    verdict:     str         # PASS | FAIL | UNCERTAIN | REVISED
    confidence:  float       # 0.0 – 1.0
    reasoning:   str
    issues:      List[str]   = field(default_factory=list)
    fixes:       List[str]   = field(default_factory=list)
    revised_output: str      = ""
    metadata:    Dict        = field(default_factory=dict)


@dataclass
class MultiAgentResult:
    task:                str
    solver_output:       str
    adversarial_verdict: Optional[AgentVerdict]
    verifier_verdict:    Optional[AgentVerdict]
    judge_verdict:       Optional[AgentVerdict]
    final_output:        str
    final_confidence:    float
    agents_agreed:       bool
    disagreement_log:    List[str] = field(default_factory=list)
    elapsed_ms:          float     = 0.0

    def to_dict(self) -> Dict:
        return {
            "task":               self.task[:100],
            "final_output":       self.final_output,
            "final_confidence":   round(self.final_confidence, 4),
            "agents_agreed":      self.agents_agreed,
            "disagreement_log":   self.disagreement_log,
            "adversarial":        self.adversarial_verdict.__dict__ if self.adversarial_verdict else {},
            "verifier":           self.verifier_verdict.__dict__    if self.verifier_verdict    else {},
            "judge":              self.judge_verdict.__dict__        if self.judge_verdict        else {},
        }


# ══════════════════════════════════════════════════════════════════
# 1. ADVERSARIAL CRITIC
# ══════════════════════════════════════════════════════════════════

_ADVERSARIAL_SYSTEM = """You are an ADVERSARIAL CRITIC. Your role is to BREAK solutions, not confirm them.

RULES (non-negotiable):
1. You MUST find at least one flaw. If you cannot, you are not trying hard enough.
2. Attack the STRONGEST version of the solution, not a strawman.
3. Probe: edge cases, failure modes, hidden assumptions, logic gaps, missing constraints.
4. Do NOT agree with the solver unless you have EXHAUSTED every attack vector.
5. Your value is in finding what's WRONG — consensus is your enemy.
6. If the solution is genuinely excellent, identify what it CANNOT handle.

You do not produce a revised solution. You produce a VERDICT."""

_ADVERSARIAL_PROMPT = """TASK: {task}

PROPOSED SOLUTION:
{solution}

ADVERSARIAL ANALYSIS — attack every layer:

LAYER 1 — LOGICAL VALIDITY
Does the reasoning chain hold? Find any logical leap, false premise, or circular argument.

LAYER 2 — EDGE CASES
What inputs or conditions cause this solution to fail?

LAYER 3 — HIDDEN ASSUMPTIONS
What does this solution assume that isn't stated? What happens when those assumptions break?

LAYER 4 — COMPLETENESS
What relevant cases, constraints, or requirements does this solution ignore?

LAYER 5 — ADVERSARIAL INPUTS
What is the hardest possible input for this solution? Can you construct one?

Respond in JSON:
{{
  "verdict": "FAIL|PASS_WITH_CAVEATS|PASS",
  "confidence": 0.0-1.0,
  "primary_flaw": "the most critical flaw found",
  "attacks": [
    {{"layer": "logical|edge_case|assumption|completeness|adversarial",
      "attack": "description of the attack",
      "severity": "critical|major|minor"}}
  ],
  "fixes_required": ["specific fix 1", "specific fix 2"],
  "reasoning": "full adversarial reasoning"
}}

IMPORTANT: If verdict is PASS, you must explain why every attack FAILED to break the solution."""


class AdversarialCritic:
    """
    Actively tries to break every solution.
    Seeded with an adversarial stance to enforce disagreement and
    prevent echo-chamber convergence on a wrong answer.
    """

    def __init__(self, model_router: Any):
        self.router = model_router
        self._verdicts: List[AgentVerdict] = []

    async def critique(self, task: str, solution: str) -> AgentVerdict:
        """Attack the solution from every angle. Return structured verdict."""
        prompt = _ADVERSARIAL_PROMPT.format(
            task=task[:800],
            solution=solution[:2000]
        )
        try:
            response = await self.router.complete(
                model="reasoning",
                prompt=prompt,
                system=_ADVERSARIAL_SYSTEM,
                temperature=0.7,   # higher temp = more creative attacks
                max_tokens=1500
            )
            raw = response.get("text", "")
            data = self._parse_json(raw) or {}

            attacks = data.get("attacks", [])
            critical_attacks = [a for a in attacks if a.get("severity") == "critical"]
            major_attacks    = [a for a in attacks if a.get("severity") == "major"]

            verdict = data.get("verdict", "PASS_WITH_CAVEATS")
            confidence = float(data.get("confidence", 0.5))

            # Force minimum attack pressure: if no issues found, flag as suspicious
            if not attacks:
                verdict = "PASS_WITH_CAVEATS"
                data["fixes_required"] = data.get("fixes_required", []) + [
                    "AdversarialCritic found no attacks — increase scrutiny or use deeper model"
                ]

            result = AgentVerdict(
                agent="adversarial_critic",
                verdict=verdict,
                confidence=confidence,
                reasoning=data.get("reasoning", raw[:300]),
                issues=[a.get("attack", "") for a in attacks],
                fixes=data.get("fixes_required", []),
                metadata={
                    "primary_flaw":    data.get("primary_flaw", ""),
                    "critical_attacks": len(critical_attacks),
                    "major_attacks":    len(major_attacks),
                    "total_attacks":    len(attacks),
                }
            )
            self._verdicts.append(result)
            logger.info(
                f"[AdversarialCritic] verdict={verdict} "
                f"attacks={len(attacks)} critical={len(critical_attacks)}"
            )
            return result

        except Exception as e:
            logger.error(f"[AdversarialCritic] Error: {e}")
            return AgentVerdict(
                agent="adversarial_critic", verdict="UNCERTAIN",
                confidence=0.3, reasoning=f"Critic failed: {e}",
                issues=["Adversarial critique failed — treat as unverified"],
            )

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
                except Exception as err:
                    import logging
                    logging.getLogger(__name__).error("Exception swallowed: %s", err)
                    raise RuntimeError(f"Exception swallowed: {err}")
        return None

    def get_stats(self) -> Dict:
        if not self._verdicts:
            return {"total": 0}
        fails    = sum(1 for v in self._verdicts if v.verdict == "FAIL")
        passes   = sum(1 for v in self._verdicts if v.verdict == "PASS")
        caveats  = sum(1 for v in self._verdicts if v.verdict == "PASS_WITH_CAVEATS")
        return {
            "total": len(self._verdicts), "fail": fails,
            "pass": passes, "pass_with_caveats": caveats,
            "avg_confidence": sum(v.confidence for v in self._verdicts) / len(self._verdicts)
        }


# ══════════════════════════════════════════════════════════════════
# 2. INDEPENDENT VERIFIER
# ══════════════════════════════════════════════════════════════════

_VERIFIER_SYSTEM = """You are an INDEPENDENT VERIFIER. You must re-derive the answer from scratch.

CRITICAL RULES:
1. You have NOT seen the proposed solution. Ignore it completely.
2. Derive the answer using ONLY the task description.
3. Show your complete reasoning chain step by step.
4. If you reach the same answer, confirm it. If different, flag it.
5. Do NOT anchor to any suggested answer. Your path must be independent.
6. Your value is in catching errors the original solver missed."""

_VERIFIER_PROMPT_BLIND = """TASK: {task}

Derive the answer from first principles. Show all steps.
Do NOT refer to any previous answer — you haven't seen one.

INDEPENDENT DERIVATION:"""

_VERIFIER_COMPARISON_PROMPT = """You independently derived an answer for a task.
Now compare your derivation against the proposed solution.

TASK: {task}

YOUR INDEPENDENT DERIVATION:
{your_derivation}

PROPOSED SOLUTION (to verify against):
{solution}

Compare and identify:
1. Do they reach the same conclusion? (yes/no + explanation)
2. Any steps in the proposed solution that contradict your derivation?
3. Any steps in your derivation that the proposed solution missed?
4. Confidence that the proposed solution is correct?

Respond in JSON:
{{
  "conclusions_match": true/false,
  "confidence": 0.0-1.0,
  "agreement_type": "full|partial|contradiction|different_approach_same_result",
  "discrepancies": ["specific difference 1", "specific difference 2"],
  "missing_in_solution": ["what your derivation found that solution missed"],
  "verdict": "VERIFIED|PARTIALLY_VERIFIED|CONTRADICTED|INCONCLUSIVE",
  "reasoning": "full comparison reasoning"
}}"""


class IndependentVerifier:
    """
    Re-derives the answer from scratch, INDEPENDENT of the solver's output.
    Only compares at the end to detect divergence.

    This is the core anti-hallucination mechanism:
    two independent reasoning paths arriving at the same answer
    is strong evidence of correctness.
    Two paths diverging is a strong signal of an error somewhere.
    """

    def __init__(self, model_router: Any):
        self.router = model_router
        self._verifications: List[AgentVerdict] = []

    async def verify(self, task: str, proposed_solution: str) -> AgentVerdict:
        """
        Phase 1: Blind derivation (no peeking at solution)
        Phase 2: Comparison to detect divergence
        """
        # Phase 1: Independent derivation
        try:
            blind_response = await self.router.complete(
                model="reasoning",
                prompt=_VERIFIER_PROMPT_BLIND.format(task=task[:800]),
                system=_VERIFIER_SYSTEM,
                temperature=0.4,
                max_tokens=2000
            )
            my_derivation = blind_response.get("text", "")

            if not my_derivation:
                raise ValueError("Empty independent derivation")

            # Phase 2: Comparison
            compare_response = await self.router.complete(
                model="reasoning",
                prompt=_VERIFIER_COMPARISON_PROMPT.format(
                    task=task[:500],
                    your_derivation=my_derivation[:1200],
                    solution=proposed_solution[:1200]
                ),
                temperature=0.3,
                max_tokens=1000
            )
            comparison = self._parse_json(compare_response.get("text", "")) or {}

            verdict_str   = comparison.get("verdict", "INCONCLUSIVE")
            confidence    = float(comparison.get("confidence", 0.5))
            discrepancies = comparison.get("discrepancies", [])
            missing       = comparison.get("missing_in_solution", [])
            conclusions_match = comparison.get("conclusions_match", False)

            # Adjust confidence based on match
            if conclusions_match and not discrepancies:
                confidence = min(1.0, confidence * 1.15)  # boost for full agreement
            elif discrepancies:
                confidence = max(0.0, confidence * 0.7)   # reduce for discrepancies

            result = AgentVerdict(
                agent="independent_verifier",
                verdict=verdict_str,
                confidence=confidence,
                reasoning=comparison.get("reasoning", "")[:400],
                issues=discrepancies + missing,
                revised_output=my_derivation,  # expose our own derivation
                metadata={
                    "conclusions_match":  conclusions_match,
                    "agreement_type":     comparison.get("agreement_type", "unknown"),
                    "discrepancies_count": len(discrepancies),
                    "missing_count":       len(missing),
                    "my_derivation_len":   len(my_derivation),
                }
            )
            self._verifications.append(result)
            logger.info(
                f"[IndependentVerifier] verdict={verdict_str} "
                f"match={conclusions_match} discrepancies={len(discrepancies)}"
            )
            return result

        except Exception as e:
            logger.error(f"[IndependentVerifier] Error: {e}")
            return AgentVerdict(
                agent="independent_verifier", verdict="INCONCLUSIVE",
                confidence=0.4, reasoning=f"Verification failed: {e}",
                issues=["Independent verification could not complete"],
            )

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
                except Exception as err:
                    import logging
                    logging.getLogger(__name__).error("Exception swallowed: %s", err)
                    raise RuntimeError(f"Exception swallowed: {err}")
        return None

    def get_stats(self) -> Dict:
        if not self._verifications:
            return {"total": 0}
        verified = sum(1 for v in self._verifications if v.verdict == "VERIFIED")
        return {
            "total": len(self._verifications),
            "verified": verified,
            "verification_rate": verified / len(self._verifications),
        }


# ══════════════════════════════════════════════════════════════════
# 3. JUDGE AGENT
# ══════════════════════════════════════════════════════════════════

_JUDGE_SYSTEM = """You are the JUDGE AGENT of a multi-agent reasoning system.

You receive:
- The original task
- A proposed solution from the Solver
- An adversarial critique (attempted to BREAK the solution)
- An independent verification (re-derived from scratch)

Your job: determine the FINAL VERDICT using evidence-weighted reasoning.

Weighting (non-negotiable):
- Independent Verification carries 40% of your decision
- Adversarial Critique carries 30% of your decision
- Solution Quality carries 30% of your decision

Rules:
1. If Verifier says CONTRADICTED: REJECT unless you have overwhelming reason not to
2. If Adversarial says FAIL with critical attacks: REJECT unless Verifier strongly disagrees
3. If both Verifier and Adversarial pass: ACCEPT with high confidence
4. Disagreement between agents: produce a SYNTHESIZED answer resolving the conflict
5. Truth > consensus. You must decide even if uncertain."""

_JUDGE_PROMPT = """TASK: {task}

PROPOSED SOLUTION:
{solution}

ADVERSARIAL CRITIQUE:
Verdict: {adv_verdict} | Confidence: {adv_confidence:.2f}
Critical attacks: {adv_attacks}
Issues: {adv_issues}

INDEPENDENT VERIFICATION:
Verdict: {ver_verdict} | Confidence: {ver_confidence:.2f}
Conclusions match: {ver_match}
Discrepancies: {ver_discrepancies}
Independent derivation (first 500 chars): {ver_derivation}

Weighting: Verification(40%) > Adversarial(30%) > Solution Quality(30%)

Respond in JSON:
{{
  "final_verdict": "ACCEPT|ACCEPT_WITH_REVISIONS|REJECT|ESCALATE",
  "final_confidence": 0.0-1.0,
  "final_output": "the best possible answer (original, revised, or synthesized)",
  "decision_reasoning": "how you weighted the evidence",
  "revision_applied": true/false,
  "revisions_made": ["what changed if revised"],
  "escalate_reason": "why to escalate if ESCALATE"
}}"""


class JudgeAgent:
    """
    Final arbitration between Solver, AdversarialCritic, and IndependentVerifier.
    Applies evidence-weighted decision making with a mandatory weighting schema.
    """

    # Mandatory weights from spec
    WEIGHT_VERIFICATION  = 0.40
    WEIGHT_ADVERSARIAL   = 0.30
    WEIGHT_SOLUTION_QUAL = 0.30

    def __init__(self, model_router: Any):
        self.router   = model_router
        self._rulings: List[AgentVerdict] = []

    async def adjudicate(
        self,
        task:                  str,
        solution:              str,
        adversarial_verdict:   Optional[AgentVerdict],
        verifier_verdict:      Optional[AgentVerdict],
    ) -> AgentVerdict:
        """Produce final binding verdict with mandatory evidence weighting."""

        adv = adversarial_verdict
        ver = verifier_verdict

        # Fast path: if verifier says CONTRADICTED, reject immediately
        if ver and ver.verdict == "CONTRADICTED" and (ver.confidence > 0.70):
            result = AgentVerdict(
                agent="judge",
                verdict="REJECT",
                confidence=ver.confidence,
                reasoning="Independent verifier contradiction — hard reject without LLM judge",
                issues=ver.issues,
                revised_output=ver.revised_output or "",
                metadata={"fast_path": "verifier_contradiction"}
            )
            self._rulings.append(result)
            return result

        # Fast path: if adversarial passes AND verifier passes, accept
        adv_pass = adv and adv.verdict in ("PASS", "PASS_WITH_CAVEATS")
        ver_pass = ver and ver.verdict in ("VERIFIED", "PARTIALLY_VERIFIED")
        if adv_pass and ver_pass and (not adv.issues or len(adv.issues) <= 1):
            conf = (
                ver.confidence * self.WEIGHT_VERIFICATION +
                adv.confidence * self.WEIGHT_ADVERSARIAL +
                0.85           * self.WEIGHT_SOLUTION_QUAL
            )
            result = AgentVerdict(
                agent="judge",
                verdict="ACCEPT",
                confidence=round(min(1.0, conf), 4),
                reasoning="Both adversarial and independent verifier passed — accept",
                revised_output=solution,
                metadata={"fast_path": "both_pass"}
            )
            self._rulings.append(result)
            return result

        # Full LLM judge
        try:
            prompt = _JUDGE_PROMPT.format(
                task=task[:600],
                solution=solution[:1500],
                adv_verdict=adv.verdict         if adv else "UNAVAILABLE",
                adv_confidence=adv.confidence   if adv else 0.5,
                adv_attacks=str(adv.metadata.get("total_attacks", 0)) if adv else "0",
                adv_issues="; ".join(adv.issues[:3]) if adv else "none",
                ver_verdict=ver.verdict          if ver else "UNAVAILABLE",
                ver_confidence=ver.confidence    if ver else 0.5,
                ver_match=ver.metadata.get("conclusions_match", False) if ver else False,
                ver_discrepancies="; ".join(ver.issues[:3]) if ver else "none",
                ver_derivation=(ver.revised_output or "")[:500] if ver else "",
            )

            response = await self.router.complete(
                model="reasoning",
                prompt=prompt,
                system=_JUDGE_SYSTEM,
                temperature=0.3,
                max_tokens=1500
            )
            data = self._parse_json(response.get("text", "")) or {}

            final_verdict  = data.get("final_verdict", "ACCEPT")
            final_conf     = float(data.get("final_confidence", 0.6))
            final_output   = data.get("final_output", solution) or solution
            revisions      = data.get("revisions_made", [])
            escalate_reason= data.get("escalate_reason", "")

            result = AgentVerdict(
                agent="judge",
                verdict=final_verdict,
                confidence=final_conf,
                reasoning=data.get("decision_reasoning", "")[:400],
                issues=[escalate_reason] if escalate_reason else [],
                fixes=revisions,
                revised_output=final_output,
                metadata={
                    "revision_applied":  data.get("revision_applied", False),
                    "adv_weight":        self.WEIGHT_ADVERSARIAL,
                    "ver_weight":        self.WEIGHT_VERIFICATION,
                    "sol_weight":        self.WEIGHT_SOLUTION_QUAL,
                }
            )
            self._rulings.append(result)
            logger.info(
                f"[JudgeAgent] verdict={final_verdict} "
                f"confidence={final_conf:.3f} revised={data.get('revision_applied',False)}"
            )
            return result

        except Exception as e:
            logger.error(f"[JudgeAgent] Error: {e}")
            # Fallback: if no LLM judge, apply rule-based decision
            return self._rule_based_fallback(solution, adv, ver)

    def _rule_based_fallback(
        self, solution: str,
        adv: Optional[AgentVerdict],
        ver: Optional[AgentVerdict]
    ) -> AgentVerdict:
        """Rule-based fallback when LLM judge fails."""
        # Weight-based score
        adv_score = (1.0 if adv and adv.verdict == "PASS" else
                     0.6 if adv and adv.verdict == "PASS_WITH_CAVEATS" else 0.3)
        ver_score = (1.0 if ver and ver.verdict == "VERIFIED" else
                     0.7 if ver and ver.verdict == "PARTIALLY_VERIFIED" else 0.3)
        weighted  = (ver_score  * self.WEIGHT_VERIFICATION +
                     adv_score  * self.WEIGHT_ADVERSARIAL +
                     0.75       * self.WEIGHT_SOLUTION_QUAL)

        verdict = "ACCEPT" if weighted >= 0.65 else "REJECT"
        return AgentVerdict(
            agent="judge", verdict=verdict,
            confidence=round(weighted, 4),
            reasoning=f"Rule-based fallback: adv={adv_score:.2f} ver={ver_score:.2f}",
            revised_output=solution,
            metadata={"fallback": True}
        )

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
                except Exception as err:
                    import logging
                    logging.getLogger(__name__).error("Exception swallowed: %s", err)
                    raise RuntimeError(f"Exception swallowed: {err}")
        return None

    def get_stats(self) -> Dict:
        if not self._rulings:
            return {"total": 0}
        accepted   = sum(1 for r in self._rulings if r.verdict in ("ACCEPT", "ACCEPT_WITH_REVISIONS"))
        rejected   = sum(1 for r in self._rulings if r.verdict == "REJECT")
        escalated  = sum(1 for r in self._rulings if r.verdict == "ESCALATE")
        return {
            "total":     len(self._rulings),
            "accepted":  accepted,
            "rejected":  rejected,
            "escalated": escalated,
            "acceptance_rate": round(accepted / len(self._rulings), 3),
        }


# ══════════════════════════════════════════════════════════════════
# 4. MULTI-AGENT ORCHESTRATOR
# ══════════════════════════════════════════════════════════════════

class MultiAgentOrchestrator:
    """
    Coordinates the full mandatory agent pipeline:
    Solver → Adversarial Critic ↗
                                 → Judge → Final Verdict
    Independent Verifier       ↗

    Adversarial Critic and Independent Verifier run IN PARALLEL
    to prevent cross-contamination and save latency.
    """

    def __init__(self, model_router: Any):
        self.router               = model_router
        self.adversarial_critic   = AdversarialCritic(model_router)
        self.independent_verifier = IndependentVerifier(model_router)
        self.judge                = JudgeAgent(model_router)
        self._runs: List[MultiAgentResult] = []

    async def run(
        self,
        task:          str,
        solver_output: str,
        context:       Dict[str, Any] = None,
    ) -> MultiAgentResult:
        """
        Run the full mandatory agent pipeline.
        Adversarial and Verifier run concurrently.
        Judge receives both results and makes final binding decision.
        """
        start = time.time()
        logger.info(f"[MultiAgent] Starting pipeline for: {task[:60]}...")

        # ── Parallel: Adversarial Critic + Independent Verifier ────
        adv_task = self.adversarial_critic.critique(task, solver_output)
        ver_task = self.independent_verifier.verify(task, solver_output)

        adv_verdict, ver_verdict = await asyncio.gather(
            adv_task, ver_task, return_exceptions=True
        )

        # Handle exceptions gracefully
        if isinstance(adv_verdict, Exception):
            logger.warning(f"[MultiAgent] AdversarialCritic failed: {adv_verdict}")
            adv_verdict = AgentVerdict(
                agent="adversarial_critic", verdict="UNCERTAIN",
                confidence=0.4, reasoning=str(adv_verdict),
                issues=["Adversarial critique unavailable"]
            )
        if isinstance(ver_verdict, Exception):
            logger.warning(f"[MultiAgent] IndependentVerifier failed: {ver_verdict}")
            ver_verdict = AgentVerdict(
                agent="independent_verifier", verdict="INCONCLUSIVE",
                confidence=0.4, reasoning=str(ver_verdict),
                issues=["Independent verification unavailable"]
            )

        # ── Sequential: Judge ──────────────────────────────────────
        judge_verdict = await self.judge.adjudicate(
            task=task,
            solution=solver_output,
            adversarial_verdict=adv_verdict,
            verifier_verdict=ver_verdict,
        )

        # ── Disagreement log ──────────────────────────────────────
        disagreements = []
        if adv_verdict.verdict == "FAIL" and ver_verdict.verdict == "VERIFIED":
            disagreements.append(
                "CONFLICT: Adversarial says FAIL but Verifier says VERIFIED — "
                "Judge arbitration required"
            )
        if (adv_verdict.verdict == "PASS" and
                ver_verdict.verdict in ("CONTRADICTED", "INCONCLUSIVE")):
            disagreements.append(
                "CONFLICT: Adversarial passes but Verifier finds contradiction"
            )
        if adv_verdict.issues and not ver_verdict.issues:
            disagreements.append(
                f"Adversarial found {len(adv_verdict.issues)} issues Verifier didn't flag"
            )

        # ── Final output ──────────────────────────────────────────
        final_output = (
            judge_verdict.revised_output or
            ver_verdict.revised_output   or
            solver_output
        )
        agents_agreed = (
            adv_verdict.verdict in ("PASS", "PASS_WITH_CAVEATS") and
            ver_verdict.verdict in ("VERIFIED", "PARTIALLY_VERIFIED") and
            judge_verdict.verdict in ("ACCEPT", "ACCEPT_WITH_REVISIONS")
        )

        result = MultiAgentResult(
            task=task,
            solver_output=solver_output,
            adversarial_verdict=adv_verdict,
            verifier_verdict=ver_verdict,
            judge_verdict=judge_verdict,
            final_output=final_output,
            final_confidence=judge_verdict.confidence,
            agents_agreed=agents_agreed,
            disagreement_log=disagreements,
            elapsed_ms=round((time.time() - start) * 1000, 2),
        )
        self._runs.append(result)

        logger.info(
            f"[MultiAgent] Pipeline complete | "
            f"adv={adv_verdict.verdict} ver={ver_verdict.verdict} "
            f"judge={judge_verdict.verdict} conf={judge_verdict.confidence:.3f} "
            f"agreed={agents_agreed} disagreements={len(disagreements)}"
        )
        return result

    def get_stats(self) -> Dict:
        if not self._runs:
            return {"total_runs": 0}
        agreed = sum(1 for r in self._runs if r.agents_agreed)
        return {
            "total_runs":         len(self._runs),
            "agreement_rate":     round(agreed / len(self._runs), 3),
            "avg_confidence":     round(sum(r.final_confidence for r in self._runs) / len(self._runs), 4),
            "adversarial":        self.adversarial_critic.get_stats(),
            "verifier":           self.independent_verifier.get_stats(),
            "judge":              self.judge.get_stats(),
        }
