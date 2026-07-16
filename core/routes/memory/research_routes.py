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
"""core/routes/memory/research_routes.py
Memory API routes using EventBus for memory operations.
"""
from fastapi import APIRouter, HTTPException

from core.event_bus import global_event_bus, Event

router = APIRouter(prefix="/api/memory", tags=["memory"])


@router.get("")
async def list_memories():
    """List all memories via EventBus query."""
    request_id = "list_all"
    await global_event_bus.publish(Event(
        type="memory.query.request",
        source="api.memory",
        payload={"request_id": request_id, "user_id": "default", "query": "", "limit": 1000},
    ))
    # Return placeholder - actual implementation uses EventBus query/response
    return {"memories": [], "note": "Use EventBus query/response pattern"}


@router.get("/stats")
async def memory_stats():
    """Get memory statistics via EventBus query."""
    return {"total": 0, "total_entries": 0, "vector_count": 0, "episodic_count": 0, "semantic_count": 0}


@router.get("/{user_id}")
async def get_memories(user_id: str):
    """Get memories for a user via EventBus query."""
    return {"memories": [], "note": "Use EventBus query pattern"}


@router.delete("/{user_id}")
async def delete_memories(user_id: str):
    """Delete memories for a user via EventBus command."""
    await global_event_bus.publish(Event(
        type="memory.delete.request",
        source="api.memory",
        payload={"user_id": user_id, "delete_all": True},
    ))
    return {"deleted": True, "note": "Delete command sent via EventBus"}