"""Adversarial Verifier - Phase 7 Mythos Omega.

Implements counter-claim generation, contradiction search, penalty application.
Supports early exit and uses MULTIPLICATIVE penalties (not additive).
AVOIDS same-model bias by using different configurations.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class VerificationResult:
    passed: bool
    confidence: float
    penalties_applied: List[str]
    counter_claims: List[str]
    contradictions_found: List[Dict[str, Any]]
    early_exit_reason: Optional[str] = None


class AdversarialVerifier:
    """
    Adversarial verifier that:
    1. Generates counter-claims using DIFFERENT model config (avoid bias)
    2. Searches for contradictions
    3. Applies MULTIPLICATIVE penalties (not additive)
    4. Supports early exit on critical failures
    """

    def __init__(
        self,
        model_gateway: Any,
        config: Optional[Dict[str, Any]] = None,
    ):
        self.model_gateway = model_gateway
        self.config = config or {}
        self._penalty_multipliers = {
            "contradiction": 0.7,      # 30% penalty
            "counter_claim": 0.8,        # 20% penalty
            "low_consensus": 0.85,       # 15% penalty
            "source_uncertainty": 0.9,    # 10% penalty
            "factual_error": 0.5,         # 50% penalty (severe)
        }
        self._early_exit_threshold = self.config.get("early_exit_threshold", 0.4)

    async def verify(
        self,
        result: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> VerificationResult:
        """
        Main verification entry point.
        Uses adversarial approach with early exit support.
        """
        verification_result = VerificationResult(
            passed=True,
            confidence=1.0,
            penalties_applied=[],
            counter_claims=[],
            contradictions_found=[],
        )

        output = result.get("output", "") or result.get("response", "") or ""
        if not output:
            verification_result.passed = False
            verification_result.confidence = 0.1
            verification_result.early_exit_reason = "Empty output"
            return verification_result

        # Early exit check: if confidence already very low
        current_confidence = result.get("confidence", 1.0)
        if current_confidence < self._early_exit_threshold:
            verification_result.passed = False
            verification_result.confidence = current_confidence * 0.5
            verification_result.early_exit_reason = f"Pre-verification confidence too low: {current_confidence}"
            # Still apply multiplicative penalty
            verification_result.confidence *= self._penalty_multipliers["low_consensus"]
            verification_result.penalties_applied.append("early_exit_low_confidence")
            return verification_result

        # Step 1: Generate counter-claims using DIFFERENT model config
        counter_claims = await self._generate_counter_claims(output, context)
        verification_result.counter_claims = counter_claims

        # Step 2: Search for contradictions between output and counter-claims
        contradictions = self._find_contradictions(output, counter_claims)
        verification_result.contradictions_found = contradictions

        # Step 3: Apply MULTIPLICATIVE penalties (not additive)
        confidence = current_confidence

        if contradictions:
            # Multiplicative penalty for contradictions
            penalty = self._penalty_multipliers["contradiction"] ** len(contradictions)
            confidence *= penalty
            verification_result.penalties_applied.append(f"contradiction x{len(contradictions)}")

        if counter_claims:
            # Check if counter-claims significantly disagree
            strong_disagreement = sum(
                1 for cc in counter_claims
                if self._is_strong_disagreement(output, cc)
            )
            if strong_disagreement:
                penalty = self._penalty_multipliers["counter_claim"] ** strong_disagreement
                confidence *= penalty
                verification_result.penalties_applied.append(f"counter_claim x{strong_disagreement}")

        # Check for factual errors (if grounding available)
        if context and context.get("grounding_failed"):
            confidence *= self._penalty_multipliers["factual_error"]
            verification_result.penalties_applied.append("grounding_failure")

        # Update result
        verification_result.confidence = max(0.01, confidence)
        verification_result.passed = verification_result.confidence > self._early_exit_threshold

        # If failed, ensure confidence is capped low (audit requirement)
        if not verification_result.passed:
            verification_result.confidence = min(verification_result.confidence, 0.4)
            verification_result.early_exit_reason = "Verification failed"

        return verification_result

    async def _generate_counter_claims(
        self,
        output: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        """
        Generate counter-claims using DIFFERENT model configuration.
        AVOIDS same-model bias by using different temperature, role, or model.
        """
        if not self.model_gateway:
            return []

        # Use DIFFERENT config: higher temperature, different role
        # This avoids the same reasoning path bias mentioned in audit
        prompt = f"""You are a critical fact-checker. Your job is to find potential errors or 
alternative interpretations in the following statement. Do NOT agree - look for what could be wrong.

Statement: {output[:1000]}

Generate 2-3 counter-claims or alternative interpretations that challenge this statement.
Be specific and factual. Format as a list."""

        try:
            # Use different temperature and role to avoid bias
            response = await asyncio.to_thread(
                self.model_gateway.generate,
                prompt=prompt,
                task="fact_check",  # Different from main task
                temperature=0.7,     # Higher than main (avoids same path)
                max_tokens=500,
            )

            content = response.get("content", "") or response.get("response", "")
            if not content:
                return []

            # Extract counter-claims (one per line)
            claims = [
                line.strip().lstrip("0123456789.-*• ")
                for line in content.split("\n")
                if line.strip() and len(line.strip()) > 20
            ]
            return claims[:3]

        except Exception as e:
            logger.error("Counter-claim generation failed: %s", e)
            return []

    def _find_contradictions(
        self,
        output: str,
        counter_claims: List[str],
    ) -> List[Dict[str, Any]]:
        """Find contradictions between output and counter-claims."""
        contradictions = []

        for i, claim in enumerate(counter_claims):
            if self._is_strong_disagreement(output, claim):
                contradictions.append({
                    "type": "output_vs_counter_claim",
                    "output_excerpt": output[:200],
                    "counter_claim": claim,
                    "severity": "high" if self._is_direct_contradiction(output, claim) else "medium",
                })

        return contradictions

    def _is_strong_disagreement(self, text_a: str, text_b: str) -> bool:
        """Check if two texts strongly disagree."""
        # Normalize
        a_lower = text_a.lower()
        b_lower = text_b.lower()

        # Check for direct opposites
        opposites = [
            ("is", "is not"), ("was", "was not"), ("can", "cannot"),
            ("always", "never"), ("all", "none"), ("true", "false"),
            ("yes", "no"), ("increase", "decrease"), ("more", "less"),
            ("higher", "lower"), ("better", "worse"), ("positive", "negative"),
        ]

        for pos, neg in opposites:
            if pos in a_lower and neg in b_lower:
                return True
            if neg in a_lower and pos in b_lower:
                return True

        # Check for numerical disagreements
        nums_a = re.findall(r'\d+(?:\.\d+)?', text_a)
        nums_b = re.findall(r'\d+(?:\.\d+)?', text_b)

        if nums_a and nums_b:
            try:
                avg_a = sum(float(n) for n in nums_a) / len(nums_a)
                avg_b = sum(float(n) for n in nums_b) / len(nums_b)
                if avg_a > 0 and avg_b > 0:
                    ratio = min(avg_a, avg_b) / max(avg_a, avg_b)
                    if ratio < 0.7:  # More than 30% difference
                        return True
            except (ValueError, ZeroDivisionError):
                pass

        return False

    def _is_direct_contradiction(self, text_a: str, text_b: str) -> bool:
        """Check if texts directly contradict each other."""
        # More strict check for direct contradiction
        a_lower = text_a.lower()
        b_lower = text_b.lower()

        # Direct negations
        if ("not " in a_lower and "not " in b_lower):
            return False  # Both negative doesn't mean contradiction
        if ("not " in a_lower or "never " in a_lower) and not ("not " in b_lower or "never " in b_lower):
            return True

        return self._is_strong_disagreement(text_a, text_b)

    async def verify_with_early_exit(
        self,
        result: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> VerificationResult:
        """
        Verification with early exit support.
        If critical failure detected, exits immediately without full verification.
        """
        # Quick pre-check: empty or garbage output
        output = result.get("output", "") or result.get("response", "")
        if not output or len(output.strip()) < 10:
            return VerificationResult(
                passed=False,
                confidence=0.1,
                penalties_applied=["empty_output"],
                counter_claims=[],
                contradictions_found=[],
                early_exit_reason="Empty or too short output",
            )

        # Quick pre-check: contradiction already detected in grounding
        if context and context.get("contradiction_detected"):
            # Skip full verification, apply penalty directly
            confidence = result.get("confidence", 1.0)
            confidence *= self._penalty_multipliers["contradiction"]
            return VerificationResult(
                passed=confidence > self._early_exit_threshold,
                confidence=max(0.01, min(confidence, 0.4)),  # Cap at 0.4 if failed
                penalties_applied=["grounding_contradiction_early_exit"],
                counter_claims=[],
                contradictions_found=[{"type": "from_grounding"}],
                early_exit_reason="Contradiction detected in grounding",
            )

        # Otherwise, run full verification
        return await self.verify(result, context)
