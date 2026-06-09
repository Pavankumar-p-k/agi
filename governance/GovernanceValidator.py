# Copyright (c) 2024-2026 JARVIS Project
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

from brain.execution_context import BrainExecutionContext
from governance.exceptions import GovernanceViolation


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
        """Synchronous wrapper for validate_execution_async."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.validate_execution_async(result, context))
        
        # If already in an async loop, we must run it in a thread to avoid nested loop error
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, self.validate_execution_async(result, context)).result(timeout=20)

    async def validate_execution_async(
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
                safe = await self._semantic_check(task)
                if not safe:
                    raise GovernanceViolation("Execution blocked: semantic safety check failed.")
            except GovernanceViolation:
                raise
            except Exception as e:
                import logging
                logging.getLogger("jarvis").warning("Semantic safety check error: %s", e)
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
            from core.llm_router import get_router
            prompt = (
                f"Does this command risk damaging the system?\n"
                f"Command: {command}\n\n"
                f"Unsafe means: deletes system files, formats drives, sends data externally, "
                f"installs malware, bypasses security, modifies system registry, "
                f"disables firewall, kills processes, or alters system configuration.\n"
                f"Reply ONLY: SAFE or UNSAFE"
            )
            r = await get_router().acompletion(
                model="fast",
                messages=[{"role": "user", "content": prompt}],
                timeout=10,
            )
            answer = r.choices[0].message.content.strip().upper()
            return "SAFE" in answer and "UNSAFE" not in answer
        except Exception as e:
            logging.getLogger("jarvis").warning("[governance.GovernanceValidator] semantic check failed: %s", e)
            return True


__all__ = [
    "GovernanceValidator",
]
