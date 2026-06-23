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
"""core/context_builder.py — Unified context gathering for all chat entry points."""

import asyncio
import logging
from typing import Any

from .session import ConversationManager
from memory.memory_facade import memory
from tools.ragflow_tool import format_rag_context, ragflow_search

logger = logging.getLogger("jarvis.context")


async def build_unified_context(message: str, session_id: str, extra_context: str = "") -> str:
    """Gather linear history, semantic memory, and RAG into a single context string."""
    
    # 1. Linear History
    cm = ConversationManager(session_id=session_id)
    history_context = ""
    if cm.path.exists():
        cm.load()
        history = cm.get_context(last_n=10)
        history_str = "\n".join([f"{m['role']}: {m['content']}" for m in history])
        history_context = f"## Recent Conversation History:\n{history_str}"

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
        parts.append(history_context)
    if memory_context:
        parts.append(memory_context)
    if rag_context:
        parts.append(rag_context)
    if extra_context:
        parts.append(f"## Additional Context:\n{extra_context}")

    return "\n\n".join(parts).strip()
