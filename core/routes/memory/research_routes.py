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
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/memory", tags=["memory"])


@router.get("")
async def list_memories():
    from memory.memory_facade import memory
    return memory.get_all("default")


@router.get("/stats")
async def memory_stats():
    from memory.memory_facade import memory
    all_mem = memory.get_all("default")
    total = len(all_mem)
    vector_count = sum(1 for m in all_mem if m.get("tier") == "hot" or m.get("vector"))
    episodic_count = sum(1 for m in all_mem if m.get("type") == "episodic" or "session" in str(m.get("memory", "")))
    semantic_count = total - episodic_count
    return {
        "total": total,
        "total_entries": total,
        "vector_count": vector_count,
        "episodic_count": episodic_count,
        "semantic_count": semantic_count,
    }


@router.get("/{user_id}")
async def get_memories(user_id: str):
    from memory.memory_facade import memory
    return {"memories": memory.get_all(user_id)}


@router.delete("/{user_id}")
async def delete_memories(user_id: str):
    from memory.memory_facade import memory
    return {"deleted": memory.delete_all(user_id)}
