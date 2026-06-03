from fastapi import APIRouter
router = APIRouter(prefix="/memory", tags=["memory"])

@router.get("/{user_id}")
async def get_memories(user_id: str):
    from memory.mem0_adapter import mem0_memory
    return {"memories": mem0_memory.get_all(user_id)}

@router.delete("/{user_id}")
async def delete_memories(user_id: str):
    from memory.mem0_adapter import mem0_memory
    return {"deleted": mem0_memory.delete_all(user_id)}
