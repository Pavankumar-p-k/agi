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
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import User, verify_token

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
