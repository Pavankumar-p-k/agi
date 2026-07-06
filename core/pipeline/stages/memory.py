"""Memory stage — store execution context in the memory facade
and extract structured facts from the conversation.

**Classification:** Impure (external writes).

**Inputs:** ``context.execution_result``, ``context.outcome``,
``context.verification_result``,
``context.raw_input``, ``context.user_id``

**Outputs:** ``context.store_decision``, ``context.memory_refs``,
``context.extracted_facts``

**Owned:** ``context.memory_refs``, ``context.store_decision``

**Forbidden:** LLM calls, provider selection, Activity creation, transport I/O.
"""
from __future__ import annotations

import logging

from core.pipeline.base import PipelineStage, StageOutcome, StageResult
from core.pipeline.context import PipelineContext
from core.pipeline.store_decision import StoreAction, StoreDecision

logger = logging.getLogger(__name__)


class MemoryStage(PipelineStage):
    @property
    def name(self) -> str:
        return "memory"

    async def execute(self, context: PipelineContext) -> StageResult:
        verification = context.verification_result or {}

        if verification.get("passed") is False:
            context.store_decision = StoreDecision(
                action=StoreAction.IGNORE,
                reason="Verification failed",
            )
            return StageResult(outcome=StageOutcome.CONTINUE, context=context)

        output_text = context.outcome.text if context.outcome else ""
        if not output_text:
            execution_result = context.execution_result or {}
            output_text = execution_result.get("text", "") or ""

        if not output_text.strip():
            context.store_decision = StoreDecision(
                action=StoreAction.IGNORE,
                reason="No output to store",
            )
            return StageResult(outcome=StageOutcome.CONTINUE, context=context)

        store_type = self._classify(context)
        user_id = context.user_id or context.session_id or "default"
        messages = [
            {"role": "user", "content": context.raw_input or ""},
            {"role": "assistant", "content": output_text},
        ]
        refs: list[str] = []

        # ── Store conversation in memory facade ──────────────────────────────
        try:
            from memory.memory_facade import memory

            memory.store(messages, user_id=user_id)
            refs.append(f"memory:{store_type}:{user_id}")
        except Exception as exc:
            logger.warning("Memory stage: facade store failed: %s", exc)

        # ── Extract and store structured facts ───────────────────────────────
        fact_ids: list[str] = []
        contradictions: list[dict] = []

        try:
            from memory.extraction import extract_facts_from_messages
            from memory.fact_store import get_fact_store

            activity_id = context.activity_id
            conversation_id = context.metadata.get("conversation_id") if context.metadata else None

            facts = extract_facts_from_messages(
                messages,
                user_id=user_id,
                activity_id=activity_id,
                conversation_id=conversation_id,
            )
            if facts:
                fact_store = get_fact_store()

                # Check for contradictions before storing
                contradictions = fact_store.find_contradictions(facts, user_id=user_id, threshold=0.6)
                if contradictions:
                    logger.info("Memory stage: %d contradiction(s) detected", len(contradictions))
                    fact_ids = fact_store.store_facts(facts, user_id=user_id, force=True)
                else:
                    fact_ids = fact_store.store_facts(facts, user_id=user_id)

                refs.extend(fact_ids)
        except Exception as exc:
            logger.warning("Memory stage: fact extraction failed: %s", exc)

        context.memory_refs = refs
        context.store_decision = StoreDecision(
            action=StoreAction.STORE,
            store_type=store_type,
            reason="New conversation turn",
            confidence=0.95,
            fact_count=len(fact_ids),
            contradictions=contradictions or None,
            memory_refs=refs,
        )
        return StageResult(outcome=StageOutcome.CONTINUE, context=context)

    def _classify(self, context: PipelineContext) -> str:
        raw_input = (context.raw_input or "").lower()

        preference_keywords = {"my favorite", "i like", "i prefer", "set my", "remember that i"}
        project_keywords = {"project", "working on", "task", "assignment", "repo"}
        fact_keywords = {"remember", "fact", "the answer is", "know that", "learn that"}

        if any(k in raw_input for k in preference_keywords):
            return "preference"
        if any(k in raw_input for k in project_keywords):
            return "project"
        if any(k in raw_input for k in fact_keywords):
            return "fact"
        return "conversation"
