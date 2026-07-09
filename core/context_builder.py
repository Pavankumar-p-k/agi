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
"""core/context_builder.py — Unified context gathering for all chat entry points.

Canonical persistent store: ChatHistory (SQLAlchemy, core/database.py).
ConversationManager (JSON files) is a legacy fallback.
"""

import asyncio
import logging
from typing import Any

from .session import ConversationManager
import importlib as _il
memory = _il.import_module("memory.memory_facade").memory
from tools.ragflow_tool import format_rag_context, ragflow_search

logger = logging.getLogger("jarvis.context")


async def _load_chat_history(session_id: str, last_n: int = 10) -> str:
    """Load recent messages from ChatHistory (SQLAlchemy)."""
    try:
        import sqlalchemy as sa
        from .database import ChatHistory as ChatHistoryModel, get_db
        async for db in get_db():
            stmt = (
                sa.select(ChatHistoryModel)
                .where(ChatHistoryModel.session_id == session_id)
                .order_by(ChatHistoryModel.timestamp.desc())
                .limit(last_n)
            )
            rows = (await db.execute(stmt)).scalars().all()
            if rows:
                history = []
                for r in reversed(rows):
                    history.append({"role": r.role, "content": r.message})
                return "\n".join(f"{m['role']}: {m['content']}" for m in history)
    except Exception as e:
        logger.debug("[context_builder] ChatHistory read failed: %s", e)
    return ""


async def build_unified_context(message: str, session_id: str, extra_context: str = "") -> str:
    """Gather linear history, semantic memory, and RAG into a single context string."""
    
    # 1. Linear History — ChatHistory (canonical) with ConversationManager fallback
    history_context = await _load_chat_history(session_id, last_n=10)
    if not history_context:
        try:
            cm = ConversationManager(session_id=session_id)
            if cm.path.exists():
                cm.load()
                history = cm.get_context(last_n=10)
                history_str = "\n".join([f"{m['role']}: {m['content']}" for m in history])
                history_context = f"## Recent Conversation History:\n{history_str}"
        except Exception as e:
            logger.debug("[context_builder] ConversationManager fallback failed: %s", e)

    # 2. Semantic Memory (Recall) — run in thread to avoid blocking event loop
    loop = asyncio.get_event_loop()
    memories = await loop.run_in_executor(None, lambda: memory.recall(message, user_id=session_id, limit=5))
    memory_context = memory.format_context(memories)

    # 3. RAG (External Knowledge)
    rag_result = await ragflow_search(message, top_k=5)
    rag_context = format_rag_context(rag_result.get("chunks", []))

    # 4. Combine
    parts = []
    if history_context:
        parts.append(f"## Recent Conversation History:\n{history_context}")
    if memory_context:
        parts.append(memory_context)
    if rag_context:
        parts.append(rag_context)
    if extra_context:
        parts.append(f"## Additional Context:\n{extra_context}")

    return "\n\n".join(parts).strip()
