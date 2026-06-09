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
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..auth import User, verify_token

router = APIRouter(tags=["Quality Assurance"])

class QualityGradeRequest(BaseModel):
    type: str
    content: str

@router.post("/api/quality/grade")
async def quality_grade(
    req: QualityGradeRequest,
    user: User = Depends(verify_token),
):
    import core.llm_router
    from core.llm_router import health_check
    from core.quality_grader import QualityGrader

    if not await health_check():
        return JSONResponse(status_code=503, content={"error": "Ollama is offline"})

    try:
        grader = QualityGrader(
            constitution_path="config/quality_constitution.json",
            llm_router=core.llm_router,
        )
        grade = await grader.grade(req.type, req.content)
        return {
            "aggregate_score": grade.aggregate_score,
            "passed": grade.passed,
            "criteria": [
                {
                    "id": c.id,
                    "description": c.description,
                    "passed": c.passed,
                    "score": c.score,
                    "evidence": c.evidence,
                }
                for c in grade.criteria
            ],
        }
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
