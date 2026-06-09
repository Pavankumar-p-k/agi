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
import asyncio
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from core.auth import verify_token
from core.database import User
from core.schemas import HorizonGoalRequest, QualityGradeRequest

router = APIRouter(tags=["admin"])


# ── QUALITY ─────────────────────────────────────────────────────────

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
            constitution_path=str(Path(__file__).parent.parent.parent / "config" / "quality_constitution.json"),
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


# ── HORIZON PLANNER ─────────────────────────────────────────────────

@router.post("/api/horizon/goal")
async def create_horizon_goal(req: HorizonGoalRequest, user: User = Depends(verify_token)):
    from core.horizon_planner import HorizonPlanner
    planner = HorizonPlanner()
    goal = planner.create(req.goal, req.domain, req.horizon, req.deadline)
    return {"goal_id": goal.goal_id, "description": goal.description, "milestones": [m.__dict__ for m in goal.milestones]}


@router.get("/api/horizon/goals")
async def list_horizon_goals(domain: str | None = None, user: User = Depends(verify_token)):
    from core.horizon_planner import HorizonPlanner
    planner = HorizonPlanner()
    goals = planner.list(domain)
    return {"goals": [{"goal_id": g.goal_id, "description": g.description, "domain": g.domain,
                        "horizon": g.horizon, "deadline": g.deadline, "progress": g.progress,
                        "milestones": [m.__dict__ for m in g.milestones],
                        "created_at": g.created_at, "updated_at": g.updated_at} for g in goals]}


@router.post("/api/horizon/goal/{goal_id}/advance")
async def advance_horizon_goal(goal_id: str, user: User = Depends(verify_token)):
    from core.horizon_planner import HorizonPlanner
    planner = HorizonPlanner()
    goal = planner.advance(goal_id)
    if goal is None:
        raise HTTPException(404, "Goal not found")
    return {"result": f"Advanced goal '{goal.description[:40]}'", "progress": goal.progress}


@router.delete("/api/horizon/goal/{goal_id}")
async def delete_horizon_goal(goal_id: str, user: User = Depends(verify_token)):
    from core.horizon_planner import HorizonPlanner
    planner = HorizonPlanner()
    ok = planner.delete(goal_id)
    return {"ok": ok}


@router.post("/api/system/test-alert")
async def test_proactive_alert(request: Request, user: User = Depends(verify_token)):
    from core.proactive_monitor import Alert
    pm = getattr(request.app.state, "proactive_monitor", None)
    if pm is None:
        raise HTTPException(503, "ProactiveMonitor not initialized")
    alert = Alert(priority="medium", module="test", message="Test alert received",
                  voice_summary="Test alert received")
    await pm._notify(alert)
    return {"fired": True, "alert": alert.to_dict()}


# ── DOCUMENT PROCESSOR UPLOAD ──────────────────────────────────────

@router.post("/api/chat/upload")
async def chat_upload(file: UploadFile = File(...), user: User = Depends(verify_token)):
    file_bytes = await file.read()
    size_mb = len(file_bytes) / (1024 * 1024)
    if size_mb > 50:
        raise HTTPException(413, f"File too large ({size_mb:.1f} MB). Max: 50 MB")
    if not file.filename:
        raise HTTPException(400, "Filename is required")
    ext = Path(file.filename).suffix.lower()
    allowed = {".pdf", ".docx", ".doc", ".xlsx", ".xls", ".csv", ".txt", ".md",
               ".py", ".json", ".png", ".jpg", ".jpeg", ".webp", ".gif"}
    if ext not in allowed:
        raise HTTPException(400, f"Unsupported file type: {ext}")
    from core.document_processor import doc_processor
    saved_path = await doc_processor.save_upload(file_bytes, file.filename)
    ctx = await doc_processor.process(saved_path)
    return ctx.to_dict()


# ── AUDIO EMOTION ANALYSIS ─────────────────────────────────────────

@router.post("/api/audio/analyze-emotion")
async def analyze_audio_emotion(file: UploadFile = File(...), user: User = Depends(verify_token)):
    import tempfile
    from dataclasses import asdict

    from core.audio_emotion import emotion_detector
    suffix = Path(file.filename).suffix if file.filename else ".wav"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name
    try:
        audio_ctx = await emotion_detector.analyze(tmp_path)
        result = asdict(audio_ctx)
        result["is_urgent"] = audio_ctx.is_urgent
        return result
    finally:
        Path(tmp_path).unlink(missing_ok=True)


# ── 3D SCENE GENERATION ────────────────────────────────────────────

class SceneRequest(BaseModel):
    description: str
    output_format: str = "auto"


@router.post("/api/scene/generate")
async def generate_3d_scene(request: SceneRequest, user: User = Depends(verify_token)):
    from brain.UnifiedBrain import unified_brain
    from tools.scene_generator import scene_generator
    result = await scene_generator.generate(
        description=request.description,
        brain=unified_brain,
        output_format=request.output_format,
    )
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error or "Scene generation failed")
    response = {"success": result.success, "output_format": result.output_format, "attempts": result.attempts}
    if result.artifact_code:
        response["artifact_code"] = result.artifact_code
        response["artifact_type"] = "html"
    if result.render_path:
        response["render_path"] = result.render_path
    return response


# ── PROMPT OPTIMIZATION ────────────────────────────────────────────

@router.post("/api/system/prompt-optimize")
async def system_prompt_optimize(request: Request, agent: str | None = Query(None), user: User = Depends(verify_token)):
    opt = getattr(request.app.state, "prompt_optimizer", None)
    if not opt:
        raise HTTPException(status_code=503, detail="PromptOptimizer not initialized")
    if agent:
        output_type = opt.AGENT_OUTPUT_TYPE.get(agent)
        if not output_type:
            raise HTTPException(status_code=400, detail=f"Unknown agent: {agent}")
        result = await opt.optimize_agent(agent, output_type)
        return [result]
    results = await opt.run_cycle()
    return results


@router.get("/api/system/prompt-versions")
async def system_prompt_versions(agent: str | None = Query(None), user: User = Depends(verify_token)):
    from brain.prompt_optimizer import PromptStore
    store = PromptStore()
    if agent:
        return {"agent": agent, "history": store.get_history(agent),
                "active": store.get_active(agent), "can_rollback": store.can_rollback(agent)}
    all_agents = ["chat", "coder", "researcher", "website_builder",
                  "critic", "grader", "orchestrator"]
    return {a: {"history": store.get_history(a), "active": store.get_active(a),
                 "can_rollback": store.can_rollback(a)} for a in all_agents}


@router.post("/api/system/prompt-rollback/{agent}")
async def system_prompt_rollback(request: Request, agent: str, user: User = Depends(verify_token)):
    opt = getattr(request.app.state, "prompt_optimizer", None)
    if not opt:
        raise HTTPException(status_code=503, detail="PromptOptimizer not initialized")
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, opt.rollback_agent, agent)
    if result["status"] == "error":
        raise HTTPException(status_code=400, detail=result["reason"])
    return result
