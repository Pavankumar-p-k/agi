from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from brain.reasoning_engine import reasoning_engine

logger = logging.getLogger(__name__)


@dataclass
class VerificationResult:
    """Result of verifying an action or output."""
    verified: bool
    confidence: float = 0.0
    issues: list[str] = field(default_factory=list)
    evidence: str = ""


VERIFIER_SYSTEM = (
    "You are a verification engine. Your job is to check if an action was successful.\n"
    "Output inside <answer> tags in this exact JSON format:\n"
    "{\"verified\": true/false, \"confidence\": 0.0-1.0, \"issues\": [...], \"evidence\": \"...\"}\n"
    "Be strict: if there is any indication of failure, mark as not verified.\n"
    "Think step by step inside <think> tags."
)


class Verifier:
    """Verification layer — never trust the LLM's output without checking.

    Every action goes through:
        Plan -> Execute -> Verify -> Store

    The verifier checks:
    1. Was the output what we expected?
    2. Is there any evidence of error?
    3. Does the result make logical sense given the context?
    """

    def __init__(self):
        self._engine = reasoning_engine

    async def verify_action(self, action_description: str,
                            intended_outcome: str,
                            actual_result: str) -> VerificationResult:
        """Verify that an action produced the intended outcome."""
        prompt = (
            f"Action: {action_description}\n"
            f"Intended outcome: {intended_outcome}\n"
            f"Actual result: {actual_result}\n\n"
            "Was the action successful? Check carefully for errors."
        )

        result = await self._engine.reason(
            f"Verify: {action_description}",
            prompt,
            system_override=VERIFIER_SYSTEM,
        )

        return self._parse_verification(result.answer)

    async def verify_file_creation(self, file_path: str,
                                   expected_content_snippet: str = "") -> VerificationResult:
        """Verify that a file was created with the expected content."""
        import os
        if not os.path.exists(file_path):
            return VerificationResult(
                verified=False,
                confidence=0.0,
                issues=["File does not exist"],
            )
        if expected_content_snippet:
            try:
                with open(file_path, encoding="utf-8", errors="replace") as f:
                    content = f.read()
                if expected_content_snippet not in content:
                    return VerificationResult(
                        verified=False,
                        confidence=0.3,
                        issues=[f"Expected content not found in {file_path}"],
                        evidence=f"File exists ({len(content)} bytes) but expected snippet missing",
                    )
            except Exception as e:
                return VerificationResult(
                    verified=False,
                    confidence=0.5,
                    issues=[f"Could not read file: {e}"],
                )
        return VerificationResult(
            verified=True,
            confidence=1.0,
            evidence=f"File exists at {file_path}",
        )

    async def verify_code_output(self, code_snippet: str,
                                  output: str,
                                  expected_behavior: str) -> VerificationResult:
        """Verify that code produces the expected output."""
        prompt = (
            f"Code:\n```\n{code_snippet}\n```\n"
            f"Output:\n{output}\n"
            f"Expected behavior: {expected_behavior}\n\n"
            "Does the output match the expected behavior?"
        )

        result = await self._engine.reason(
            "Verify code output",
            prompt,
            system_override=VERIFIER_SYSTEM,
        )

        return self._parse_verification(result.answer)

    def _parse_verification(self, raw: str) -> VerificationResult:
        """Parse the LLM's verification response."""
        import json
        import re

        answer_match = re.search(r"<answer>(.*?)</answer>", raw, re.DOTALL)
        json_str = answer_match.group(1).strip() if answer_match else raw.strip()
        json_str = re.sub(r"```(?:json)?\s*", "", json_str).strip()

        try:
            data = json.loads(json_str)
            return VerificationResult(
                verified=bool(data.get("verified", False)),
                confidence=float(data.get("confidence", 0.0)),
                issues=data.get("issues", []),
                evidence=data.get("evidence", ""),
            )
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning("[Verifier] failed to parse response: %s", e)
            # Fallback: check for keywords
            verified = "success" in raw.lower() or "verified" in raw.lower()
            return VerificationResult(
                verified=verified,
                confidence=0.5 if verified else 0.3,
                issues=["Could not parse verification response"],
                evidence=raw[:200],
            )


verifier = Verifier()
