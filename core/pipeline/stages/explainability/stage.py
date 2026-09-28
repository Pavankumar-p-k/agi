"""ExplainabilityStage — human-readable explanation of the request flow."""
from __future__ import annotations

import uuid as _uuid

from core.pipeline.base import PipelineStage, StageOutcome, StageResult
from core.pipeline.explanation_result import ExplanationResult
from core.pipeline.pipeline import PipelineContext


class ExplainabilityStage(PipelineStage):
    @property
    def name(self) -> str:
        return "explainability"

    async def execute(self, context: PipelineContext) -> StageResult:
        services = getattr(context, "services", None)
        eid = services.uuid4() if services is not None and hasattr(services, "uuid4") \
            else _uuid.uuid4().hex

        trace: list = []
        findings: list = []

        classification = getattr(context, "classification", None)
        if isinstance(classification, dict):
            mode = classification.get("mode", "unknown")
            trace.append(f"classification={mode}")

        rr = getattr(context, "reasoning_result", None)
        if rr is not None:
            beliefs = tuple(getattr(rr, "beliefs", ()) or ())
            trace.append(f"reasoning=completed ({len(beliefs)} beliefs)")
            findings.extend(f"belief: {b.claim}" for b in beliefs[:3])
        else:
            trace.append("reasoning=skipped")

        pr = getattr(context, "planner_result", None)
        if pr is not None:
            strategies = tuple(getattr(getattr(pr, "ranking", None),
                                       "strategies", ()) or ())
            count = getattr(pr, "total_candidates", 0) or len(strategies)
            trace.append(f"planning={count}_strategies")
        else:
            trace.append("planning=skipped")

        state = str(getattr(context, "execution_state", "pending"))
        trace.append(f"execution={state}")

        reflection = getattr(context, "reflection_result", None)
        if reflection is not None:
            trace.append("reflection=completed")
            lessons = tuple(getattr(reflection, "lessons", ()) or ())
            findings.extend(f"lesson: {l}" for l in lessons[:3])
        else:
            trace.append("reflection=skipped")

        confidence = float(getattr(rr, "confidence", 0.0) or 0.0) if rr else 0.0
        summary = (
            f"Request '{str(getattr(context, 'raw_input', '') or '')[:60]}' was "
            f"processed through {len(trace)} stages; final state: {state}."
        )
        context.explanation = ExplanationResult(
            explanation_id=f"exp_{eid[:24]}",
            request_id=str(getattr(context, "request_id", "") or ""),
            activity_id=str(getattr(context, "activity_id", "") or ""),
            summary=summary,
            confidence=confidence,
            reasoning_trace=tuple(trace),
            key_findings=tuple(findings),
        )
        return StageResult(outcome=StageOutcome.CONTINUE, context=context)


__all__ = ["ExplainabilityStage"]
