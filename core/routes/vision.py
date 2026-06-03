from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.auth import verify_token

router = APIRouter(tags=["vision"])


class VisionAnalyzeRequest(BaseModel):
    question: str = ""


@router.post("/api/vision/screen")
async def vision_screen(user=Depends(verify_token)):
    try:
        from core.vision_agent import VisionAgent
        agent = VisionAgent()
        try:
            state = await agent._capture()
            desc = await agent._describe(state)
            return {
                "description": desc,
                "b64": state.b64,
                "width": state.w,
                "height": state.h,
            }
        finally:
            await agent.close()
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/api/vision/analyze")
async def vision_analyze(req: VisionAnalyzeRequest, user=Depends(verify_token)):
    question = req.question or "What is on my screen?"
    try:
        from core.vision_agent import VisionAgent
        from core.model_router import get_ollama_url, model_for_role
        agent = VisionAgent()
        try:
            state = await agent._capture()
            vision_model = model_for_role("vision")
            import httpx
            async with httpx.AsyncClient(timeout=120) as client:
                r = await client.post(
                    f"{get_ollama_url(vision_model)}/api/generate",
                    json={
                        "model": vision_model,
                        "prompt": question,
                        "images": [state.b64],
                        "stream": False,
                        "options": {"num_predict": 256, "temperature": 0.3, "num_gpu": 99}}
                )
            answer = r.json().get("response", "").strip()
            return {"question": question, "answer": answer, "b64": state.b64}
        finally:
            await agent.close()
    except Exception as e:
        raise HTTPException(500, str(e))
