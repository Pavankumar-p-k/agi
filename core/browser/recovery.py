"""Bounded recovery ladder for Browser AI.

Failure -> retry/wait -> alternative selector -> DOM re-evaluation ->
refresh/reopen -> alternative workflow -> report failure.

No infinite retry loops: every rung is attempted at most once per recovery
pass, the ladder is bounded by max_attempts, and repeated identical failures
short-circuit (loop detection) instead of retrying forever.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)

ToolCaller = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]

# Ladder rungs, attempted in order; each at most once per pass.
RUNGS = ("retry", "alt_selector", "dom_reevaluate", "refresh", "alternative_workflow")


@dataclass
class RecoveryAttempt:
    rung: str
    action: str
    status: str            # ok | failed | skipped
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"rung": self.rung, "action": self.action, "status": self.status, "detail": self.detail}


@dataclass
class RecoveryOutcome:
    recovered: bool = False
    attempts: list[RecoveryAttempt] = field(default_factory=list)
    exhausted: bool = False     # ladder ran to the end without success
    loop_detected: bool = False
    result: dict[str, Any] | None = None   # successful action result, if recovered
    failure_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "recovered": self.recovered,
            "exhausted": self.exhausted,
            "loop_detected": self.loop_detected,
            "failure_reason": self.failure_reason,
            "attempts": [a.to_dict() for a in self.attempts],
            "result": self.result,
        }


@dataclass
class RecoveryContext:
    action_name: str                     # e.g. "browser_click"
    params: dict[str, Any] = field(default_factory=dict)
    alt_selectors: list[str] = field(default_factory=list)
    alternative_workflows: list[tuple[str, dict[str, Any]]] = field(default_factory=list)  # [(tool, params), ...]


class RecoveryEngine:
    def __init__(self, call: ToolCaller, max_passes: int = 2, wait_seconds: float = 1.5) -> None:
        self._call = call
        self.max_passes = max(1, int(max_passes))
        self.wait_seconds = max(0.0, float(wait_seconds))
        self._failure_history: list[str] = []

    async def _run_action(self, tool: str, params: dict[str, Any]) -> dict[str, Any]:
        try:
            return await self._call(tool, params)
        except Exception as exc:
            return {"status": "error", "error": f"{type(exc).__name__}: {exc}", "error_type": type(exc).__name__}

    def _record_failure(self, signature: str) -> None:
        self._failure_history.append(signature)
        del self._failure_history[:-12]

    def _is_loop(self, signature: str) -> bool:
        recent = self._failure_history[-6:]
        return len(recent) >= 4 and recent[-4:].count(signature) >= 3

    async def recover(self, ctx: RecoveryContext) -> RecoveryOutcome:
        """Attempt bounded recovery for a failed action."""
        outcome = RecoveryOutcome()
        signature = f"{ctx.action_name}:{str(sorted(ctx.params.items()))[:120]}"
        if self._is_loop(signature):
            outcome.loop_detected = True
            outcome.failure_reason = "loop detected: identical failure repeated; recovery stopped"
            logger.warning("[recovery] %s", outcome.failure_reason)
            return outcome

        params = dict(ctx.params)

        for pass_number in range(self.max_passes):
            # Rung 1: simple retry after settle wait
            attempt = await self._try_rung("retry", self._run_action(ctx.action_name, params), outcome)
            if attempt.status == "ok":
                return outcome

            # Rung 2: alternative selectors (click/fill only)
            if ctx.action_name in ("browser_click", "browser_fill", "browser_select") and ctx.alt_selectors:
                for alt in ctx.alt_selectors:
                    alt_params = dict(params)
                    alt_params["selector"] = alt
                    attempt = await self._try_rung("alt_selector", self._run_action(ctx.action_name, alt_params), outcome, action=f"{ctx.action_name}({alt})")
                    if attempt.status == "ok":
                        return outcome

            # Rung 3: DOM re-evaluation — re-perceive, optionally retry with text= selector
            attempt = await self._try_rung("dom_reevaluate", self._run_action("browser_snapshot", {"session_id": params.get("session_id", "default")}), outcome,
                                           counts_as_recovery=False)
            if attempt.status == "ok":
                text_selector = f"text={ctx.params.get('selector', '')}"
                if ctx.action_name in ("browser_click", "browser_fill", "browser_select"):
                    alt_params = dict(params)
                    alt_params["selector"] = text_selector
                    attempt = await self._try_rung("dom_reevaluate", self._run_action(ctx.action_name, alt_params), outcome, action=f"{ctx.action_name}(text=...)")
                    if attempt.status == "ok":
                        return outcome

            # Rung 4: refresh (navigation recovery) / reopen tab
            if ctx.action_name == "browser_navigate":
                attempt = await self._try_rung("refresh", self._run_action("browser_navigate", params), outcome, action="navigate retry")
                if attempt.status == "ok":
                    return outcome
                reopen = await self._try_rung("refresh", self._run_action("browser_new_tab", {"url": ctx.params.get("url", "")}), outcome, action="reopen in new tab")
                if reopen.status == "ok":
                    return outcome
            else:
                attempt = await self._try_rung("refresh", self._run_action("browser_refresh", {"session_id": params.get("session_id", "default")}), outcome,
                                               counts_as_recovery=False)
                if attempt.status == "ok":
                    attempt = await self._try_rung("refresh", self._run_action(ctx.action_name, params), outcome, action=f"{ctx.action_name} after refresh")
                    if attempt.status == "ok":
                        return outcome

            # Rung 5: caller-provided alternative workflows
            for tool, alt_params in ctx.alternative_workflows:
                attempt = await self._try_rung("alternative_workflow", self._run_action(tool, dict(alt_params)), outcome, action=f"{tool}")
                if attempt.status == "ok":
                    return outcome

        outcome.exhausted = True
        outcome.failure_reason = outcome.failure_reason or "recovery ladder exhausted without success"
        self._record_failure(signature)
        return outcome

    async def _try_rung(self, rung: str, coro: Any, outcome: RecoveryOutcome, action: str | None = None,
                        counts_as_recovery: bool = True) -> RecoveryAttempt:
        import asyncio
        result = await coro
        ok = result.get("status") == "ok"
        attempt = RecoveryAttempt(
            rung=rung,
            action=action or rung,
            status="ok" if ok else "failed",
            detail=str(result.get("error") or "")[:200],
        )
        outcome.attempts.append(attempt)
        # Only the RECOVERY ACTION (the retried action / alternative workflow)
        # counts as recovered.  Intermediate perception or preparation steps
        # (DOM snapshot, refresh) succeeding proves nothing about the original
        # failure and must never mark the recovery successful.
        if ok and counts_as_recovery:
            outcome.recovered = True
            outcome.result = result
        return attempt
