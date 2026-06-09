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
from fastapi import APIRouter

router = APIRouter(prefix="/memory", tags=["memory"])

@router.get("/{user_id}")
async def get_memories(user_id: str):
    from memory.memory_facade import memory
    return {"memories": memory.get_all(user_id)}

@router.delete("/{user_id}")
async def delete_memories(user_id: str):
    from memory.memory_facade import memory
    return {"deleted": memory.delete_all(user_id)}
