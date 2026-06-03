# api/vision_routes.py
"""
VISION AGENT API — add to existing JARVIS main.py:

  from api.vision_routes import router as vision_router
  app.include_router(vision_router)

  @app.on_event("startup")
  async def startup():
      from api.vision_routes import init_agents
      await init_agents()
"""

import asyncio, time
from fastapi import APIRouter, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional

from pc_agent.playbooks  import match, build_steps

router = APIRouter(prefix="/vision", tags=["vision"])

_agent:   Optional[object] = None
_VisionAgent: type = None
_Task: type = None
_tasks:   dict = {}    # bg tasks: id → result
_running: Optional[str] = None   # currently running task id


async def _lazy_init():
    global _VisionAgent, _Task
    if _VisionAgent is None:
        from core.vision_agent import VisionAgent, Task as VA_Task
        _VisionAgent = VisionAgent
        _Task = VA_Task


async def init_agents():
    global _agent
    await _lazy_init()
    _agent = _VisionAgent()
    print("[VisionAPI] Vision Agent ready [OK]")


async def _get_agent():
    global _agent
    if _agent is None:
        await init_agents()
    return _agent


# ─── Models ──────────────────────────────────────────────────

class RunReq(BaseModel):
    instruction: str
    platform:    str  = "pc"    # "pc" or "android"
    background:  bool = False   # fire-and-forget

class ScreenReq(BaseModel):
    platform: str = "pc"


# ─── Routes ──────────────────────────────────────────────────

@router.post("/run")
async def run_task(req: RunReq, bg: BackgroundTasks):
    """
    Run a natural language task on PC or Android.

    PC examples:
      "open chrome search amazon buy white t-shirt under 500"
      "open instagram find rahul send happy birthday"
      "open whatsapp message mom — I'm coming home"
      "open photos share latest photo to rahul"
      "open photos delete screenshots"
      "youtube play lofi music"
      "google search latest iphone price"
      "send email to rahul@gmail.com about meeting tomorrow at 3pm"

    Android examples (requires ADB):
      "android: open instagram dm rahul happy birthday"
      "android: open whatsapp message mom I'm home"
      "android: share latest photo to rahul"
    """
    global _running
    instr = req.instruction.strip()
    tid   = f"t{int(time.time()*1000)}"

    if req.background:
        bg.add_task(_run_bg, tid, instr, req.platform)
        return {"task_id": tid, "status": "started", "instruction": instr}

    result = await _execute(tid, instr, req.platform)
    return result


@router.get("/task/{task_id}")
async def get_task(task_id: str):
    """Poll background task result."""
    if task_id in _tasks:
        return _tasks[task_id]
    return {"task_id": task_id, "status": "running"}


@router.get("/history")
async def get_history():
    """Recent task history."""
    agent = await _get_agent()
    return {"tasks": agent.get_history()}


@router.post("/screenshot")
async def screenshot(req: ScreenReq):
    """Capture current screen and return as base64 JPEG."""
    agent = await _get_agent()
    state = await agent._capture()
    return {"b64": state.b64, "w": state.w, "h": state.h}


@router.post("/describe")
async def describe_screen():
    """LLava describes what's currently on screen."""
    agent = await _get_agent()
    state = await agent._capture()
    desc  = await agent._describe(state)
    return {"description": desc, "b64": state.b64}


@router.get("/playbooks")
async def list_playbooks():
    """List all known task playbooks."""
    from pc_agent.playbooks import _PB
    return {
        "count": len(_PB),
        "playbooks": [
            {"name": name, "patterns": pb["pats"][:1]}
            for name, pb in _PB.items()
        ]
    }


@router.get("/status")
async def status():
    """Vision agent status."""
    agent = await _get_agent()
    return {
        "ready":        _agent is not None,
        "running_task": _running,
        "tasks_done":   len(agent.get_history()),
    }


# ─── Execution ───────────────────────────────────────────────

async def _run_bg(tid, instr, platform):
    _tasks[tid] = await _execute(tid, instr, platform)


async def _execute(tid: str, instr: str, platform: str) -> dict:
    global _running
    _running = tid
    t0 = time.time()
    agent = await _get_agent()

    try:
        # Try playbook first — faster and more reliable
        hit = match(instr)
        if hit:
            print(f"[VisionAPI] Playbook: {hit['name']}")
            steps = build_steps(hit)
            task  = _Task(id=tid, instruction=instr)
            task.steps  = steps
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
            task.t_end  = time.time()
            done  = sum(1 for s in task.steps if s.get("_status")=="done")
            task.result = f"[OK] {hit['name']} — {done}/{len(steps)} steps done"
            agent._history.append(task)

        else:
            # Full vision planning
            task = await agent.run(instr)

        _running = None
        return _task_dict(task, t0, hit["name"] if hit else None)

    except Exception as e:
        _running = None
        return {"task_id": tid, "status": "failed", "error": str(e), "latency_ms": int((time.time()-t0)*1000)}


def _task_dict(task: object, t0: float, playbook: Optional[str]) -> dict:
    done  = sum(1 for s in task.steps if isinstance(s,dict) and s.get("_status")=="done")
    total = len(task.steps)
    return {
        "task_id":     task.id,
        "instruction": task.instruction,
        "status":      task.status,
        "result":      task.result,
        "error":       task.error,
        "steps_done":  done,
        "steps_total": total,
        "playbook":    playbook,
        "latency_ms":  int((time.time()-t0)*1000),
        "steps": [
            {"n": s.get("step_num"), "desc": s.get("desc"), "action": s.get("action"), "status": s.get("_status","pending")}
            for s in task.steps
        ],
    }
