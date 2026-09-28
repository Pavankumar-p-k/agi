"""VerificationStage — decides whether an execution outcome is verified.

verification_status:
  confirmed    — success outcome AND non-empty planning_artifacts
  unconfirmed  — success outcome but no artifacts to back it
  failure      — the execution itself failed
"""
from __future__ import annotations

from typing import Any

from core.pipeline.base import PipelineStage, PipelineStageResult


class VerificationStage(PipelineStage):
    name = "verification"

    async def execute(self, ctx: Any) -> PipelineStageResult:
        md: dict[str, Any] = getattr(ctx, "metadata", None) or {}

        outcome = str(md.get("planning_outcome", md.get("outcome", ""))).lower()
        execution_status = str(md.get("execution_status", "")).lower()
        artifacts = md.get("planning_artifacts") or md.get("artifacts") or {}

        failed = (
            outcome in ("failure", "failed", "error")
            or execution_status in ("failed", "error")
        )
        if failed:
            return PipelineStageResult(
                outcome="failure",
                metadata={"verification_status": "failure",
                          "reason": "execution reported failure"},
            )

        succeeded = outcome in ("success", "completed", "complete") or \
            execution_status in ("completed", "complete", "success")
        if not succeeded:
            return PipelineStageResult(
                outcome="skipped",
                metadata={"verification_status": "unconfirmed",
                          "reason": f"unknown outcome: {outcome or execution_status or 'none'}"},
            )

        if artifacts:
            status = "confirmed"
            reason = "success with artifacts"
        else:
            status = "unconfirmed"
            reason = "success without artifacts"
        return PipelineStageResult(
            outcome="success" if status == "confirmed" else "skipped",
            metadata={"verification_status": status, "reason": reason},
        )
