from __future__ import annotations

import uuid
from functools import lru_cache
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from jarvis_os.bootstrap import build_jarvis_os


router = APIRouter(prefix="/os", tags=["jarvis-os"])


class PromptRequest(BaseModel):
    prompt: str = ""
    agent_name: str = "auto"
    context: dict[str, Any] = Field(default_factory=dict)


@lru_cache(maxsize=1)
def get_runtime():
    return build_jarvis_os()


def _goal(prompt: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "goal_id": f"goal_{uuid.uuid4().hex[:10]}",
        "prompt": prompt,
        "context": dict(context or {}),
    }


def _normalize_execution(result: dict[str, Any]) -> dict[str, Any]:
    payload = dict(result)
    execution = dict(payload.get("execution", {}))
    if "results" in execution and "step_results" not in execution:
        execution["step_results"] = list(execution.get("results", []))
    if "latency_ms" not in payload:
        started_at = execution.get("started_at")
        completed_at = execution.get("completed_at")
        if started_at and completed_at:
            payload["latency_ms"] = int((completed_at - started_at) * 1000)
        else:
            payload["latency_ms"] = 0
    payload["execution"] = execution
    return payload


def _status_payload() -> dict[str, Any]:
    runtime = get_runtime()
    status = runtime.status()
    return {
        "initialized": True,
        "components": {
            "tools": runtime.tools.catalog(),
            "models": status.get("models", {}),
            "scheduler": {"count": status.get("schedule_count", 0)},
            "skills_registry": {"count": status.get("skills", 0)},
            "supervisor": status.get("daemon", {}),
            "safety": status.get("policy", {}),
            "self_improvement": {"running": status.get("daemon", {}).get("running", False)},
            "world_model": {
                "memories": status.get("memory_items", 0),
                "goals": len(runtime.list_jobs().get("jobs", [])),
                "knowledge": 0,
                "experiences": 0,
            },
            "learning": {"enabled": True, "student_agi_loaded": False},
            "browser": {"mode": "local"},
            "access_manager": {"grants": []},
            "mobile_sync": {"linked_devices": []},
            "gateway": {"channels": {}},
        },
    }


@router.get("/tools")
def tools() -> dict[str, Any]:
    return {"tools": get_runtime().tools.catalog()}


@router.get("/status")
def status() -> dict[str, Any]:
    return _status_payload()


@router.post("/agents/preview")
@router.post("/agent/plan")
def preview(req: PromptRequest) -> dict[str, Any]:
    runtime = get_runtime()
    result = runtime.preview_prompt(req.prompt, context=req.context, agent_name=req.agent_name)
    result["goal"] = _goal(req.prompt, req.context)
    return result


@router.post("/run")
def run_agent(req: PromptRequest) -> dict[str, Any]:
    runtime = get_runtime()
    result = runtime.handle_prompt(req.prompt, context=req.context, agent_name=req.agent_name)
    return _normalize_execution(result)


@router.post("/agents/submit")
@router.post("/agent/submit")
def submit(req: PromptRequest) -> dict[str, Any]:
    runtime = get_runtime()
    submission = runtime.submit_prompt(req.prompt, context=req.context, agent_name=req.agent_name)
    preview = submission.get("preview", {})
    job = submission.get("job", {})
    return {
        "goal": _goal(req.prompt, req.context),
        "job_id": job.get("job_id", ""),
        "plan": preview.get("plan", {}),
        "analysis": preview.get("analysis", {}),
        "specialist": preview.get("specialist", {}),
    }


@router.get("/executions/{job_id}")
def execution(job_id: str) -> dict[str, Any]:
    runtime = get_runtime()
    job = runtime.get_job(job_id)
    result = job.get("result", {})
    if result:
        result = _normalize_execution(result)
        execution_payload = result.get("execution", {})
        return {
            "job_id": job_id,
            "status": job.get("status", "missing"),
            "result": {
                "summary": execution_payload.get("summary", result.get("reply", "")),
                "step_results": execution_payload.get("step_results", []),
            },
        }
    return {
        "job_id": job_id,
        "status": job.get("status", "missing"),
        "error": job.get("error", ""),
    }


@router.post("/jobs/{job_id}/pause")
def pause_job(job_id: str) -> dict[str, Any]:
    return get_runtime().pause_job(job_id)


@router.post("/jobs/{job_id}/resume")
def resume_job(job_id: str) -> dict[str, Any]:
    return get_runtime().resume_job(job_id)
