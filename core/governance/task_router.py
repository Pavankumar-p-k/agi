"""core/governance/task_router.py
TaskRouter — routes any incoming task string to the best handler.

Priority order:
  1. Skill keyword match  → "skill"
  2. Web / research task  → sub_agent "researcher"
  3. Code / execution     → sub_agent "coder"
  4. Multi-step planning  → sub_agent "planner"
  5. Conversational/Q&A   → "llm_direct"

Route confidence < 0.5 triggers a clarification request upstream.
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Literal

logger = logging.getLogger(__name__)

# ── keyword tables ────────────────────────────────────────────────────────────

_RESEARCH_KEYWORDS: set[str] = {
    "search", "find", "look up", "lookup", "research", "browse", "google",
    "news", "latest", "current", "today", "what is", "who is", "define",
    "wikipedia", "online", "internet", "web", "fetch", "scrape",
}

_CODER_KEYWORDS: set[str] = {
    "code", "write code", "program", "script", "function", "class", "module",
    "debug", "fix bug", "refactor", "implement", "develop", "build app",
    "run", "execute", "compile", "test", "unit test", "python", "javascript",
    "java", "typescript", "rust", "golang", "sql", "bash", "shell command",
    "install package", "pip install", "npm install",
}

_PLANNER_KEYWORDS: set[str] = {
    "plan", "steps", "organize", "break down", "schedule", "roadmap",
    "strategy", "workflow", "project", "multiple", "sequence", "phases",
    "step by step", "first then", "create a plan", "how do i",
}

_CONVERSATIONAL_KEYWORDS: set[str] = {
    "hello", "hi", "hey", "thanks", "thank you", "what do you think",
    "tell me", "explain", "describe", "summarize", "help me understand",
    "can you", "could you", "opinion", "recommend", "suggest",
}

# Estimated durations in seconds per handler type
_DURATION_ESTIMATES: dict[str, float] = {
    "skill": 2.0,
    "researcher": 8.0,
    "coder": 15.0,
    "planner": 5.0,
    "llm_direct": 3.0,
}


# ── data classes ──────────────────────────────────────────────────────────────

@dataclass
class RouteDecision:
    handler: Literal["sub_agent", "skill", "tool", "llm_direct"]
    target: str          # agent role / skill id / tool name
    confidence: float
    reasoning: str
    estimated_duration_s: float

    def needs_clarification(self) -> bool:
        return self.confidence < 0.5

    def to_dict(self) -> dict:
        return {
            "handler": self.handler,
            "target": self.target,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "estimated_duration_s": self.estimated_duration_s,
        }


# ── helpers ───────────────────────────────────────────────────────────────────

def _normalize(text: str) -> str:
    return re.sub(r"[^\w\s]", " ", text.lower()).strip()


def _keyword_score(text_lower: str, keywords: set[str]) -> float:
    """Return a 0-1 score based on how many keywords appear in the text."""
    hits = sum(1 for kw in keywords if kw in text_lower)
    if hits == 0:
        return 0.0
    return min(1.0, 0.4 + hits * 0.2)


def _skill_match(task_lower: str, skill_keywords: dict[str, list[str]]) -> tuple[str | None, float]:
    """
    Returns (skill_id, confidence) or (None, 0.0) if no skill matches.
    skill_keywords: {skill_id: [keyword, ...]}
    """
    best_skill = None
    best_score = 0.0
    for skill_id, keywords in skill_keywords.items():
        score = _keyword_score(task_lower, set(keywords))
        if score > best_score:
            best_score = score
            best_skill = skill_id
    return (best_skill, best_score) if best_score >= 0.4 else (None, 0.0)


# ── main class ────────────────────────────────────────────────────────────────

class TaskRouter:
    """Routes a task string to the best handler.

    Usage::
        router = TaskRouter()
        decision = await router.route("search for latest AI news", {})
        if decision.needs_clarification():
            # ask user
            ...
    """

    def __init__(self, tool_registry=None):
        """
        Parameters
        ----------
        tool_registry : ai_os.tool_registry.ToolRegistry | None
            Optional ToolRegistry; if provided, skill/tool names are used
            to build the skill keyword map.
        """
        self._skill_keywords: dict[str, list[str]] = {}
        if tool_registry is not None:
            self._load_skill_keywords(tool_registry)

    # ── public API ────────────────────────────────────────────────────────────

    async def route(self, task: str, context: dict | None = None) -> RouteDecision:
        """Async route — may call LLM for ambiguous (0.35 < conf < 0.55) cases."""
        context = context or {}
        decision = self._rule_based_route(task, context)

        # Try LLM disambiguation for ambiguous cases
        if 0.35 < decision.confidence < 0.55:
            llm_decision = await self._llm_route(task, context)
            if llm_decision is not None and llm_decision.confidence > decision.confidence:
                decision = llm_decision

        logger.info(
            "[TaskRouter] '%s…' → %s/%s (conf=%.2f)",
            task[:60], decision.handler, decision.target, decision.confidence,
        )
        return decision

    # ── internal ──────────────────────────────────────────────────────────────

    def _rule_based_route(self, task: str, context: dict) -> RouteDecision:
        task_lower = _normalize(task)

        # ── 1. Skill match (highest priority) ─────────────────────────────────
        if self._skill_keywords:
            skill_id, skill_conf = _skill_match(task_lower, self._skill_keywords)
            if skill_id:
                return RouteDecision(
                    handler="skill",
                    target=skill_id,
                    confidence=skill_conf,
                    reasoning=f"Task matches skill '{skill_id}' keywords.",
                    estimated_duration_s=_DURATION_ESTIMATES["skill"],
                )

        # ── 2. Research / web search ──────────────────────────────────────────
        research_score = _keyword_score(task_lower, _RESEARCH_KEYWORDS)
        coder_score    = _keyword_score(task_lower, _CODER_KEYWORDS)
        planner_score  = _keyword_score(task_lower, _PLANNER_KEYWORDS)
        convo_score    = _keyword_score(task_lower, _CONVERSATIONAL_KEYWORDS)

        scores = {
            "researcher": research_score,
            "coder":      coder_score,
            "planner":    planner_score,
            "llm_direct": convo_score,
        }

        best_agent = max(scores, key=lambda k: scores[k])
        best_score = scores[best_agent]

        if best_score == 0.0:
            # No keywords matched at all — weakly route to llm_direct
            return RouteDecision(
                handler="llm_direct",
                target="llm_direct",
                confidence=0.35,
                reasoning="No strong keyword match; defaulting to direct LLM.",
                estimated_duration_s=_DURATION_ESTIMATES["llm_direct"],
            )

        if best_agent == "llm_direct":
            return RouteDecision(
                handler="llm_direct",
                target="llm_direct",
                confidence=best_score,
                reasoning="Task appears conversational/explanatory.",
                estimated_duration_s=_DURATION_ESTIMATES["llm_direct"],
            )

        return RouteDecision(
            handler="sub_agent",
            target=best_agent,
            confidence=best_score,
            reasoning=(
                f"Keyword analysis: researcher={research_score:.2f}, "
                f"coder={coder_score:.2f}, planner={planner_score:.2f}. "
                f"Best match → '{best_agent}'."
            ),
            estimated_duration_s=_DURATION_ESTIMATES.get(best_agent, 5.0),
        )

    async def _llm_route(self, task: str, context: dict) -> RouteDecision | None:
        """
        Call LLM to disambiguate; returns None if LLM is unavailable.
        Keeps the import lazy so the router works even without Ollama.
        """
        try:
            from core.llm_router import complete  # type: ignore

            system = (
                "You are a task router. Given a task, output EXACTLY one JSON object:\n"
                '{"handler": "<sub_agent|skill|tool|llm_direct>", '
                '"target": "<researcher|coder|planner|llm_direct>", '
                '"confidence": <0.0-1.0>, "reasoning": "<one sentence>"}\n'
                "No other text."
            )
            result = await complete("chat", [
                {"role": "system", "content": system},
                {"role": "user", "content": f"Task: {task}"},
            ])
            raw = result.unwrap_or("") if hasattr(result, "unwrap_or") else str(result)

            import json
            data = json.loads(raw.strip())
            handler  = data.get("handler", "llm_direct")
            target   = data.get("target", "llm_direct")
            conf     = float(data.get("confidence", 0.5))
            reasoning = data.get("reasoning", "LLM classification.")
            est      = _DURATION_ESTIMATES.get(target, 5.0)
            return RouteDecision(
                handler=handler,
                target=target,
                confidence=conf,
                reasoning=f"[LLM] {reasoning}",
                estimated_duration_s=est,
            )
        except Exception as exc:
            logger.debug("[TaskRouter] LLM disambiguation failed: %s", exc)
            return None

    def _load_skill_keywords(self, tool_registry) -> None:
        """Build skill keyword map from a ToolRegistry catalog."""
        try:
            for entry in tool_registry.catalog():
                name = entry.get("name", "")
                schema = entry.get("schema", {})
                description = schema.get("description", "")
                # Use name words + description words as keywords
                words = set(re.findall(r"\w+", (name + " " + description).lower()))
                if words:
                    self._skill_keywords[name] = list(words)
        except Exception as exc:
            logger.warning("[TaskRouter] Could not load skill keywords: %s", exc)

    def add_skill(self, skill_id: str, keywords: list[str]) -> None:
        """Manually register skill keywords (used in tests / boot)."""
        self._skill_keywords[skill_id] = [kw.lower() for kw in keywords]


# ── singleton ─────────────────────────────────────────────────────────────────

task_router = TaskRouter()
