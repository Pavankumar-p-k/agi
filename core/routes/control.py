from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from ..auth import verify_token, User

router = APIRouter(tags=["Computer Control"])

class ComputerControlRequest(BaseModel):
    instruction: str = ""
    confirm: bool = True

@router.post("/computer")
async def computer_control(req: ComputerControlRequest, user: User = Depends(verify_token)):
    from pc_agent.computer_agent import computer_agent
    if not req.instruction:
        raise HTTPException(400, "Instruction is required")
    result = await computer_agent.execute_natural_language(req.instruction, confirm=req.confirm)
    return result
