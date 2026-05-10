"""Reasoning engine for the JARVIS AI Operating System."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Dict, List, Optional

from .contracts import Goal

logger = logging.getLogger("jarvis.os.reasoning")


class ReasoningEngine:
    def __init__(self, world_model: Any, tool_router: Any, observability: Any, config: Optional[dict] = None):
        self.world_model = world_model
        self.tool_router = tool_router
        self.observability = observability
        self.config = config or {}

    async def analyze(self, prompt: str, context: Optional[Dict[str, Any]] = None, session_id: str = "") -> Dict[str, Any]:
        ctx = context or {}
        legacy = await self._analyze_with_legacy_orchestrator(prompt, ctx, session_id)
        intent = legacy.get("intent") or self._heuristic_intent(prompt)
        tool_candidates = self.tool_router.recommend_tools(prompt)
        memory_hits = await self.world_model.query(prompt, top_k=self.config.get("memory_top_k", 5))
        complexity = max(1, len(self._split_actions(prompt)))
        goal = Goal(
            prompt=prompt,
            context=ctx,
            intent=intent,
            priority=int(ctx.get("priority", 5)),
            constraints=ctx.get("constraints", {}),
            session_id=session_id or ctx.get("session_id", ""),
        )
        analysis = {
            "goal": goal,
            "intent": intent,
            "emotion": legacy.get("emotion", "neutral"),
            "route": legacy.get("route", "os"),
            "confidence": float(legacy.get("confidence", 0.45)),
            "model": legacy.get("model", "hybrid"),
            "memory_hits": memory_hits,
            "tool_candidates": [candidate.to_dict() for candidate in tool_candidates],
            "complexity": complexity,
            "subtasks": self._split_actions(prompt),
            "legacy": legacy,
        }
        self.observability.record_event(
            "reasoning.analysis",
            {
                "goal_id": goal.goal_id,
                "intent": intent,
                "complexity": complexity,
                "memory_hits": len(memory_hits),
                "candidate_tools": [candidate.tool for candidate in tool_candidates],
            },
        )
        return analysis

    async def reflect(self, goal: Goal, plan: Any, execution_report: Any) -> Dict[str, Any]:
        failures = [step for step in execution_report.step_results if not step.success]
        reflection = {
            "goal_id": goal.goal_id,
            "plan_id": plan.plan_id,
            "success": execution_report.success,
            "failure_count": len(failures),
            "lessons": self._lessons_from_failures(failures),
            "next_focus": "deepen_tooling" if failures else "reuse_successful_strategy",
        }
        self.observability.record_event("reasoning.reflection", reflection)
        return reflection

    async def _analyze_with_legacy_orchestrator(
        self,
        prompt: str,
        context: Dict[str, Any],
        session_id: str,
    ) -> Dict[str, Any]:
        try:
            from autonomy import get_orchestrator

            orchestrator = get_orchestrator()
            if not orchestrator:
                return {}
            result = await asyncio.wait_for(
                orchestrator.process(
                    prompt,
                    platform=context.get("platform", "os"),
                    session=session_id or context.get("session_id", ""),
                ),
                timeout=float(self.config.get("legacy_timeout_s", 3.0)),
            )
            return {
                "intent": result.intent,
                "emotion": result.emotion,
                "route": result.route,
                "confidence": result.confidence,
                "model": result.model_used,
                "reply": result.reply,
                "plan": result.plan,
            }
        except Exception as exc:
            logger.debug("Legacy orchestrator analysis unavailable: %s", exc)
            return {}

    def _heuristic_intent(self, prompt: str) -> str:
        lowered = prompt.lower()
        rules = {
            "browser": ["in chrome", "amazon", "flipkart", "website", "cart", "checkout", "search for", "open instagram", "open whatsapp", "open amazon"],
            "automation": ["open ", "launch ", "browser", "send ", "message", "click", "type ", "login", "log in", "sign in", "search ", "in chrome"],
            "vision": ["camera", "screen", "image", "face", "see ", "visual"],
            "filesystem": ["file", "folder", "directory", "read ", "list ", "save ", "write "],
            "adb": ["android", "adb", "device", "phone", "battery", "screenshot"],
            "learning": ["learn", "study", "teach", "practice", "improve", "why did"],
            "realtime": ["today", "current date", "current time", "news", "latest", "who is", "what is"],
            "workspace": ["project", "repo", "repository", "codebase", "review", "architecture", "module", "develop", "build", "implement", "fix", "debug", "refactor", "understand"],
            "scheduler": ["schedule", "cron", "heartbeat", "daily", "every day", "background task", "remind me"],
            "mobile": ["mobile", "phone sync", "android sync", "pair device", "sync my phone"],
            "access": ["permission", "approval", "grant access", "allow access", "security profile"],
            "gateway": ["telegram", "whatsapp", "discord", "slack", "message channel", "notify me"],
        }
        for intent, patterns in rules.items():
            if any(pattern in lowered for pattern in patterns):
                return intent
        return "general_chat"

    def _split_actions(self, prompt: str) -> List[str]:
        parts = [part.strip() for part in re.split(r"\b(?:and then|then|after that|and)\b", prompt, flags=re.IGNORECASE)]
        return [part for part in parts if part]

    def _lessons_from_failures(self, failures: List[Any]) -> List[str]:
        if not failures:
            return ["Current plan completed successfully; cache the route and prefer it next time."]
        lessons = []
        for failure in failures[:3]:
            if failure.tool:
                lessons.append(f"{failure.tool} needs stronger guardrails or better argument normalization.")
            if failure.error:
                lessons.append(f"Retry policy should classify '{failure.error[:80]}' earlier.")
        return lessons or ["Execution failed without a classified cause; capture richer telemetry."]
