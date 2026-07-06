from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from core.pipeline.base import PipelineStage, StageOutcome, StageResult
from core.pipeline.context import PipelineContext

logger = logging.getLogger(__name__)


# ── Verdict ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Verdict:
    """Outcome of a single verifier check.

    ``blocking`` controls whether this verdict stops the pipeline:
    a FAIL verdict with ``blocking=True`` halts execution; a FAIL verdict
    with ``blocking=False`` is advisory only.
    """

    verifier_name: str
    outcome: str  # "PASS" | "WARNING" | "FAIL"
    message: str = ""
    blocking: bool = True
    confidence: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)


# ── Verifier ABC ─────────────────────────────────────────────────────────────


class Verifier(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    async def verify(self, context: PipelineContext) -> Verdict:
        ...


# ── Built-in verifiers ──────────────────────────────────────────────────────


class SafetyVerifier(Verifier):
    @property
    def name(self) -> str:
        return "safety"

    async def verify(self, context: PipelineContext) -> Verdict:
        text = context.outcome.text if context.outcome else ""
        if not text:
            result = context.execution_result
            text = (result or {}).get("text", "") or ""
        if not text:
            return Verdict(verifier_name="safety", outcome="PASS", message="No output to check")
        lower = text.lower()

        blocked_patterns = [
            "ignore previous instructions",
            "ignore all instructions",
            "system prompt:",
            "you are an ai",
        ]
        for pattern in blocked_patterns:
            if pattern in lower:
                return Verdict(
                    verifier_name="safety",
                    outcome="FAIL",
                    message=f"Output contains blocked pattern: {pattern}",
                )
        return Verdict(verifier_name="safety", outcome="PASS", message="Safety check passed")


class SchemaVerifier(Verifier):
    @property
    def name(self) -> str:
        return "schema"

    async def verify(self, context: PipelineContext) -> Verdict:
        if context.outcome is not None:
            if not context.outcome.success:
                return Verdict(verifier_name="schema", outcome="FAIL", message="Execution outcome indicates failure")
            if "text" not in context.outcome.outputs:
                return Verdict(verifier_name="schema", outcome="WARNING", message="Outcome has no 'text' in outputs")
            return Verdict(verifier_name="schema", outcome="PASS", message="Schema check passed")
        result = context.execution_result
        if result is None:
            return Verdict(verifier_name="schema", outcome="PASS", message="No result to check")
        if not isinstance(result, dict):
            return Verdict(verifier_name="schema", outcome="FAIL", message="execution_result is not a dict")
        if "text" not in result:
            return Verdict(verifier_name="schema", outcome="WARNING", message="execution_result has no 'text' field")
        return Verdict(verifier_name="schema", outcome="PASS", message="Schema check passed")


class ConfidenceVerifier(Verifier):
    @property
    def name(self) -> str:
        return "confidence"

    async def verify(self, context: PipelineContext) -> Verdict:
        tags = context.epistemic_tags or {}
        threshold = 0.3
        confidence = tags.get("confidence", 1.0)
        if confidence < threshold:
            return Verdict(
                verifier_name="confidence",
                outcome="WARNING",
                message=f"Confidence {confidence} below threshold {threshold}",
            )
        return Verdict(verifier_name="confidence", outcome="PASS", message="Confidence check passed")


# ── Default verifiers ────────────────────────────────────────────────────────

DEFAULT_VERIFIERS: list[Verifier] = [
    SafetyVerifier(),
    SchemaVerifier(),
    ConfidenceVerifier(),
]


# ── VerificationStage ────────────────────────────────────────────────────────


class VerificationStage(PipelineStage):
    def __init__(self) -> None:
        self._verifiers: list[Verifier] = list(DEFAULT_VERIFIERS)

    @property
    def name(self) -> str:
        return "verification"

    def add_verifier(self, verifier: Verifier) -> VerificationStage:
        self._verifiers.append(verifier)
        return self

    def clear_verifiers(self) -> VerificationStage:
        self._verifiers = []
        return self

    async def execute(self, context: PipelineContext) -> StageResult:
        verdicts: list[dict[str, Any]] = []
        for verifier in self._verifiers:
            try:
                verdict = await verifier.verify(context)
                verdicts.append({
                    "verifier": verdict.verifier_name,
                    "outcome": verdict.outcome,
                    "message": verdict.message,
                    "blocking": verdict.blocking,
                    "confidence": verdict.confidence,
                    "metadata": dict(verdict.metadata),
                })
            except Exception as exc:
                logger.warning("Verifier %s failed: %s", verifier.name, exc)
                verdicts.append({
                    "verifier": verifier.name,
                    "outcome": "FAIL",
                    "message": f"Verifier raised: {exc}",
                    "blocking": True,
                    "confidence": 0.0,
                    "metadata": {},
                })

        has_blocking_fail = any(
            v["outcome"] == "FAIL" and v.get("blocking", True) for v in verdicts
        )

        context.verification_result = {
            "verdicts": verdicts,
            "passed": not has_blocking_fail,
        }

        if has_blocking_fail:
            return StageResult(
                outcome=StageOutcome.FAIL,
                context=context,
                error="Verification failed:\n" + "\n".join(
                    f"  [{v['outcome']}] {v['verifier']}: {v['message']}"
                    for v in verdicts if v["outcome"] == "FAIL"
                ),
            )

        return StageResult(outcome=StageOutcome.CONTINUE, context=context)
