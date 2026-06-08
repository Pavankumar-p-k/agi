"""cli_requests.py — HTTP request, polling, and streaming helpers for the JARVIS CLI."""
from __future__ import annotations

import asyncio
import concurrent.futures
import json
import time
import uuid
import urllib.error
import urllib.request
from typing import Optional

from cli_utils import colorize
from cli_state import ROOT

_legacy_route_notice_shown = False
_local_runtime_notice_shown = False
_local_os_runtime = None


def get_local_os_runtime():
    global _local_os_runtime
    if str(ROOT) not in __import__('sys').path:
        __import__('sys').path.insert(0, str(ROOT))
    if _local_os_runtime is None:
        try:
            from jarvis_os.bootstrap import build_jarvis_os
        except ImportError:
            build_jarvis_os = None
        if build_jarvis_os is None:
            _local_os_runtime = {}
        else:
            _local_os_runtime = build_jarvis_os()
    return _local_os_runtime


def _run_async(coro):
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(asyncio.run, coro)
        return future.result()


def _normalize_local_execution(result: dict) -> dict:
    execution = dict(result.get("execution", {}))
    if "results" in execution and "step_results" not in execution:
        execution["step_results"] = list(execution.get("results", []))
    if "latency_ms" not in result:
        if execution.get("started_at") and execution.get("completed_at"):
            result["latency_ms"] = int((execution["completed_at"] - execution["started_at"]) * 1000)
        else:
            result["latency_ms"] = 0
    result["execution"] = execution
    return result


def _local_goal(prompt: str, context: dict | None = None) -> dict:
    return {
        "goal_id": f"goal_{uuid.uuid4().hex[:10]}",
        "prompt": prompt,
        "context": dict(context or {}),
    }


def legacy_endpoint_fallback(endpoint: str, payload: dict | None = None) -> tuple[str, dict | None] | None:
    mapping = {
        "/os/agents/run": "/os/agent/think",
        "/os/agents/preview": "/os/agent/plan",
        "/os/agents/submit": "/os/agent/submit",
    }
    fallback = mapping.get(endpoint)
    if not fallback:
        return None
    normalized_payload = dict(payload or {})
    normalized_payload.pop("agent_name", None)
    return fallback, normalized_payload


def local_request_json(endpoint: str, payload: dict | None = None, method: str | None = None) -> dict:
    runtime = get_local_os_runtime()
    data = dict(payload or {})
    prompt = data.get("prompt", "")
    context = data.get("context") or {}
    agent_name = data.get("agent_name", "auto")

    if method == "GET" and endpoint == "/os/tools":
        return {"tools": runtime.tools.as_dicts()}
    if method == "GET" and endpoint == "/os/status":
        status = runtime.status()
        return {
            "initialized": True,
            "components": {
                "tools": runtime.tools.as_dicts(),
                "models": status.get("models", {}),
                "scheduler": {"count": status.get("schedule_count", 0)},
                "skills_registry": {"count": status.get("skills", 0)},
                "supervisor": status.get("daemon", {}),
                "safety": status.get("policy", {}),
                "self_improvement": {"running": status.get("daemon", {}).get("running", False)},
                "world_model": {"memories": status.get("memory_items", 0), "goals": len(runtime.list_jobs().get("jobs", [])), "knowledge": 0, "experiences": 0},
                "learning": {"enabled": True, "student_agi_loaded": False},
                "browser": {"mode": "local"},
                "access_manager": {"grants": []},
                "mobile_sync": {"linked_devices": []},
                "gateway": {"channels": {}},
            },
        }
    if endpoint in {"/os/agents/preview", "/os/agent/plan"}:
        preview = runtime.preview_prompt(prompt, context=context, agent_name=agent_name)
        if asyncio.iscoroutine(preview):
            preview = _run_async(preview)
        preview["goal"] = _local_goal(prompt, context)
        return preview
    if endpoint in {"/os/agents/run", "/os/agent/think"}:
        result = runtime.handle_prompt(prompt, context=context, agent_name=agent_name)
        if asyncio.iscoroutine(result):
            result = _run_async(result)
        return _normalize_local_execution(result)
    if endpoint in {"/os/agents/submit", "/os/agent/submit"}:
        submission = runtime.submit_prompt(prompt, context=context, agent_name=agent_name)
        if asyncio.iscoroutine(submission):
            submission = _run_async(submission)
        preview = submission.get("preview", {})
        job = submission.get("job", {})
        return {
            "goal": _local_goal(prompt, context),
            "job_id": job.get("job_id", ""),
            "plan": preview.get("plan", {}),
            "analysis": preview.get("analysis", {}),
            "specialist": preview.get("specialist", {}),
        }
    if method == "GET" and endpoint.startswith("/os/executions/"):
        job_id = endpoint.rsplit("/", 1)[-1]
        job = runtime.get_job(job_id)
        if asyncio.iscoroutine(job):
            job = _run_async(job)
        result = job.get("result", {})
        if result:
            result = _normalize_local_execution(result)
            execution = result.get("execution", {})
            return {
                "job_id": job_id,
                "status": job.get("status", "missing"),
                "result": {
                    "summary": execution.get("summary", result.get("reply", "")),
                    "step_results": execution.get("step_results", []),
                },
            }
        return {"job_id": job_id, "status": job.get("status", "missing"), "error": job.get("error", "")}
    raise urllib.error.HTTPError(url=endpoint, code=404, msg="Not Found", hdrs=None, fp=None)


def request_json(base_url: str, endpoint: str, payload: dict | None = None, method: str | None = None) -> dict:
    global _legacy_route_notice_shown, _local_runtime_notice_shown
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}{endpoint}",
        data=data,
        headers={"Content-Type": "application/json"},
        method=method or ("POST" if data else "GET"),
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        fallback = legacy_endpoint_fallback(endpoint, payload)
        if exc.code == 404 and fallback:
            legacy_endpoint, legacy_payload = fallback
            if not _legacy_route_notice_shown:
                print("JARVIS > detected older backend routes; using compatibility mode.")
                _legacy_route_notice_shown = True
            result = request_json(base_url, legacy_endpoint, legacy_payload, method=method)
            if isinstance(result, dict):
                result.setdefault("_jarvis_compat", {})["fallback_endpoint"] = legacy_endpoint
            return result
        if endpoint.startswith("/os/") and exc.code == 404:
            if not _local_runtime_notice_shown:
                print("JARVIS > backend AI OS routes unavailable; using local JARVIS OS runtime.")
                _local_runtime_notice_shown = True
            return local_request_json(endpoint, payload, method=method or ("POST" if data else "GET"))
        raise
    except urllib.error.URLError:
        if endpoint.startswith("/os/"):
            if not _local_runtime_notice_shown:
                print("JARVIS > backend unreachable; using local JARVIS OS runtime.")
                _local_runtime_notice_shown = True
            return local_request_json(endpoint, payload, method=method or ("POST" if data else "GET"))
        raise


def poll_job(base_url: str, job_id: str, max_wait_s: int = 180) -> int:
    waited = 0
    while waited < max_wait_s:
        result = request_json(base_url, f"/os/executions/{job_id}", method="GET")
        status = result.get("status", "missing")
        if status in {"completed", "failed"}:
            print(f"Job status: {status}")
            payload = result.get("result", {})
            if payload:
                print(payload.get("summary", "No summary"))
                for step in payload.get("step_results", []):
                    mark = "ok" if step.get("success") else "fail"
                    detail = step.get("error") or step.get("tool")
                    print(f"  - {mark}: {detail}")
            elif result.get("error"):
                print(result["error"])
            return 0 if status == "completed" else 1
        if waited == 0:
            print("Running...")
        time.sleep(2)
        waited += 2
    print("Timed out waiting for job completion.")
    return 1


def poll_supervisor(base_url: str, build_id: str, max_wait_s: int = 3600) -> int:
    waited = 0
    last_status = ""
    while waited < max_wait_s:
        result = request_json(base_url, f"/api/supervisor/status/{build_id}", method="GET")
        status = result.get("status", "missing")
        if status in ("completed", "partial"):
            print(f"\nBuild complete! Status: {status}")
            completed = result.get("completed", [])
            failed = result.get("failed", [])
            print(f"  Tasks completed: {len(completed)}")
            if failed:
                print(f"  Tasks failed: {len(failed)}")
            return 0 if status == "completed" else 1
        if status == "cancelled":
            print("\nBuild cancelled.")
            return 1
        current = result.get("current_agent") or "idle"
        if current != last_status:
            print(f"[{current}] ", end="", flush=True)
            last_status = current
        else:
            print(".", end="", flush=True)
        time.sleep(3)
        waited += 3
    print("\nTimed out.")
    return 1


def stream_chat_ws(base_url: str, payload: dict) -> str:
    import asyncio
    try:
        ws_url = base_url.replace("http://", "ws://").replace("https://", "wss://")
        ws_url += "/ws/chat_stream"

        async def _stream():
            from websockets import connect
            full_reply = ""
            async with connect(ws_url) as ws:
                await ws.send(json.dumps(payload))
                while True:
                    msg = await ws.recv()
                    data = json.loads(msg)
                    if data.get("type") == "stream_token":
                        token = data.get("token", "")
                        print(token, end="", flush=True)
                        full_reply += token
                    elif data.get("type") == "stream_end":
                        print()
                        full_reply = data.get("full_response", full_reply)
                        break
                    elif data.get("type") == "error":
                        print(f"\n{colorize('[STREAM ERROR]', 'red')} {data.get('message', '')}")
                        break
            return full_reply

        return asyncio.run(_stream())
    except Exception as e:
        print(f"\n{colorize('[WS STREAM]', 'yellow')} falling back to POST: {e}")
        result = request_json(base_url, "/api/chat", payload)
        return extract_reply(result)


def extract_reply(result: dict) -> str:
    direct = result.get("response")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    execution = result.get("execution", {})
    for step in reversed(execution.get("step_results", [])):
        output = step.get("output")
        if isinstance(output, dict):
            for key in ("response", "reply", "summary", "speech", "output"):
                value = output.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
            if output.get("success") is False:
                error = output.get("error") or output.get("speech")
                if error:
                    return str(error)
        if isinstance(output, str) and output.strip():
            return output.strip()
        error = step.get("error")
        if error:
            return str(error)
    reflection = result.get("reflection", {})
    lessons = reflection.get("lessons", [])
    if lessons and not execution.get("success", False):
        return str(lessons[0])
    return execution.get("summary", "Request completed.")


def is_limited_mode_reply(reply: str) -> bool:
    lowered = reply.lower()
    return "limited mode" in lowered or "start ollama" in lowered or "ollama" in lowered and "full ai features" in lowered


def run_autonomy_cli(cli_args: list[str]) -> int:
    from cli_utils import python_exe, common_env, run_command
    from cli_server import ensure_server_running
    from cli_state import AUTONOMY_CLI, ROOT

    env = common_env()
    ensure_server_running(env.get("JARVIS_SERVER", "http://127.0.0.1:8000"))
    cmd = [python_exe(), str(AUTONOMY_CLI), *cli_args]
    return run_command(cmd, cwd=ROOT, env=env)
