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
"""Vision agent API routes — consolidated from api/vision_routes.py."""

from __future__ import annotations

import asyncio
import time

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from core.auth import verify_token

router = APIRouter(tags=["vision"])

# ── Shared agent state (for run/task endpoints) ──────────────

_agent: object | None = None
_VisionAgent: type = None
_Task: type = None
_tasks: dict = {}
_running: str | None = None


async def _lazy_init():
    global _VisionAgent, _Task
    if _VisionAgent is None:
        from core.vision_agent import Task as VA_Task
        from core.vision_agent import VisionAgent
        _VisionAgent = VisionAgent
        _Task = VA_Task


async def _get_agent():
    global _agent
    if _agent is None:
        await _lazy_init()
        _agent = _VisionAgent()
    return _agent


# ── Models ───────────────────────────────────────────────────

class VisionAnalyzeRequest(BaseModel):
    question: str = ""


class RunRequest(BaseModel):
    instruction: str
    platform: str = "pc"
    background: bool = False


class ScreenRequest(BaseModel):
    platform: str = "pc"


# ── Simple endpoints (per-request agent) ─────────────────────

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
        import importlib as _il
        _llm_router = _il.import_module("core.llm_router")
        get_ollama_url = _llm_router.get_ollama_url
        model_for_role = _llm_router.model_for_role
        from core.vision_agent import VisionAgent
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


# ── Run / task endpoints (global agent, playbook support) ────

@router.post("/api/vision/run")
async def run_task(req: RunRequest, bg: BackgroundTasks, user=Depends(verify_token)):
    global _running
    instr = req.instruction.strip()
    tid = f"t{int(time.time()*1000)}"

    if req.background:
        bg.add_task(_run_bg, tid, instr, req.platform)
        return {"task_id": tid, "status": "started", "instruction": instr}

    result = await _execute(tid, instr, req.platform)
    return result


@router.get("/api/vision/task/{task_id}")
async def get_task(task_id: str, user=Depends(verify_token)):
    if task_id in _tasks:
        return _tasks[task_id]
    return {"task_id": task_id, "status": "running"}


@router.get("/api/vision/history")
async def get_history(user=Depends(verify_token)):
    agent = await _get_agent()
    return {"tasks": agent.get_history()}


@router.post("/api/vision/screenshot")
async def screenshot(req: ScreenRequest, user=Depends(verify_token)):
    agent = await _get_agent()
    state = await agent._capture()
    return {"b64": state.b64, "w": state.w, "h": state.h}


@router.post("/api/vision/describe")
async def describe_screen(user=Depends(verify_token)):
    agent = await _get_agent()
    state = await agent._capture()
    desc = await agent._describe(state)
    return {"description": desc, "b64": state.b64}


@router.get("/api/vision/playbooks")
async def list_playbooks(user=Depends(verify_token)):
    from pc_agent.playbooks import _PB
    return {
        "count": len(_PB),
        "playbooks": [
            {"name": name, "patterns": pb["pats"][:1]}
            for name, pb in _PB.items()
        ]
    }


@router.get("/api/vision/status")
async def status(user=Depends(verify_token)):
    agent = await _get_agent()
    return {
        "ready": _agent is not None,
        "running_task": _running,
        "tasks_done": len(agent.get_history()),
    }


# ── Execution helpers ────────────────────────────────────────

async def _run_bg(tid: str, instr: str, platform: str):
    _tasks[tid] = await _execute(tid, instr, platform)


async def _execute(tid: str, instr: str, platform: str) -> dict:
    global _running
    _running = tid
    t0 = time.time()
    agent = await _get_agent()

    try:
        from pc_agent.playbooks import build_steps, match
        hit = match(instr)
        if hit:
            steps = build_steps(hit)
            task = _Task(id=tid, instruction=instr)
            task.steps = steps
            task.status = "running"

            for i, step in enumerate(steps):
                res = await agent._do(step)
                step["_status"] = res.status
                step["_output"] = res.output
                if res.status == "failed":
                    alt = await agent._correct(step, res.error)
                    if alt:
                        res2 = await agent._do(alt)
                        step["_status"] = res2.status
                await asyncio.sleep(0.15)

            task.status = "done"
            task.t_end = time.time()
            done = sum(1 for s in task.steps if s.get("_status") == "done")
            task.result = f"[OK] {hit['name']} — {done}/{len(steps)} steps done"
            agent._history.append(task)
        else:
            task = await agent.run(instr)

        _running = None
        return _task_dict(task, t0, hit["name"] if hit else None)

    except Exception as e:
        _running = None
        return {"task_id": tid, "status": "failed", "error": str(e), "latency_ms": int((time.time() - t0) * 1000)}


def _task_dict(task: object, t0: float, playbook: str | None) -> dict:
    done = sum(1 for s in task.steps if isinstance(s, dict) and s.get("_status") == "done")
    total = len(task.steps)
    return {
        "task_id": task.id,
        "instruction": task.instruction,
        "status": task.status,
        "result": task.result,
        "error": task.error,
        "steps_done": done,
        "steps_total": total,
        "playbook": playbook,
        "latency_ms": int((time.time() - t0) * 1000),
        "steps": [
            {"n": s.get("step_num"), "desc": s.get("desc"), "action": s.get("action"), "status": s.get("_status", "pending")}
            for s in task.steps
        ],
    }
