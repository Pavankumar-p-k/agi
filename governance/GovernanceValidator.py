from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

from brain.execution_context import BrainExecutionContext
from jarvis_os.runtime.exceptions import GovernanceViolation
from .strict_verification import StrictVerificationEngine, VerificationReport, VerificationVerdict


class GovernanceValidator:
    """
    Canonical governance gate for execution requests.
    Raises `GovernanceViolation` on any policy breach.
    Uses keyword blocklist + semantic LLM classification.
    """

    _INJECTION_TOKENS = (
        "ignore previous instructions",
        "bypass governance",
        "disable safety",
        "emulate this",
        "jailbreak",
    )

    _DESTRUCTIVE_PATTERNS = (
        "rm -rf", "format ", "diskpart", "cipher", "shutdown", "reboot",
        "del /s", "del /f", "rd /s", "remove-item", "stop-computer",
        "restart-computer", "clear-content", "| sh", "| bash",
    )

    def __init__(self) -> None:
        self.last_decision: Optional[Dict[str, Any]] = None
        self._semantic_check_enabled = True

    def validate_execution(
        self,
        result: Dict[str, Any],
        context: Optional[BrainExecutionContext] = None,
    ) -> bool:
        task = str(result.get("task", "")).lower()

        # 1. Keyword blocklist
        if any(token in task for token in self._INJECTION_TOKENS):
            raise GovernanceViolation("Execution blocked: prompt injection or policy bypass intent detected.")
        if any(pattern in task for pattern in self._DESTRUCTIVE_PATTERNS):
            raise GovernanceViolation("Execution blocked: destructive command pattern detected.")

        # 2. Semantic check via TinyLlama
        if self._semantic_check_enabled:
            try:
                loop = asyncio.new_event_loop()
                safe = loop.run_until_complete(self._semantic_check(task))
                loop.close()
                if not safe:
                    raise GovernanceViolation("Execution blocked: semantic safety check failed.")
            except GovernanceViolation:
                raise
            except Exception:
                pass

        if result.get("success") is False and float(result.get("trust_risk", 0.0)) > 0.5:
            raise GovernanceViolation("Execution blocked: trust risk exceeded allowed threshold.")

        self.last_decision = {
            "allowed": True,
            "task": result.get("task", ""),
            "context": context.to_dict() if context else {},
        }
        return True

    async def _semantic_check(self, command: str) -> bool:
        """Classify command as SAFE or UNSAFE using tinyllama."""
        try:
            from core.llm_router import router as llm_router
            prompt = (
                f"Does this command risk damaging the system?\n"
                f"Command: {command}\n\n"
                f"Unsafe means: deletes system files, formats drives, sends data externally, "
                f"installs malware, bypasses security, modifies system registry, "
                f"disables firewall, kills processes, or alters system configuration.\n"
                f"Reply ONLY: SAFE or UNSAFE"
            )
            r = await llm_router.acompletion(
                model="fast",
                messages=[{"role": "user", "content": prompt}],
                timeout=10,
            )
            answer = r.choices[0].message.content.strip().upper()
            return "SAFE" in answer and "UNSAFE" not in answer
        except Exception:
            return True


__all__ = [
    "GovernanceValidator",
    "StrictVerificationEngine",
    "VerificationReport",
    "VerificationVerdict",
]
