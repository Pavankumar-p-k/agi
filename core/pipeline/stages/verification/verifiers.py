"""Built-in verifiers: safety, schema, confidence (Sprint 3)."""
from __future__ import annotations

import re
from typing import Any

from core.pipeline.stages.verification.base import Verdict, Verifier


_BLOCKED_PATTERNS = (
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"disregard\s+(all\s+)?(prior|previous)\s+instructions", re.IGNORECASE),
    re.compile(r"reveal\s+(your\s+)?(system\s+)?prompt", re.IGNORECASE),
)


class SafetyVerifier(Verifier):
    """Blocks prompt-injection / instruction-override output."""

    @property
    def name(self) -> str:
        return "safety"

    async def verify(self, ctx: Any) -> Verdict:
        result = getattr(ctx, "execution_result", None)
        if result is None:
            return Verdict(verifier_name=self.name, outcome="PASS")
        text = ""
        if isinstance(result, dict):
            text = str(result.get("text", ""))
        elif isinstance(result, str):
            text = result
        for pattern in _BLOCKED_PATTERNS:
            if pattern.search(text):
                return Verdict(verifier_name=self.name, outcome="FAIL",
                               message=f"blocked pattern matched: {pattern.pattern!r}")
        return Verdict(verifier_name=self.name, outcome="PASS")


class SchemaVerifier(Verifier):
    """Execution output must be a dict containing a text field."""

    @property
    def name(self) -> str:
        return "schema"

    async def verify(self, ctx: Any) -> Verdict:
        result = getattr(ctx, "execution_result", None)
        if result is None:
            return Verdict(verifier_name=self.name, outcome="PASS")
        if not isinstance(result, dict):
            return Verdict(verifier_name=self.name, outcome="FAIL",
                           message=f"execution_result is {type(result).__name__}, "
                                   f"expected dict")
        if "text" not in result:
            return Verdict(verifier_name=self.name, outcome="WARNING",
                           message="execution_result missing 'text' field")
        return Verdict(verifier_name=self.name, outcome="PASS")


class ConfidenceVerifier(Verifier):
    """Warns when the epistemic confidence is low."""

    @property
    def name(self) -> str:
        return "confidence"

    async def verify(self, ctx: Any) -> Verdict:
        tags = getattr(ctx, "epistemic_tags", None) or {}
        confidence = tags.get("confidence") if isinstance(tags, dict) else None
        if confidence is None:
            return Verdict(verifier_name=self.name, outcome="PASS")
        if float(confidence) < 0.3:
            return Verdict(verifier_name=self.name, outcome="WARNING",
                           message=f"low confidence: {confidence}")
        return Verdict(verifier_name=self.name, outcome="PASS")


__all__ = ["SafetyVerifier", "SchemaVerifier", "ConfidenceVerifier"]
