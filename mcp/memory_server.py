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
"""
memory_server.py

MCP server exposing memory management (list, add, edit, delete, search).
Uses ``memory.crud_store.CrudStore`` for JSON-file persistence and
``memory.vector_store`` for vector search.
"""

import asyncio
import sys
import time
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent
logger = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

server = Server("memory")

# Late-initialized store (set during first tool call)
_store = None
_initialized = False


def _ensure_init():
    """Lazy-init the CrudStore on first use."""
    global _store, _initialized
    if _initialized:
        return
    _initialized = True

    from core.constants import DATA_DIR
    from memory.crud_store import CrudStore
    _store = CrudStore(DATA_DIR)


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="manage_memory",
            description="Manage the user's memory system: list, add, edit, delete, or search memories.",
            inputSchema={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["list", "add", "edit", "delete", "search"],
                        "description": "The action to perform",
                    },
                    "text": {"type": "string", "description": "Memory text (add/edit) or search query (search)"},
                    "memory_id": {"type": "string", "description": "Memory ID (edit/delete)"},
                    "category": {
                        "type": "string",
                        "enum": ["fact", "event", "contact", "preference"],
                        "description": "Memory category (add/list filter)",
                    },
                },
                "required": ["action"],
            },
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name != "manage_memory":
        return [TextContent(type="text", text=f"Unknown tool: {name}")]

    _ensure_init()
    if not _store:
        return [TextContent(type="text", text="Error: Memory store not available")]

    action = arguments.get("action", "")

    if action == "list":
        category_filter = arguments.get("category", "")
        memories = _store.list_all(category=category_filter) if category_filter else _store.list_all()
        if not memories:
            msg = "No memories found"
            if category_filter:
                msg += f" in category '{category_filter}'"
            return [TextContent(type="text", text=msg + ".")]
        lines = [f"Found {len(memories)} memory entries:\n"]
        for m in memories[:100]:
            cat = m.get("category", "fact")
            mid = m.get("id", "?")[:8]
            text = m.get("text", "")
            if len(text) > 150:
                text = text[:150] + "..."
            lines.append(f"- [{cat}] `{mid}` — {text}")
        if len(memories) > 100:
            lines.append(f"... and {len(memories) - 100} more")
        return [TextContent(type="text", text="\n".join(lines))]

    elif action == "add":
        text = arguments.get("text", "")
        category = arguments.get("category", "fact")
        if not text:
            return [TextContent(type="text", text="Error: Memory text cannot be empty")]
        entry = _store.add(text, source="ai_agent", category=category)
        memories = _store.load_all()
        memories.append(entry)
        _store.save(memories)
        if _store.vector_healthy:
            _store.vector_add(entry["id"], text)
        return [TextContent(type="text", text=f"Memory added: [{category}] {text} (id: {entry['id'][:8]})")]

    elif action == "edit":
        memory_id = arguments.get("memory_id", "")
        new_text = arguments.get("text", "")
        if not memory_id or not new_text:
            return [TextContent(type="text", text="Error: edit needs memory_id and text")]
        old = _store.update(memory_id, text=new_text)
        if old is None:
            return [TextContent(type="text", text=f"Error: Memory '{memory_id}' not found")]
        full_id = old["id"]
        if _store.vector_healthy:
            _store.vector_remove(full_id)
            _store.vector_add(full_id, new_text)
        return [TextContent(type="text", text=f"Memory updated: {new_text}")]

    elif action == "delete":
        memory_id = arguments.get("memory_id", "")
        if not memory_id:
            return [TextContent(type="text", text="Error: delete needs memory_id")]
        all_entries = _store.load_all()
        full_id = None
        deleted_text = ""
        deleted_category = ""
        for m in all_entries:
            if m.get("id", "").startswith(memory_id):
                full_id = m["id"]
                deleted_text = m.get("text", "")
                deleted_category = m.get("category", "")
                break
        if not full_id:
            return [TextContent(type="text", text=f"Error: Memory '{memory_id}' not found")]
        _store.delete(memory_id)
        if _store.vector_healthy:
            _store.vector_remove(full_id)
        cat = f"[{deleted_category}] " if deleted_category else ""
        snippet = deleted_text if len(deleted_text) <= 120 else deleted_text[:117] + "..."
        return [TextContent(type="text", text=f"Memory deleted: {cat}{snippet} (id: {memory_id})")]

    elif action == "search":
        query = arguments.get("text", "")
        if not query:
            return [TextContent(type="text", text="Error: search needs text (query)")]
        results = _store.get_relevant_memories(query, threshold=0.05, max_items=20)
        if not results:
            return [TextContent(type="text", text=f"No memories found matching '{query}'.")]
        lines = [f"Found {len(results)} matching memories:\n"]
        for m in results:
            cat = m.get("category", "fact")
            mid = m.get("id", "?")[:8]
            text = m.get("text", "")
            lines.append(f"- [{cat}] `{mid}` — {text}")
        return [TextContent(type="text", text="\n".join(lines))]

    else:
        return [TextContent(type="text", text=f"Error: Unknown action '{action}'. Use: list, add, edit, delete, search")]


async def run():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(run())
