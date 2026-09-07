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
import logging
from typing import Any, Dict, Optional

from brain.execution_context import BrainExecutionContext
from governance.exceptions import GovernanceViolation

logger = logging.getLogger("jarvis.governance")


class GovernanceValidator:
    """
    Canonical governance gate for execution requests.
    Raises `GovernanceViolation` on any policy breach.
    Uses keyword blocklist + semantic LLM classification.

    Policy: FAIL-CLOSED. Any unclassifiable or errored request is denied.
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

    _BLOCKED_APPS = (
        "cmd", "cmd.exe", "command prompt",
        "powershell", "powershell.exe", "pwsh", "pwsh.exe",
        "regedit", "regedit.exe", "registry editor",
        "taskmgr", "taskmgr.exe", "task manager",
    )

    _BLOCKED_PATTERNS = (
        "taskkill", "taskkill.exe", "stop-process", "kill -9",
        "del /q", "del /f /q", "rd /s /q", "remove-item -force",
        "remove-item -recurse", "rmdir /s /q", "rm -f",
        "rm -r", "rm --no-preserve-root",
        "reg delete", "reg add", "reg import", "reg export",
        "reg save", "reg restore", "reg load",
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

        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, self.validate_execution_async(result, context)).result(timeout=20)

    async def validate_execution_async(
        self,
        result: Dict[str, Any],
        context: Optional[BrainExecutionContext] = None,
    ) -> bool:
        task = str(result.get("task", "")).lower()

        # 1. Keyword blocklist — prompt injection
        if any(token in task for token in self._INJECTION_TOKENS):
            raise GovernanceViolation(
                policy="input.blocklist",
                reason="Prompt injection or policy bypass intent detected",
                severity="critical",
            )

        # 2. Destructive command patterns
        if any(pattern in task for pattern in self._DESTRUCTIVE_PATTERNS):
            raise GovernanceViolation(
                policy="input.destructive",
                reason="Destructive command pattern detected",
                severity="critical",
            )

        # 3. Blocked applications (cmd, powershell, regedit, task manager)
        task_words = task.split()
        for word in task_words:
            clean = word.strip("\"'.,;:!?")
            if clean in self._BLOCKED_APPS:
                raise GovernanceViolation(
                    policy="input.blocked_app",
                    reason=f"Blocked application '{clean}' requires explicit permission",
                    severity="critical",
                )

        # 4. Blocked dangerous patterns (file delete/write, process control, registry)
        if any(pattern in task for pattern in self._BLOCKED_PATTERNS):
            raise GovernanceViolation(
                policy="input.dangerous_action",
                reason="Dangerous OS action detected (process control, file deletion, or registry modification)",
                severity="critical",
            )

        # 5. Semantic check via LLM — FAIL-CLOSED on error
        if self._semantic_check_enabled:
            try:
                safe = await self._semantic_check(task)
                if not safe:
                    raise GovernanceViolation(
                        policy="input.semantic",
                        reason="Semantic safety check classified request as unsafe",
                        severity="critical",
                    )
            except GovernanceViolation:
                raise
            except Exception as e:
                logger.warning("Semantic safety check error, failing closed: %s", e)
                raise GovernanceViolation(
                    policy="input.semantic",
                    reason=f"Semantic check unavailable ({e.__class__.__name__}), failing closed",
                    severity="critical",
                )

        # 6. Trust risk threshold
        if result.get("success") is False and float(result.get("trust_risk", 0.0)) > 0.5:
            raise GovernanceViolation(
                policy="input.trust",
                reason="Trust risk exceeded allowed threshold",
                severity="warning",
            )

        self.last_decision = {
            "allowed": True,
            "task": result.get("task", ""),
            "context": context.to_dict() if context else {},
        }
        return True

    async def _semantic_check(self, command: str) -> bool:
        """Classify command as SAFE or UNSAFE using tinyllama.
        FAIL-CLOSED: returns False (unsafe) on any error."""
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
            logger.warning("[GovernanceValidator] semantic check failed, failing closed: %s", e)
            return False


__all__ = [
    "GovernanceValidator",
]
