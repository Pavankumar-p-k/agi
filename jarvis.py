#!/usr/bin/env python3
"""Unified JARVIS launcher for CLI, server, GUI, models, and IDE integrations."""

from __future__ import annotations

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import argparse
import asyncio
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
BACKEND = ROOT
APPS = ROOT / "apps" / "jarvis_app"
AUTONOMY_CLI = ROOT / "autonomy" / "cli" / "jarvis_cli.py"
STUDENT_MAIN = ROOT / "learning" / "student_agi" / "student_agi_main.py"

MODEL_PORTS = [
    ("tinyllama", 11434),
    ("deepseek-r1:1.5b", 11435),
    ("qwen2.5-coder:3b", 11436),
    ("qwen3:4b", 11437),
    ("qwen2.5:7b", 11438),
    ("mistral:7b", 11439),
    ("llama3.1:8b", 11440),
    ("phi3:mini", 11441),
    ("moondream", 11442),
]

_legacy_route_notice_shown = False
_local_runtime_notice_shown = False
_local_os_runtime = None

IDE_PRESETS = {
    "codex": "CLI-first workflow similar to Codex. Use JARVIS through terminal and HTTP APIs.",
    "vscode": "VS Code and forks can call JARVIS through local tasks, terminal profiles, and HTTP tools.",
    "cursor": "Cursor can reuse the same local CLI and HTTP endpoints as VS Code.",
    "windsurf": "Windsurf can connect through terminal tasks and local JARVIS APIs.",
    "zed": "Zed can use shell commands and OpenAPI/HTTP integrations against the JARVIS server.",
    "jetbrains": "JetBrains IDEs can use external tools and HTTP clients against the JARVIS server.",
}


def python_exe() -> str:
    candidates = [
        ROOT / ".venv" / "Scripts" / "python.exe",
        ROOT / ".venv311" / "Scripts" / "python.exe",
        ROOT / "venv" / "Scripts" / "python.exe",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return sys.executable


def common_env() -> dict:
    env = os.environ.copy()
    env.setdefault("PYTHONPATH", str(ROOT))
    env.setdefault("JARVIS_SERVER", "http://127.0.0.1:8000")
    env.setdefault("OLLAMA_URL", "http://127.0.0.1:11434")
    env.setdefault("JARVIS_AUTO_MODELS", "single")
    return env


def run_command(cmd: list[str], cwd: Path | None = None, env: dict | None = None, dry_run: bool = False) -> int:
    cmd = prepare_command(cmd)
    if dry_run:
        print("DRY RUN:", " ".join(cmd))
        if cwd:
            print("CWD:", cwd)
        return 0
    return subprocess.run(cmd, cwd=str(cwd) if cwd else None, env=env).returncode


def spawn_background(
    title: str,
    cmd: list[str],
    cwd: Path | None = None,
    env: dict | None = None,
    dry_run: bool = False,
) -> int:
    cmd = prepare_command(cmd)
    if dry_run:
        print(f"DRY RUN [{title}]:", " ".join(cmd))
        if cwd:
            print("CWD:", cwd)
        return 0
    popen_kwargs = {
        "cwd": str(cwd) if cwd else None,
        "env": env,
    }
    if os.name == "nt":
        popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
    subprocess.Popen(cmd, **popen_kwargs)
    return 0


def prepare_command(cmd: list[str]) -> list[str]:
    if not cmd:
        raise ValueError("Command cannot be empty")
    if os.name != "nt":
        return cmd

    executable = shutil.which(cmd[0]) or cmd[0]
    if Path(executable).suffix.lower() in {".bat", ".cmd"}:
        return ["cmd.exe", "/c", executable, *cmd[1:]]
    return [executable, *cmd[1:]]


def run_autonomy_cli(cli_args: list[str]) -> int:
    env = common_env()
    ensure_server_running(env.get("JARVIS_SERVER", "http://127.0.0.1:8000"))
    cmd = [python_exe(), str(AUTONOMY_CLI), *cli_args]
    return run_command(cmd, cwd=ROOT, env=env)


def cmd_cli(args: argparse.Namespace) -> int:
    env = common_env()
    base_url = env.get("JARVIS_SERVER", "http://127.0.0.1:8000")
    ensure_local_stack_running(env)
    mode = "agent"
    print()
    print("+----------------------------------------------+")
    print("|  JARVIS AI OS - Interactive Chat             |")
    print("|  /plan /goal /develop /tools /mode          |")
    print("|  Type 'exit' to quit                         |")
    print("+----------------------------------------------+")
    print()
    while True:
        try:
            text = input("You > ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye.")
            return 0
        if not text:
            continue
        if text.lower() in {"exit", "quit", "bye"}:
            return 0
        if text.startswith("/"):
            command_status = handle_cli_slash_command(text, args, env, base_url, mode)
            if command_status == "handled":
                if text.lower().startswith("/mode "):
                    mode = text.split(None, 1)[1].strip().lower()
                continue
            if command_status == "exit":
                return 0
            continue
        try:
            context = build_cli_context(text)
            context["cli_mode"] = mode
            if mode == "agent" and is_agentic_prompt(text):
                preview = request_json(
                    base_url,
                    "/os/agents/preview",
                    {"prompt": text, "agent_name": "auto", "context": context},
                )
                print_plan_preview(preview)
            endpoint = "/os/agents/run" if mode == "agent" else "/os/agent/think"
            payload = {"prompt": text, "context": context}
            if mode == "agent":
                payload["agent_name"] = "auto"
            result = request_json(base_url, endpoint, payload)
            reply = extract_reply(result)
            if is_limited_mode_reply(reply):
                ensure_ollama_running(env)
                context["retry_after_model_boot"] = True
                result = request_json(base_url, endpoint, payload)
                reply = extract_reply(result)
            print(f"JARVIS > {reply}")
            specialist = result.get("specialist", {}).get("name")
            if specialist:
                print(f"        [agent={specialist}]")
            print(f"        [{result.get('latency_ms', 0)} ms]")
        except Exception as exc:
            print(f"JARVIS > request failed: {exc}")


def handle_cli_slash_command(
    text: str,
    args: argparse.Namespace,
    env: dict,
    base_url: str,
    mode: str,
) -> str:
    lowered = text.lower().strip()
    if lowered in {"/status", "/s"}:
        cmd_status(args)
        return "handled"
    if lowered in {"/help", "/h", "/?"}:
        print("Commands: /status /tools /plan <goal> /goal <goal> /develop <goal> /mode <chat|agent>")
        return "handled"
    if lowered == "/tools":
        result = request_json(base_url, "/os/tools", method="GET")
        tools = [tool.get("name", "") for tool in result.get("tools", [])]
        print("Tools:", ", ".join(sorted(name for name in tools if name)))
        return "handled"
    if lowered.startswith("/mode "):
        target = text.split(None, 1)[1].strip().lower()
        if target not in {"chat", "agent"}:
            print("JARVIS > mode must be 'chat' or 'agent'.")
            return "handled"
        print(f"JARVIS > CLI mode set to {target}.")
        return "handled"
    if lowered.startswith("/plan "):
        prompt = text.split(None, 1)[1].strip()
        context = build_cli_context(prompt)
        context["cli_mode"] = mode
        endpoint = "/os/agents/preview" if mode == "agent" else "/os/agent/plan"
        payload = {"prompt": prompt, "context": context}
        if mode == "agent":
            payload["agent_name"] = "auto"
        preview = request_json(base_url, endpoint, payload)
        specialist = preview.get("specialist", {}).get("name")
        if specialist:
            print(f"Agent: {specialist}")
        print_plan_preview(preview)
        return "handled"
    if lowered.startswith("/goal "):
        prompt = text.split(None, 1)[1].strip()
        context = build_cli_context(prompt)
        context["cli_mode"] = mode
        endpoint = "/os/agents/submit" if mode == "agent" else "/os/agent/submit"
        payload = {"prompt": prompt, "context": context}
        if mode == "agent":
            payload["agent_name"] = "auto"
        result = request_json(base_url, endpoint, payload)
        specialist = result.get("specialist", {}).get("name")
        if specialist:
            print(f"Agent: {specialist}")
        print(f"JARVIS > queued goal {result['goal']['goal_id']} as job {result['job_id']}")
        print_plan_preview(result)
        return "handled"
    if lowered.startswith("/develop "):
        prompt = text.split(None, 1)[1].strip()
        context = build_cli_context(prompt)
        context["cli_mode"] = mode
        endpoint = "/os/agents/submit" if mode == "agent" else "/os/agent/submit"
        payload = {"prompt": prompt, "context": context}
        if mode == "agent":
            payload["agent_name"] = "auto"
        result = request_json(base_url, endpoint, payload)
        specialist = result.get("specialist", {}).get("name")
        if specialist:
            print(f"Agent: {specialist}")
        print(f"JARVIS > starting development goal {result['goal']['goal_id']}")
        print_plan_preview(result)
        poll_job(base_url, result["job_id"])
        return "handled"
    if lowered.startswith("/vision "):
        prompt = text.split(None, 1)[1].strip()
        context = build_cli_context(prompt)
        context["intent"] = "vision"
        context["cli_mode"] = mode
        result = request_json(base_url, "/os/agent/think", {"prompt": prompt, "context": context})
        print(f"JARVIS > {extract_reply(result)}")
        return "handled"
    return "ignored"


def cmd_autonomy_passthrough(args: argparse.Namespace) -> int:
    tail = getattr(args, "text", None) or getattr(args, "query", None) or []
    if isinstance(tail, list):
        return run_autonomy_cli([args.command, *tail])
    return run_autonomy_cli([args.command, str(tail)])


def cmd_status(args: argparse.Namespace) -> int:
    env = common_env()
    base_url = env.get("JARVIS_SERVER", "http://127.0.0.1:8000")
    ensure_local_stack_running(env)
    try:
        result = request_json(base_url, "/os/status", method="GET")
    except Exception as exc:
        print(f"Status request failed: {exc}")
        return 1

    components = result.get("components", {})
    world = components.get("world_model", {})
    learning = components.get("learning", {})
    tools = components.get("tools", [])
    models = components.get("models", {})
    browser = components.get("browser", {})
    skills_registry = components.get("skills_registry", {})
    supervisor = components.get("supervisor", {})
    access_manager = components.get("access_manager", {})
    mobile_sync = components.get("mobile_sync", {})
    scheduler = components.get("scheduler", {})
    gateway = components.get("gateway", {})
    safety = components.get("safety", {})
    self_improvement = components.get("self_improvement", {})

    print()
    print("JARVIS AI OS STATUS")
    print("-------------------")
    print(f"Initialized:        {result.get('initialized', False)}")
    print(f"World memories:     {world.get('memories', 0)}")
    print(f"Tracked goals:      {world.get('goals', 0)}")
    print(f"Knowledge facts:    {world.get('knowledge', 0)}")
    print(f"Experiences:        {world.get('experiences', 0)}")
    print(f"Tools registered:   {len(tools)}")
    print(f"Learning enabled:   {learning.get('enabled', False)}")
    print(f"Student AGI loaded: {learning.get('student_agi_loaded', False)}")
    print(f"Models ready:       {models.get('ready', False)}")
    print(f"Browser mode:       {browser.get('mode', 'unknown')}")
    print(f"Skill registry:     {skills_registry.get('count', 0)} skill(s)")
    print(f"Supervisor queued:  {supervisor.get('queued', 0)}")
    print(f"Access profiles:    {len(access_manager.get('grants', []))}")
    print(f"Mobile devices:     {len(mobile_sync.get('linked_devices', []))}")
    print(f"Heartbeat jobs:     {scheduler.get('count', 0)}")
    print(f"Channels online:    {sum(1 for channel in gateway.get('channels', {}).values() if channel.get('enabled'))}")
    ollama_ready = is_ollama_reachable(env)
    print(f"Safety strict:      {safety.get('strict_mode', False)}")
    print(f"Self-improve loop:  {self_improvement.get('running', False)}")
    print(f"Ollama ready:       {ollama_ready}")
    if not ollama_ready:
        print("Ollama info:        unavailable; local/fallback mode is enabled.")
    return 0


def cmd_goal(args: argparse.Namespace) -> int:
    prompt = " ".join(args.text).strip()
    if not prompt:
        print("Usage: jarvis goal <prompt>")
        return 1
    env = common_env()
    base_url = env.get("JARVIS_SERVER", "http://127.0.0.1:8000")
    ensure_local_stack_running(env)
    context = build_cli_context(prompt)
    context["cli_mode"] = "agent"
    result = request_json(base_url, "/os/agents/submit", {"prompt": prompt, "agent_name": "auto", "context": context})
    print()
    specialist = result.get("specialist", {}).get("name")
    if specialist:
        print(f"Agent:   {specialist}")
    print(f"Goal ID: {result['goal']['goal_id']}")
    print(f"Job ID:  {result['job_id']}")
    print("Plan:")
    for index, step in enumerate(result["plan"]["steps"], start=1):
        print(f"  {index}. [{step['tool']}] {step['action']}")
    return 0


def cmd_plan_preview(args: argparse.Namespace) -> int:
    prompt = " ".join(args.text).strip()
    if not prompt:
        print("Usage: jarvis plan <prompt>")
        return 1
    env = common_env()
    base_url = env.get("JARVIS_SERVER", "http://127.0.0.1:8000")
    ensure_local_stack_running(env)
    context = build_cli_context(prompt)
    context["cli_mode"] = "agent"
    result = request_json(base_url, "/os/agents/preview", {"prompt": prompt, "agent_name": "auto", "context": context})
    print()
    specialist = result.get("specialist", {}).get("name")
    if specialist:
        print(f"Agent:   {specialist}")
    print(f"Goal ID: {result['goal']['goal_id']}")
    print(f"Intent:  {result['analysis'].get('intent', 'unknown')}")
    print("Plan:")
    for index, step in enumerate(result["plan"]["steps"], start=1):
        print(f"  {index}. [{step['tool']}] {step['action']}")
    return 0


def cmd_develop(args: argparse.Namespace) -> int:
    prompt = " ".join(args.text).strip()
    if not prompt:
        print("Usage: jarvis develop <prompt>")
        return 1
    env = common_env()
    base_url = env.get("JARVIS_SERVER", "http://127.0.0.1:8000")
    ensure_local_stack_running(env)
    context = build_cli_context(prompt)
    context["cli_mode"] = "agent"
    result = request_json(base_url, "/os/agents/submit", {"prompt": prompt, "agent_name": "auto", "context": context})
    job_id = result["job_id"]
    specialist = result.get("specialist", {}).get("name")
    if specialist:
        print(f"Agent: {specialist}")
    print(f"Started goal {result['goal']['goal_id']} as job {job_id}")
    print("Plan:")
    for index, step in enumerate(result["plan"]["steps"], start=1):
        print(f"  {index}. [{step['tool']}] {step['action']}")
    print()
    return poll_job(base_url, job_id)


def backend_server_cmd(host: str, port: int, reload_enabled: bool) -> list[str]:
    code = (
        "import sys, uvicorn; "
        "getattr(sys.stdout, 'reconfigure', lambda **kwargs: None)(encoding='utf-8', errors='replace'); "
        "getattr(sys.stderr, 'reconfigure', lambda **kwargs: None)(encoding='utf-8', errors='replace'); "
        f"uvicorn.run('core.main:app', host='{host}', port={port}, reload={str(reload_enabled)})"
    )
    return [python_exe(), "-c", code]


def parse_server_location(base_url: str) -> tuple[str, int]:
    parsed = urlparse(base_url if "://" in base_url else f"http://{base_url}")
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return host, port


def is_port_open(host: str, port: int, timeout: float = 0.3) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def is_server_reachable(base_url: str, timeout: float = 1.0) -> bool:
    host, port = parse_server_location(base_url)
    if not is_port_open(host, port, timeout=min(timeout, 0.3)):
        return False
    for endpoint in ("/health", "/os/status", "/"):
        try:
            request = urllib.request.Request(
                f"{base_url.rstrip('/')}{endpoint}",
                headers={"Connection": "close", "User-Agent": "JARVIS-Launcher"},
            )
            with urllib.request.urlopen(request, timeout=timeout) as response:
                if getattr(response, "status", 200) < 500:
                    return True
        except (urllib.error.URLError, TimeoutError, OSError):
            continue
        except Exception:
            continue
    return False


def wait_for_server(base_url: str, attempts: int = 30, interval_s: float = 1.0) -> bool:
    for _ in range(attempts):
        time.sleep(interval_s)
        if is_server_reachable(base_url, timeout=0.5):
            return True
    return False


def ensure_server_running(base_url: str, host: str = "127.0.0.1", port: int = 8000):
    target_host, target_port = parse_server_location(base_url)
    if target_host not in {"127.0.0.1", "localhost"}:
        return
    if is_server_reachable(base_url, timeout=0.5):
        return
    print("JARVIS backend is not running. Starting local server...")
    env = common_env()
    spawn_background(
        "JARVIS-Server",
        backend_server_cmd(target_host or host, target_port or port, False),
        cwd=ROOT,
        env=env,
        dry_run=False,
    )
    if wait_for_server(base_url):
        print(f"JARVIS backend ready at {base_url}")
        return
    print(f"JARVIS backend did not become ready at {base_url}")


def ollama_base_url(env: dict) -> str:
    return env.get("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")


def is_ollama_reachable(env: dict, timeout: float = 1.0) -> bool:
    base_url = ollama_base_url(env)
    try:
        with urllib.request.urlopen(f"{base_url}/api/tags", timeout=timeout):
            return True
    except Exception:
        return False


def ensure_ollama_running(env: dict):
    auto_models = env.get("JARVIS_AUTO_MODELS", "single").lower()
    if auto_models == "multi" or env.get("OLLAMA_MULTI_INSTANCE", "").lower() in {"1", "true", "yes", "on"}:
        for model, port in MODEL_PORTS:
            model_env = env.copy()
            model_env.update(
                {
                    "OLLAMA_HOST": f"127.0.0.1:{port}",
                    "OLLAMA_NUM_GPU": model_env.get("OLLAMA_NUM_GPU", "99"),
                    "OLLAMA_KEEP_ALIVE": model_env.get("OLLAMA_KEEP_ALIVE", "300"),
                    "OLLAMA_NUM_PARALLEL": model_env.get("OLLAMA_NUM_PARALLEL", "1"),
                    "OLLAMA_FLASH_ATTENTION": model_env.get("OLLAMA_FLASH_ATTENTION", "1"),
                    "OLLAMA_KV_CACHE_TYPE": model_env.get("OLLAMA_KV_CACHE_TYPE", "q8_0"),
                    "OLLAMA_MAX_LOADED_MODELS": model_env.get("OLLAMA_MAX_LOADED_MODELS", "1"),
                    "CUDA_VISIBLE_DEVICES": model_env.get("CUDA_VISIBLE_DEVICES", "0"),
                }
            )
            url = f"http://127.0.0.1:{port}"
            try:
                with urllib.request.urlopen(f"{url}/api/tags", timeout=1.0):
                    continue
            except Exception:
                print(f"Starting Ollama model endpoint for {model} on {port}...")
                spawn_background(f"Ollama-{model}", ["ollama", "serve"], cwd=ROOT, env=model_env, dry_run=False)
        env["OLLAMA_MULTI_INSTANCE"] = "1"
        env["OLLAMA_MODEL_ENDPOINTS"] = ";".join(f"{model}=http://127.0.0.1:{port}" for model, port in MODEL_PORTS)
        time.sleep(2)
        return

    if is_ollama_reachable(env):
        return
    print("Ollama is not running. Starting local model server...")
    spawn_background("Ollama", ["ollama", "serve"], cwd=ROOT, env=env, dry_run=False)
    for _ in range(20):
        time.sleep(1)
        if is_ollama_reachable(env):
            print(f"Ollama ready at {ollama_base_url(env)}")
            return
    print(f"Ollama did not become ready at {ollama_base_url(env)}")


def wait_for_ollama_ready(timeout_s: int = 30) -> bool:
    """Wait for Ollama to be reachable, with timeout."""
    for _ in range(timeout_s):
        if is_ollama_reachable({}):
            return True
        time.sleep(1)
    return False


def ensure_local_stack_running(env: dict):
    ensure_ollama_running(env)
    ensure_server_running(env.get("JARVIS_SERVER", "http://127.0.0.1:8000"))


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


def get_local_os_runtime():
    global _local_os_runtime
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    if _local_os_runtime is None:
        from jarvis_os.bootstrap import build_jarvis_os
        
        _local_os_runtime = build_jarvis_os()
    return _local_os_runtime


def _run_async(coro):
    """Run a coroutine synchronously from sync code."""
    import concurrent.futures
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


def local_request_json(endpoint: str, payload: dict | None = None, method: str | None = None) -> dict:
    runtime = get_local_os_runtime()
    data = dict(payload or {})
    prompt = data.get("prompt", "")
    context = data.get("context") or {}
    agent_name = data.get("agent_name", "auto")

    if method == "GET" and endpoint == "/os/tools":
        return {"tools": runtime.tools.catalog()}
    if method == "GET" and endpoint == "/os/status":
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
            return _run_async(local_request_json(endpoint, payload, method=method or ("POST" if data else "GET")))
        raise
    except urllib.error.URLError:
        if endpoint.startswith("/os/"):
            if not _local_runtime_notice_shown:
                print("JARVIS > backend unreachable; using local JARVIS OS runtime.")
                _local_runtime_notice_shown = True
            return _run_async(local_request_json(endpoint, payload, method=method or ("POST" if data else "GET")))
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


def build_cli_context(prompt: str) -> dict:
    cwd = Path.cwd().resolve()
    context = {
        "platform": "cli",
        "cwd": str(cwd),
        "workspace_root": str(cwd),
        "approved": True,
        "local_only": os.getenv("JARVIS_LOCAL_ONLY", "1").lower() not in {"0", "false", "no"},
    }
    lowered = prompt.lower()
    if any(
        token in lowered
        for token in ("project", "repo", "repository", "codebase", "review", "architecture", "develop", "build", "implement", "fix", "debug")
    ):
        context["workspace_summary"] = workspace_snapshot(cwd)
    return context


def is_agentic_prompt(prompt: str) -> bool:
    lowered = prompt.lower()
    triggers = (
        "open ",
        "launch ",
        "review ",
        "analyze ",
        "understand ",
        "inspect ",
        "build ",
        "develop ",
        "implement ",
        "create ",
        "fix ",
        "debug ",
        "plan ",
        "search ",
        "send ",
        "vision ",
        "look at ",
        "read ",
        "list ",
    )
    return any(token in lowered for token in triggers)


def print_plan_preview(result: dict):
    plan = result.get("plan", {})
    analysis = result.get("analysis", {})
    steps = plan.get("steps", [])
    if not steps:
        return
    print("Plan:")
    intent = analysis.get("intent")
    if intent:
        print(f"  intent: {intent}")
    for index, step in enumerate(steps, start=1):
        print(f"  {index}. [{step.get('tool', 'unknown')}] {step.get('action', '')}")


def workspace_snapshot(root: Path) -> str:
    manifest_names = ["pyproject.toml", "requirements.txt", "package.json", "pubspec.yaml", "README.md", "setup.py"]
    manifests = [name for name in manifest_names if (root / name).exists()]
    top_entries = []
    try:
        entries = sorted(root.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower()))
        for entry in entries[:12]:
            top_entries.append(entry.name + ("/" if entry.is_dir() else ""))
    except Exception as err:
        import logging
        logging.getLogger(__name__).error("workspace_snapshot error: %s", err, exc_info=True)
        raise
    readme_excerpt = ""
    readme = root / "README.md"
    if readme.exists():
        try:
            readme_excerpt = readme.read_text(encoding="utf-8", errors="replace")[:400].replace("\n", " ").strip()
        except Exception:
            readme_excerpt = ""
    return (
        f"Workspace root: {root}. "
        f"Top-level entries: {', '.join(top_entries) or 'none'}. "
        f"Manifests: {', '.join(manifests) or 'none'}. "
        f"README: {readme_excerpt or 'not available'}"
    )


def cmd_server(args: argparse.Namespace) -> int:
    if args.multi_model:
        for model, port in MODEL_PORTS:
            env = common_env()
            env.update(
                {
                    "OLLAMA_HOST": f"127.0.0.1:{port}",
                    "OLLAMA_NUM_GPU": env.get("OLLAMA_NUM_GPU", "99"),
                    "OLLAMA_KEEP_ALIVE": env.get("OLLAMA_KEEP_ALIVE", "300"),
                    "OLLAMA_NUM_PARALLEL": env.get("OLLAMA_NUM_PARALLEL", "1"),
                    "OLLAMA_FLASH_ATTENTION": env.get("OLLAMA_FLASH_ATTENTION", "1"),
                    "OLLAMA_KV_CACHE_TYPE": env.get("OLLAMA_KV_CACHE_TYPE", "q8_0"),
                    "OLLAMA_MAX_LOADED_MODELS": env.get("OLLAMA_MAX_LOADED_MODELS", "1"),
                    "CUDA_VISIBLE_DEVICES": env.get("CUDA_VISIBLE_DEVICES", "0"),
                }
            )
            spawn_background(f"Ollama-{model}", ["ollama", "serve"], cwd=ROOT, env=env, dry_run=args.dry_run)
        if not args.dry_run:
            time.sleep(2)

    env = common_env()
    if args.multi_model:
        env["OLLAMA_MULTI_INSTANCE"] = "1"
        env["OLLAMA_MODEL_ENDPOINTS"] = ";".join(f"{model}=http://127.0.0.1:{port}" for model, port in MODEL_PORTS)
    return run_command(
        backend_server_cmd(args.host, args.port, not args.no_reload),
        cwd=BACKEND,
        env=env,
        dry_run=args.dry_run,
    )


def cmd_restart(args: argparse.Namespace) -> int:
    stop_local_services(include_ollama=args.with_models)

    time.sleep(2)
    server_args = argparse.Namespace(
        multi_model=args.multi_model,
        host=args.host,
        port=args.port,
        no_reload=args.no_reload,
        dry_run=args.dry_run,
    )
    return cmd_server(server_args)


def stop_local_services(include_ollama: bool = False):
    if os.name == "nt":
        python_filter = (
            "Get-CimInstance Win32_Process | "
            "Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -match 'core\\.main:app' } | "
            "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
        )
        subprocess.run(["powershell", "-NoProfile", "-Command", python_filter], capture_output=True, text=True)
        if include_ollama:
            ollama_filter = (
                "Get-CimInstance Win32_Process | "
                "Where-Object { $_.Name -eq 'ollama.exe' } | "
                "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
            )
            subprocess.run(["powershell", "-NoProfile", "-Command", ollama_filter], capture_output=True, text=True)
        return

    subprocess.run(["pkill", "-f", "core.main:app"], capture_output=True, text=True)
    if include_ollama:
        subprocess.run(["pkill", "-f", "ollama serve"], capture_output=True, text=True)


def cmd_gui(args: argparse.Namespace) -> int:
    api_url = args.api_url or f"http://{args.host}:{args.port}"
    ws_url = args.ws_url or f"ws://{args.host}:{args.port}/ws"
    cmd = [
        "flutter",
        "run",
        "-d",
        args.device,
        f"--dart-define=API_BASE_URL={api_url}",
        f"--dart-define=WS_URL={ws_url}",
    ]
    return run_command(cmd, cwd=APPS, env=common_env(), dry_run=args.dry_run)


def cmd_up(args: argparse.Namespace) -> int:
    server_args = argparse.Namespace(
        multi_model=args.multi_model,
        host=args.host,
        port=args.port,
        no_reload=args.no_reload,
        dry_run=args.dry_run,
    )
    gui_args = argparse.Namespace(
        api_url=args.api_url,
        ws_url=args.ws_url,
        host=args.host,
        port=args.port,
        device=args.device,
        dry_run=args.dry_run,
    )

    if args.background:
        env = common_env()
        if args.multi_model:
            env["OLLAMA_MULTI_INSTANCE"] = "1"
            env["OLLAMA_MODEL_ENDPOINTS"] = ";".join(f"{model}=http://127.0.0.1:{port}" for model, port in MODEL_PORTS)
            for model, port in MODEL_PORTS:
                ollama_env = env.copy()
                ollama_env["OLLAMA_HOST"] = f"127.0.0.1:{port}"
                spawn_background(f"Ollama-{model}", ["ollama", "serve"], cwd=ROOT, env=ollama_env, dry_run=args.dry_run)
        spawn_background(
            "JARVIS-Server",
            backend_server_cmd(args.host, args.port, not args.no_reload),
            cwd=BACKEND,
            env=env,
            dry_run=args.dry_run,
        )
        return spawn_background(
            "JARVIS-GUI",
            [
                "flutter",
                "run",
                "-d",
                args.device,
                f"--dart-define=API_BASE_URL={args.api_url or f'http://{args.host}:{args.port}'}",
                f"--dart-define=WS_URL={args.ws_url or f'ws://{args.host}:{args.port}/ws'}",
            ],
            cwd=APPS,
            env=common_env(),
            dry_run=args.dry_run,
        )

    code = cmd_server(server_args)
    if code != 0:
        return code
    return cmd_gui(gui_args)


def cmd_student(args: argparse.Namespace) -> int:
    cmd = [python_exe(), str(STUDENT_MAIN), *args.forward]
    return run_command(cmd, cwd=ROOT, env=common_env(), dry_run=args.dry_run)


def cmd_models(args: argparse.Namespace) -> int:
    if args.models_command == "list":
        for model, port in MODEL_PORTS:
            print(f"{model:18} http://127.0.0.1:{port}")
        return 0
    if args.models_command == "start":
        server_args = argparse.Namespace(
            multi_model=True,
            host=args.host,
            port=args.port,
            no_reload=args.no_reload,
            dry_run=args.dry_run,
        )
        return cmd_server(server_args)
    return 0


def cmd_extension(args: argparse.Namespace) -> int:
    if args.extension_command == "list":
        for name, description in IDE_PRESETS.items():
            print(f"{name:10} {description}")
        return 0

    ide = args.ide.lower()
    description = IDE_PRESETS.get(ide, "Generic IDE integration preset.")
    host = args.host
    port = args.port
    api_url = f"http://{host}:{port}"
    print(f"IDE preset: {ide}")
    print(description)
    print()
    print("Recommended commands:")
    print("  jarvis server")
    print("  jarvis server /m")
    print("  jarvis gui")
    print("  jarvis cli")
    print()
    print("Useful endpoints:")
    print(f"  API root:        {api_url}")
    print(f"  AI OS:           {api_url}/os")
    print(f"  Autonomy:        {api_url}/autonomy")
    print(f"  Docs:            {api_url}/docs")
    print()
    print("Environment variables:")
    print(f"  JARVIS_SERVER={api_url}")
    print("  JARVIS_AUTONOMY_PREFIX=/autonomy")
    print("  JARVIS_OS_PREFIX=/os")
    return 0


def cmd_os(args: argparse.Namespace) -> int:
    cmd = [python_exe(), "-m", "jarvis_os.interface.cli", *args.text]
    if args.agent:
        cmd.extend(["--agent", args.agent])
    if args.as_json:
        cmd.append("--json")
    if args.tools:
        cmd.append("--tools")
    if args.memory_view:
        cmd.append("--memory")
    if args.status:
        cmd.append("--status")
    if args.jobs:
        cmd.append("--jobs")
    if args.skills:
        cmd.append("--skills")
    if args.schedules:
        cmd.append("--schedules")
    if args.telemetry:
        cmd.append("--telemetry")
    if args.daemon_status:
        cmd.append("--daemon-status")
    if args.daemon_start:
        cmd.append("--daemon-start")
    if args.daemon_stop:
        cmd.append("--daemon-stop")
    if args.daemon_tick:
        cmd.append("--daemon-tick")
    if args.submit:
        cmd.append("--submit")
    if args.preview:
        cmd.append("--preview")
    if args.run_skill:
        cmd.extend(["--run-skill", args.run_skill])
    if args.show_skill:
        cmd.extend(["--show-skill", args.show_skill])
    if args.run_due:
        cmd.append("--run-due")
    return run_command(cmd, cwd=ROOT, env=common_env(), dry_run=getattr(args, "dry_run", False))


def cmd_cognitive(args: argparse.Namespace) -> int:
    cmd = [python_exe(), "-m", "cognitive_agent.main", *args.forward]
    return run_command(cmd, cwd=BACKEND, env=common_env(), dry_run=getattr(args, "dry_run", False))


def extract_reply(result: dict) -> str:
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jarvis",
        description="Unified JARVIS launcher for CLI, server, GUI, models, and IDE integrations.",
        prefix_chars="-/",
    )
    subparsers = parser.add_subparsers(dest="subcommand")

    cli_parser = subparsers.add_parser("cli", help="Start the interactive JARVIS terminal chat.", prefix_chars="-/")
    cli_parser.set_defaults(func=cmd_cli)

    goal = subparsers.add_parser("goal", help="Create an AI OS goal and submit it asynchronously.", prefix_chars="-/")
    goal.add_argument("text", nargs=argparse.REMAINDER)
    goal.set_defaults(func=cmd_goal)

    develop = subparsers.add_parser("develop", help="Submit a development goal and follow execution.", prefix_chars="-/")
    develop.add_argument("text", nargs=argparse.REMAINDER)
    develop.set_defaults(func=cmd_develop)

    for name in ("think", "run", "exec"):
        sub = subparsers.add_parser(name, help=f"Forward '{name}' to the autonomous CLI.", prefix_chars="-/")
        sub.add_argument("text", nargs=argparse.REMAINDER)
        sub.set_defaults(func=cmd_autonomy_passthrough, command=name)

    plan = subparsers.add_parser("plan", help="Preview an AI OS execution plan.", prefix_chars="-/")
    plan.add_argument("text", nargs=argparse.REMAINDER)
    plan.set_defaults(func=cmd_plan_preview)

    memory = subparsers.add_parser("memory", help="Search autonomous memory from terminal.", prefix_chars="-/")
    memory.add_argument("query", nargs=argparse.REMAINDER)
    memory.set_defaults(func=cmd_autonomy_passthrough, command="memory")

    logs = subparsers.add_parser("logs", help="Show recent autonomous execution logs.", prefix_chars="-/")
    logs.add_argument("text", nargs=argparse.REMAINDER)
    logs.set_defaults(func=cmd_autonomy_passthrough, command="logs")

    os_cli = subparsers.add_parser("os", help="Run the new phase-based JARVIS OS CLI.", prefix_chars="-/")
    os_cli.add_argument("text", nargs=argparse.REMAINDER)
    os_cli.add_argument("--agent", default="auto")
    os_cli.add_argument("--json", action="store_true", dest="as_json")
    os_cli.add_argument("--tools", action="store_true")
    os_cli.add_argument("--memory", action="store_true", dest="memory_view")
    os_cli.add_argument("--status", action="store_true")
    os_cli.add_argument("--jobs", action="store_true")
    os_cli.add_argument("--skills", action="store_true")
    os_cli.add_argument("--schedules", action="store_true")
    os_cli.add_argument("--telemetry", action="store_true")
    os_cli.add_argument("--daemon-status", action="store_true")
    os_cli.add_argument("--daemon-start", action="store_true")
    os_cli.add_argument("--daemon-stop", action="store_true")
    os_cli.add_argument("--daemon-tick", action="store_true")
    os_cli.add_argument("--submit", action="store_true")
    os_cli.add_argument("--preview", action="store_true")
    os_cli.add_argument("--run-skill", default="")
    os_cli.add_argument("--show-skill", default="")
    os_cli.add_argument("--run-due", action="store_true")
    os_cli.add_argument("--dry-run", action="store_true")
    os_cli.set_defaults(func=cmd_os)

    cognitive = subparsers.add_parser("cognitive", help="Run the extracted cognitive agent package.", prefix_chars="-/")
    cognitive.add_argument("forward", nargs=argparse.REMAINDER)
    cognitive.add_argument("--dry-run", action="store_true")
    cognitive.set_defaults(func=cmd_cognitive)

    chat = subparsers.add_parser("chat", help="Alias for 'jarvis cli'.", prefix_chars="-/")
    chat.set_defaults(func=cmd_cli)

    status = subparsers.add_parser("status", help="Show current JARVIS autonomous status.", prefix_chars="-/")
    status.set_defaults(func=cmd_status)

    server = subparsers.add_parser("server", help="Start the FastAPI backend server.", prefix_chars="-/")
    server.add_argument("/m", "--multi-model", action="store_true", dest="multi_model", help="Start multi-model Ollama servers before backend.")
    server.add_argument("--host", default="0.0.0.0")
    server.add_argument("--port", type=int, default=8000)
    server.add_argument("--no-reload", action="store_true", help="Disable auto-reload.")
    server.add_argument("--dry-run", action="store_true", help="Print commands instead of executing them.")
    server.set_defaults(func=cmd_server)

    restart = subparsers.add_parser("restart", help="Restart the local backend stack.", prefix_chars="-/")
    restart.add_argument("/m", "--multi-model", action="store_true", dest="multi_model", help="Restart with multi-model Ollama endpoints.")
    restart.add_argument("--with-models", action="store_true", help="Stop existing Ollama processes before restart.")
    restart.add_argument("--host", default="0.0.0.0")
    restart.add_argument("--port", type=int, default=8000)
    restart.add_argument("--no-reload", action="store_true", help="Disable auto-reload after restart.")
    restart.add_argument("--dry-run", action="store_true", help="Print commands instead of executing them.")
    restart.set_defaults(func=cmd_restart)

    gui = subparsers.add_parser("gui", help="Start the Flutter Windows GUI.", prefix_chars="-/")
    gui.add_argument("--device", default="windows")
    gui.add_argument("--host", default="127.0.0.1")
    gui.add_argument("--port", type=int, default=8000)
    gui.add_argument("--api-url")
    gui.add_argument("--ws-url")
    gui.add_argument("--dry-run", action="store_true")
    gui.set_defaults(func=cmd_gui)

    up = subparsers.add_parser("up", help="Start JARVIS desktop stack (server + GUI).", prefix_chars="-/")
    up.add_argument("/m", "--multi-model", action="store_true", dest="multi_model", help="Start multi-model Ollama servers too.")
    up.add_argument("--background", action="store_true", help="Spawn server and GUI in separate windows.")
    up.add_argument("--host", default="127.0.0.1")
    up.add_argument("--port", type=int, default=8000)
    up.add_argument("--device", default="windows")
    up.add_argument("--api-url")
    up.add_argument("--ws-url")
    up.add_argument("--no-reload", action="store_true")
    up.add_argument("--dry-run", action="store_true")
    up.set_defaults(func=cmd_up)

    student = subparsers.add_parser("student", help="Run the Student AGI service or commands.", prefix_chars="-/")
    student.add_argument("forward", nargs=argparse.REMAINDER)
    student.add_argument("--dry-run", action="store_true")
    student.set_defaults(func=cmd_student)

    models = subparsers.add_parser("models", help="List or start configured model servers.", prefix_chars="-/")
    models_sub = models.add_subparsers(dest="models_command")
    models_list = models_sub.add_parser("list", help="List multi-model endpoint mapping.", prefix_chars="-/")
    models_list.set_defaults(func=cmd_models)
    models_start = models_sub.add_parser("start", help="Start multi-model backend stack.", prefix_chars="-/")
    models_start.add_argument("--host", default="0.0.0.0")
    models_start.add_argument("--port", type=int, default=8000)
    models_start.add_argument("--no-reload", action="store_true")
    models_start.add_argument("--dry-run", action="store_true")
    models_start.set_defaults(func=cmd_models)

    extension = subparsers.add_parser("extension", help="Show IDE/extension integration commands.", prefix_chars="-/")
    extension_sub = extension.add_subparsers(dest="extension_command")
    extension_list = extension_sub.add_parser("list", help="List supported IDE presets.", prefix_chars="-/")
    extension_list.set_defaults(func=cmd_extension)
    extension_show = extension_sub.add_parser("show", help="Show setup commands for one IDE preset.", prefix_chars="-/")
    extension_show.add_argument("ide", choices=sorted(IDE_PRESETS.keys()))
    extension_show.add_argument("--host", default="127.0.0.1")
    extension_show.add_argument("--port", type=int, default=8000)
    extension_show.set_defaults(func=cmd_extension)

    return parser


def main() -> int:
    raw_args = sys.argv[1:]
    if raw_args and raw_args[0] == "student" and not any(flag in raw_args[1:] for flag in ("-h", "--help", "/?")):
        dry_run = False
        forward: list[str] = []
        for item in raw_args[1:]:
            if item == "--dry-run":
                dry_run = True
            else:
                forward.append(item)
        return cmd_student(argparse.Namespace(forward=forward, dry_run=dry_run))
    if raw_args and raw_args[0] == "cognitive" and not any(flag in raw_args[1:] for flag in ("-h", "--help", "/?")):
        dry_run = False
        forward: list[str] = []
        for item in raw_args[1:]:
            if item == "--dry-run":
                dry_run = True
            else:
                forward.append(item)
        return cmd_cognitive(argparse.Namespace(forward=forward, dry_run=dry_run))

    parser = build_parser()
    args = parser.parse_args()
    if not getattr(args, "subcommand", None):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
