from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional
from ..auth import verify_token, User

router = APIRouter(tags=["Utilities & Code"])

class CodeReviewRequest(BaseModel):
    code: str
    language: str
    context: Optional[str] = None

@router.post("/api/code/review")
async def code_review(
    req: CodeReviewRequest,
    user: User = Depends(verify_token),
):
    """Review code for bugs, security issues, and style problems."""
    from core.llm_router import complete as llm_complete, health_check
    if not await health_check():
        return JSONResponse(status_code=503, content={"error": "Ollama is offline", "language": req.language})
    prompt = (
        f"Review this {req.language} code for:\n"
        f"1. Bugs and logic errors\n"
        f"2. Security vulnerabilities\n"
        f"3. Performance issues\n"
        f"4. Code style improvements\n\n"
        f"Context: {req.context or 'N/A'}\n\n"
        f"```{req.language}\n{req.code}\n```\n\n"
        f"Format: For each issue found, state: SEVERITY (critical/major/minor), what, where, fix."
    )
    try:
        review = (await llm_complete("code", [{"role": "user", "content": prompt}])).unwrap_or("")
        return {"review": review, "language": req.language}
    except Exception as e:
        return {"error": str(e), "language": req.language}
