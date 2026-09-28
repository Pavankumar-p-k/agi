"""MemoryStage — decides what to persist from this request (Rule 2/3 owner).

Decisions:
  verification failed            -> IGNORE
  empty execution output         -> IGNORE
  otherwise                      -> STORE with a classified store_type:
    preference / project / fact / conversation (keyword classification).
"""
from __future__ import annotations

import re
from typing import Any

from core.pipeline.base import PipelineStage, StageOutcome, StageResult
from core.pipeline.pipeline import PipelineContext
from core.pipeline.store_decision import StoreAction, StoreDecision


_PREFERENCE_RE = re.compile(
    r"\b(my favorite|i prefer|i like|i love|i hate|my preferred|"
    r"favorite|favourite)\b", re.IGNORECASE)
_PROJECT_RE = re.compile(
    r"\b(i am working on|working on a|my project|the project|"
    r"new project|our project|repo|repository)\b", re.IGNORECASE)
_FACT_RE = re.compile(
    r"\b(remember that|remember this|note that|keep in mind|"
    r"the fact that|fact:)\b", re.IGNORECASE)


class MemoryStage(PipelineStage):
    @property
    def name(self) -> str:
        return "memory"

    def _classify(self, ctx: PipelineContext) -> str:
        raw = str(getattr(ctx, "raw_input", "") or "")
        if _PREFERENCE_RE.search(raw):
            return "preference"
        if _PROJECT_RE.search(raw):
            return "project"
        if _FACT_RE.search(raw):
            return "fact"
        return "conversation"

    async def execute(self, context: PipelineContext) -> StageResult:
        # 1) Never store unverified output.
        verification = context.verification_result or {}
        if isinstance(verification, dict) and verification.get("passed") is False:
            context.store_decision = StoreDecision(
                action=StoreAction.IGNORE, reason="verification failed")
            context.memory_refs = []
            return StageResult(outcome=StageOutcome.CONTINUE, context=context)

        # 2) Nothing to store when execution produced no text.
        execution = context.execution_result or {}
        text = execution.get("text", "") if isinstance(execution, dict) \
            else str(execution or "")
        if not str(text).strip() and not str(getattr(context, "raw_input", "")).strip():
            context.store_decision = StoreDecision(
                action=StoreAction.IGNORE, reason="no output")
            context.memory_refs = []
            return StageResult(outcome=StageOutcome.CONTINUE, context=context)

        # 3) Classify and record the decision.  Actual persistence goes
        # through the memory facade (Rule 2: writes confined to this stage).
        store_type = self._classify(context)
        user_id = getattr(context, "user_id", None) or ""
        context.store_decision = StoreDecision(
            action=StoreAction.STORE, store_type=store_type,
            reason=f"classified as {store_type}", confidence=0.8,
            payload={"text": text[:2000], "user_id": user_id},
        )
        context.memory_refs = []
        return StageResult(outcome=StageOutcome.CONTINUE, context=context)


# ── sanctioned memory gateways (Rules 2/3) ──────────────────────────
# Memory persistence is owned by this stage. Specialists (browser, research,
# coding) that need to persist a fact or an episode call these helpers rather
# than importing the facade/fact store themselves.
def store_facts(facts: list, *, user_id: str = "", tenant_id: str = "default",
                resource_scope: Any = None, force: bool = False) -> list:
    """Persist extracted facts through the canonical fact store."""
    from memory.fact_store import get_fact_store

    scope = resource_scope
    if tenant_id is None and scope is not None:
        tenant_id = getattr(scope, "tenant_id", "") or ""
    store = get_fact_store()
    try:
        return store.store_facts(list(facts or []), user_id=user_id,
                                 tenant_id=tenant_id or "", force=force)
    except TypeError:  # older store signatures without tenant_id
        return store.store_facts(list(facts or []), force=force)


def store_episode(*, goal: str, actions: list, context: Any = None,
                  result: Any = None, episode_type: str = "task",
                  tags: Any = None, user_id: str = "default") -> Any:
    """Mirror an episode into the episodic store via the memory facade."""
    from memory.memory_facade import memory

    return memory.store_episode(
        goal=goal, actions=list(actions or []),
        context=dict(context or {}), result=dict(result or {}),
        episode_type=episode_type, tags=list(tags or []), user_id=user_id,
    )


__all__ = ["MemoryStage", "store_facts", "store_episode"]
