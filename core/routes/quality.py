from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from ..auth import verify_token, User

router = APIRouter(tags=["Quality Assurance"])

class QualityGradeRequest(BaseModel):
    type: str
    content: str

@router.post("/api/quality/grade")
async def quality_grade(
    req: QualityGradeRequest,
    user: User = Depends(verify_token),
):
    from core.llm_router import complete as llm_complete, health_check
    import core.llm_router
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
