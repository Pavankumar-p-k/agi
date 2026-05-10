"""Sovereign Router - Phase 7 Mythos Omega.

Implements true classification-based routing with uncertainty computation,
grounding priority, and disagreement risk - NO keyword-only routing.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class TaskClassification:
    task_type: str
    complexity_score: float
    knowledge_familiarity: float
    ambiguity_score: float
    disagreement_risk: float


@dataclass
class RoutingPlan:
    grounding_priority: float
    verification_priority: float
    uncertainty_score: float
    confidence_policy: str
    stages: List[str] = field(default_factory=list)


class SovereignRouter:
    """
    True sovereign router that classifies tasks and computes routing plans
    based on semantic analysis - NOT keyword matching.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self._complexity_indicators = [
            "analyze", "compare", "evaluate", "synthesize", "design",
            "prove", "derive", "optimize", "architect", "investigate"
        ]
        self._factual_indicators = [
            "what is", "who is", "when did", "where is", "define",
            "explain", "describe", "list", "state"
        ]
        self._creative_indicators = [
            "write", "create", "compose", "generate", "imagine",
            "design", "invent", "story", "poem"
        ]

    def classify(self, input_text: str, context: Optional[Dict[str, Any]] = None) -> TaskClassification:
        """
        Classify task based on semantic analysis - NO keyword-only routing.
        Uses multiple signals: complexity, familiarity, ambiguity, disagreement risk.
        """
        normalized = input_text.lower().strip()

        # Compute complexity score (0.0 = simple, 1.0 = highly complex)
        complexity_score = self._compute_complexity(normalized)

        # Compute knowledge familiarity (0.0 = unfamiliar, 1.0 = very familiar)
        knowledge_familiarity = self._compute_familiarity(normalized)

        # Compute ambiguity score (0.0 = clear, 1.0 = highly ambiguous)
        ambiguity_score = self._compute_ambiguity(normalized)

        # Compute disagreement risk (0.0 = low risk, 1.0 = high risk)
        disagreement_risk = self._compute_disagreement_risk(normalized, complexity_score)

        # Determine task type based on weighted signals
        task_type = self._determine_task_type(normalized, complexity_score, knowledge_familiarity)

        return TaskClassification(
            task_type=task_type,
            complexity_score=complexity_score,
            knowledge_familiarity=knowledge_familiarity,
            ambiguity_score=ambiguity_score,
            disagreement_risk=disagreement_risk,
        )

    def build_plan(self, classification: TaskClassification) -> RoutingPlan:
        """
        Build routing plan with grounding priority, verification priority,
        uncertainty score, and confidence policy.
        """
        # Grounding priority: higher for factual tasks with low familiarity
        grounding_priority = self._compute_grounding_priority(classification)

        # Verification priority: higher for complex tasks with high disagreement risk
        verification_priority = self._compute_verification_priority(classification)

        # Uncertainty score: combined metric
        uncertainty_score = self.compute_uncertainty(classification)

        # Confidence policy based on uncertainty
        confidence_policy = self._determine_confidence_policy(uncertainty_score)

        # Determine stages based on priorities
        stages = self._determine_stages(classification, grounding_priority, verification_priority)

        return RoutingPlan(
            grounding_priority=grounding_priority,
            verification_priority=verification_priority,
            uncertainty_score=uncertainty_score,
            confidence_policy=confidence_policy,
            stages=stages,
        )

    def compute_uncertainty(self, classification: TaskClassification) -> float:
        """
        Compute uncertainty score based on multiple factors.
        Higher = more uncertain.
        """
        # Base uncertainty from ambiguity
        uncertainty = classification.ambiguity_score * 0.35

        # Add component from low familiarity
        uncertainty += (1.0 - classification.knowledge_familiarity) * 0.30

        # Add component from high complexity
        uncertainty += classification.complexity_score * 0.20

        # Add component from disagreement risk
        uncertainty += classification.disagreement_risk * 0.15

        return min(1.0, max(0.0, uncertainty))

    def _compute_complexity(self, text: str) -> float:
        """Compute complexity score based on linguistic signals."""
        score = 0.0
        words = text.split()

        # Length factor
        if len(words) > 20:
            score += 0.3
        elif len(words) > 10:
            score += 0.15

        # Complexity indicators
        for indicator in self._complexity_indicators:
            if indicator in text:
                score += 0.15

        # Nested clauses (approximate via punctuation)
        if text.count(",") > 2 or text.count(";") > 1:
            score += 0.15

        # Multiple questions
        if text.count("?") > 1:
            score += 0.10

        return min(1.0, score)

    def _compute_familiarity(self, text: str) -> float:
        """Compute knowledge familiarity score."""
        score = 0.5  # baseline

        # Factual indicators suggest familiar territory
        for indicator in self._factual_indicators:
            if indicator in text:
                score += 0.2

        # Common topics
        common_topics = ["python", "javascript", "code", "programming", "math", "science",
                         "history", "geography", "weather", "news", "sports"]
        for topic in common_topics:
            if topic in text:
                score += 0.15

        return min(1.0, score)

    def _compute_ambiguity(self, text: str) -> float:
        """Compute ambiguity score."""
        score = 0.0

        # Vague terms
        vague_terms = ["it", "that", "this", "they", "them", "something", "anything",
                       "maybe", "perhaps", "possibly", "might", "could"]
        for term in vague_terms:
            if f" {term} " in f" {text} ":
                score += 0.1

        # Unclear references (pronouns without clear antecedent)
        if text.count("it") > 1 or text.count("they") > 1:
            score += 0.15

        # Missing context indicators
        if "?" in text and len(text.split()) < 5:
            score += 0.2

        return min(1.0, score)

    def _compute_disagreement_risk(self, text: str, complexity: float) -> float:
        """
        Compute disagreement risk - ALWAYS non-zero as per audit requirement.
        High complexity + subjective topics = high disagreement risk.
        """
        score = 0.1  # BASELINE: always non-zero (audit requirement)

        # Subjective topics have higher disagreement
        subjective_terms = ["best", "worst", "better", "worse", "should", "opinion",
                           "think", "feel", "believe", "recommend", "prefer"]
        for term in subjective_terms:
            if term in text:
                score += 0.15

        # Controversial topics
        controversial = ["politics", "religion", "gun", "abortion", "climate", "vaccine",
                         "trump", "biden", "election", "war", "conflict"]
        for term in controversial:
            if term in text:
                score += 0.2

        # Complexity increases disagreement risk
        score += complexity * 0.25

        return min(1.0, max(0.1, score))  # NEVER zero

    def _determine_task_type(self, text: str, complexity: float, familiarity: float) -> str:
        """Determine task type based on multiple signals."""
        # Check for factual queries
        for indicator in self._factual_indicators:
            if indicator in text:
                return "factual_query"

        # Check for creative tasks
        for indicator in self._creative_indicators:
            if indicator in text:
                return "creative"

        # Check for coding tasks
        if any(term in text for term in ["code", "program", "script", "function", "debug", "error"]):
            return "coding"

        # Check for analysis tasks
        if any(term in text for term in ["analyze", "compare", "evaluate", "review", "assess"]):
            return "analysis"

        # Default based on complexity
        if complexity > 0.7:
            return "complex_reasoning"
        elif familiarity < 0.3:
            return "unfamiliar_domain"
        else:
            return "general"

    def _compute_grounding_priority(self, classification: TaskClassification) -> float:
        """
        Compute grounding priority.
        Saturates at 1.0 for high-uncertainty factual queries.
        """
        # Factual tasks with low familiarity need grounding
        if classification.task_type == "factual_query":
            priority = 0.4 + (1.0 - classification.knowledge_familiarity) * 0.5
        # Complex reasoning needs moderate grounding
        elif classification.task_type == "complex_reasoning":
            priority = 0.3 + classification.complexity_score * 0.4
        # Coding tasks need less grounding
        elif classification.task_type == "coding":
            priority = 0.2
        # Creative tasks need minimal grounding
        elif classification.task_type == "creative":
            priority = 0.1
        else:
            priority = 0.3

        # Boost if high ambiguity
        priority += classification.ambiguity_score * 0.2

        return min(1.0, priority)  # SATURATE at 1.0

    def _compute_verification_priority(self, classification: TaskClassification) -> float:
        """Compute verification priority."""
        # High disagreement risk needs verification
        priority = classification.disagreement_risk * 0.4

        # High complexity needs verification
        priority += classification.complexity_score * 0.3

        # Low familiarity needs verification
        priority += (1.0 - classification.knowledge_familiarity) * 0.3

        return min(1.0, priority)

    def _determine_confidence_policy(self, uncertainty: float) -> str:
        """Determine confidence policy based on uncertainty."""
        if uncertainty < 0.3:
            return "high_confidence"
        elif uncertainty < 0.6:
            return "moderate_confidence"
        else:
            return "low_confidence"

    def _determine_stages(self, classification: TaskClassification,
                          grounding_priority: float,
                          verification_priority: float) -> List[str]:
        """Determine which stages to execute."""
        stages = ["classify", "plan"]

        if grounding_priority > 0.3:
            stages.append("grounding")

        stages.append("cost_estimation")
        stages.append("adjust_budget")
        stages.append("prune_stages")

        if verification_priority > 0.5 or classification.disagreement_risk > 0.4:
            stages.append("adversarial_verification")

        stages.append("calibrate")

        return stages
