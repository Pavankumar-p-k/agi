from __future__ import annotations

import asyncio
import logging
from typing import Any

from core.pipeline.base import PipelineStage, StageOutcome, StageResult
from core.pipeline.context import PipelineContext

logger = logging.getLogger(__name__)


class ContextRetrievalStage(PipelineStage):
    @property
    def name(self) -> str:
        return "context_retrieval"

    async def execute(self, context: PipelineContext) -> StageResult:
        if not context.raw_input or not context.raw_input.strip():
            context.retrieved_context = {"memories": [], "formatted_context": ""}
            return StageResult(outcome=StageOutcome.CONTINUE, context=context)

        memories = await self._recall(context)
        formatted = self._format(memories)

        # Append known user preferences as additional context
        preferences_context = self._load_preferences(context)
        if preferences_context:
            if formatted:
                formatted += "\n\n" + preferences_context
            else:
                formatted = preferences_context

        context.retrieved_context = {
            "memories": memories,
            "formatted_context": formatted,
            "preferences": self._get_preferences_dict(context),
        }
        return StageResult(outcome=StageOutcome.CONTINUE, context=context)

    async def _recall(self, context: PipelineContext) -> list[dict[str, Any]]:
        try:
            from memory.memory_facade import memory

            user_id = context.user_id or context.session_id or "default"
            loop = asyncio.get_event_loop()
            result = await asyncio.wait_for(
                loop.run_in_executor(
                    None, lambda: memory.recall(context.raw_input, user_id=user_id, limit=5)
                ),
                timeout=5.0,
            )
            re_ranked = self._rerank(context.raw_input, result, user_id)
            return re_ranked[:5]
        except asyncio.TimeoutError:
            logger.warning("ContextRetrieval: memory recall timed out")
            return []
        except Exception as exc:
            logger.warning("ContextRetrieval: memory recall failed: %s", exc)
            return []

    def _rerank(
        self,
        query: str,
        items: list[dict[str, Any]],
        user_id: str,
    ) -> list[dict[str, Any]]:
        """Re-rank memory items for relevance."""
        try:
            from memory.reranker import ReRanker

            prefs = self._get_preferences_for_user(user_id)
            return ReRanker().rerank(query, items, user_preferences=prefs)
        except Exception as exc:
            logger.debug("ContextRetrieval: reranking unavailable: %s", exc)
            return items

    def _get_preferences_for_user(self, user_id: str) -> dict[str, str]:
        try:
            from memory.fact_store import get_fact_store
            from memory.preference_profile import PreferenceProfile

            fact_store = get_fact_store()
            profile = PreferenceProfile(user_id).build(fact_store)
            return profile.to_dict()
        except Exception:
            return {}

    def _format(self, memories: list[dict[str, Any]]) -> str:
        if not memories:
            return ""
        try:
            from memory.memory_facade import memory

            return memory.format_context(memories)
        except Exception as exc:
            logger.warning("ContextRetrieval: format_context failed: %s", exc)
            return ""

    def _load_preferences(self, context: PipelineContext) -> str:
        """Load and format known user preferences as additional context."""
        try:
            from memory.fact_store import get_fact_store
            from memory.preference_profile import PreferenceProfile

            user_id = context.user_id or context.session_id or "default"
            fact_store = get_fact_store()
            profile = PreferenceProfile(user_id).build(fact_store)
            return profile.format_context()
        except Exception as exc:
            logger.debug("ContextRetrieval: preference profile unavailable: %s", exc)
            return ""

    def _get_preferences_dict(self, context: PipelineContext) -> dict[str, str]:
        try:
            from memory.fact_store import get_fact_store
            from memory.preference_profile import PreferenceProfile

            user_id = context.user_id or context.session_id or "default"
            fact_store = get_fact_store()
            profile = PreferenceProfile(user_id).build(fact_store)
            return profile.to_dict()
        except Exception:
            return {}
