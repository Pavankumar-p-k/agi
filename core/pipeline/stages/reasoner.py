from __future__ import annotations

from typing import Any

from core.pipeline.base import PipelineStage, StageOutcome, StageResult
from core.pipeline.context import PipelineContext


class ReasonerStage(PipelineStage):
    @property
    def name(self) -> str:
        return "reasoner"

    async def execute(self, context: PipelineContext) -> StageResult:
        classification = context.classification or {}
        raw_input = context.raw_input or ""
        retrieved = context.retrieved_context or {}

        complexity = self._assess_complexity(classification, raw_input)
        requirements = self._assess_requirements(classification, raw_input, retrieved)
        constraints = self._assess_constraints(classification, raw_input)

        context.reasoning_assessment = {
            "complexity": complexity,
            "requirements": requirements,
            "constraints": constraints,
            "confidence": self._compute_confidence(classification, complexity),
            "estimated_steps": self._estimate_steps(complexity, requirements),
            "routing_hints": {
                "prefer_local": False,
            },
            "metadata": {},
        }
        return StageResult(outcome=StageOutcome.CONTINUE, context=context)

    def _assess_complexity(self, classification: dict[str, Any], raw_input: str) -> str:
        mode = classification.get("mode", "chat")
        sub_type = classification.get("sub_type", "")

        agent_keywords = {"agent", "autonomous", "delegate", "multi-step", "workflow"}
        multi_keywords = {"research", "compare", "analyze", "investigate", "build", "create", "develop"}

        if mode == "agent" or any(k in raw_input.lower() for k in agent_keywords):
            return "agentic"
        if mode in ("action", "codebase") or any(k in raw_input.lower() for k in multi_keywords):
            return "multi_step"
        return "simple"

    def _assess_requirements(self, classification: dict[str, Any], raw_input: str, retrieved: dict[str, Any]) -> list[str]:
        requirements: list[str] = []
        lower = raw_input.lower()

        research_keywords = {"search", "find", "research", "look up", "what is", "who is", "weather", "news"}
        browser_keywords = {"open", "navigate", "browse", "website", "url", "http"}
        coding_keywords = {"code", "program", "function", "class", "implement", "refactor", "debug", "test"}
        memory_keywords = {"remember", "recall", "forget", "my name", "preference"}

        if any(k in lower for k in research_keywords):
            requirements.append("research")
        if any(k in lower for k in browser_keywords):
            requirements.append("browser")
        if any(k in lower for k in coding_keywords):
            requirements.append("coding")
        if any(k in lower for k in memory_keywords):
            requirements.append("memory")

        return requirements

    def _assess_constraints(self, classification: dict[str, Any], raw_input: str) -> list[str]:
        constraints: list[str] = []
        lower = raw_input.lower()

        if any(k in lower for k in {"urgent", "asap", "quick", "fast", "immediately"}):
            constraints.append("speed")
        if any(k in lower for k in {"accurate", "precise", "exact", "fact-check"}):
            constraints.append("accuracy")
        if any(k in lower for k in {"real-time", "live", "streaming", "current"}):
            constraints.append("freshness")

        return constraints

    def _compute_confidence(self, classification: dict[str, Any], complexity: str) -> float:
        confidence = classification.get("confidence", 0.5)
        if complexity == "simple":
            return min(confidence + 0.3, 1.0)
        if complexity == "multi_step":
            return confidence
        return max(confidence - 0.2, 0.1)

    def _estimate_steps(self, complexity: str, requirements: list[str]) -> int:
        if complexity == "simple":
            return 1
        if complexity == "multi_step":
            return max(len(requirements) + 1, 2)
        return max(len(requirements) + 2, 3)
