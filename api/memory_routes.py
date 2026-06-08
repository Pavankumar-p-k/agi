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
