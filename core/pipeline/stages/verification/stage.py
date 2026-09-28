"""VerificationStage — runs the verifier chain over the execution result.

Outcome:
  any FAIL        -> StageOutcome.FAIL, verification_result.passed = False
  otherwise       -> StageOutcome.CONTINUE, verification_result.passed = True
verification_result = {"passed": bool, "verdicts": [{"verifier","outcome",
"message"}...]}
"""
from __future__ import annotations

from typing import Any, List

from core.pipeline.base import PipelineStage, StageOutcome, StageResult
from core.pipeline.pipeline import PipelineContext
from core.pipeline.stages.verification.base import Verdict, Verifier
from core.pipeline.stages.verification.verifiers import (
    ConfidenceVerifier,
    SafetyVerifier,
    SchemaVerifier,
)


class VerificationStage(PipelineStage):
    def __init__(self, **kwargs: Any) -> None:
        self._verifiers: List[Verifier] = [
            SafetyVerifier(), SchemaVerifier(), ConfidenceVerifier(),
        ]

    @property
    def name(self) -> str:
        return "verification"

    # ── verifier chain management ────────────────────────────────────
    def add_verifier(self, verifier: Verifier) -> None:
        self._verifiers.append(verifier)

    def clear_verifiers(self) -> None:
        self._verifiers = []

    @property
    def verifiers(self) -> List[Verifier]:
        return list(self._verifiers)

    # ── execution ────────────────────────────────────────────────────
    async def execute(self, context: PipelineContext) -> StageResult:
        verdicts: List[Verdict] = []
        for verifier in self._verifiers:
            try:
                verdicts.append(await verifier.verify(context))
            except Exception as exc:  # noqa: BLE001 — verifier bugs must not crash
                verdicts.append(Verdict(verifier_name=getattr(verifier, "name",
                                                          type(verifier).__name__),
                                        outcome="WARNING",
                                        message=f"verifier raised: {exc}"))

        failed = any(v.outcome == "FAIL" for v in verdicts)
        context.verification_result = {
            "passed": not failed,
            "verdicts": [
                {"verifier": v.verifier_name, "outcome": v.outcome,
                 "message": v.message}
                for v in verdicts
            ],
        }

        result = StageResult(
            outcome=StageOutcome.FAIL if failed else StageOutcome.CONTINUE,
            context=context,
        )

        # Planning-artifact flavor (integration contract): when the context
        # carries planning metadata, derive a verification_status from the
        # execution outcome and expose it on result.metadata.
        md = getattr(context, "metadata", None) or {}
        if md:
            outcome = str(md.get("planning_outcome", md.get("outcome", ""))).lower()
            execution_status = str(md.get("execution_status", "")).lower()
            artifacts = md.get("planning_artifacts") or md.get("artifacts") or {}

            if outcome in ("failure", "failed", "error") or \
                    execution_status in ("failed", "error"):
                status, reason = "failure", "execution reported failure"
            elif outcome in ("success", "completed", "complete") or \
                    execution_status in ("completed", "complete", "success"):
                if artifacts:
                    status, reason = "confirmed", "success with artifacts"
                else:
                    status, reason = "unconfirmed", "success without artifacts"
            else:
                status, reason = "unconfirmed", \
                    f"unknown outcome: {outcome or execution_status or 'none'}"
            result.metadata = {"verification_status": status, "reason": reason}

        return result


__all__ = ["VerificationStage", "Verdict", "Verifier",
           "SafetyVerifier", "SchemaVerifier", "ConfidenceVerifier"]
