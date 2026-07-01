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

"""cli_server.py — Server and Ollama management helpers for the JARVIS CLI."""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import logging
from pathlib import Path
from urllib.parse import urlparse

from cli_utils import python_exe, common_env, spawn_background, run_command
from cli_state import ROOT, MODEL_PORTS

logger = logging.getLogger(__name__)


def backend_server_cmd(host: str, port: int, reload_enabled: bool) -> list[str]:
    code = (
        "import sys, uvicorn; "
        "getattr(sys.stdout, 'reconfigure', lambda **kwargs: None)(encoding='utf-8', errors='replace'); "
        "getattr(sys.stderr, 'reconfigure', lambda **kwargs: None)(encoding='utf-8', errors='replace'); "
        "h, p, r = sys.argv[1], int(sys.argv[2]), sys.argv[3].lower() == 'true'; "
        "uvicorn.run('core.main:app', host=h, port=p, reload=r, ws_ping_interval=60, ws_ping_timeout=30)"
    )
    return [python_exe(), "-c", code, host, str(port), str(reload_enabled).lower()]


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


def free_port(port: int):
    """Kill any process listening on the given port (Windows)."""
    if os.name == "nt":
        script = (
            f"$conn = Get-NetTCPConnection -LocalPort {port} -ErrorAction SilentlyContinue; "
            f"if ($conn) {{ $conn.OwningProcess | ForEach-Object {{ Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }}; "
            f"Write-Host 'Freed port {port}' }}"
        )
        subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, text=True)
        time.sleep(0.5)


def is_server_reachable(base_url: str, timeout: float = 1.0) -> bool:
    host, port = parse_server_location(base_url)
    if not is_port_open(host, port, timeout=min(timeout, 1.0)):
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
        except Exception as e:
            logger.warning("[cli_server] server reachability check failed: %s", e)
            continue
    return False


def wait_for_server(base_url: str, attempts: int = 60, interval_s: float = 1.0) -> bool:
    for _ in range(attempts):
        time.sleep(interval_s)
        if is_server_reachable(base_url, timeout=2.0):
            return True
    return False


def ensure_server_running(base_url: str, host: str = "127.0.0.1", port: int = 8000):
    target_host, target_port = parse_server_location(base_url)
    if target_host not in {"127.0.0.1", "localhost"}:
        return
    if is_server_reachable(base_url, timeout=1.0):
        return
    free_port(target_port)
    print("JARVIS backend is not running. Starting local server...")
    env = common_env()
    env["PYTHONUNBUFFERED"] = "1"
    log_dir = ROOT / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "server.log"
    cmd = backend_server_cmd(target_host or host, target_port or port, False)
    subprocess.Popen(
        cmd,
        cwd=str(ROOT),
        env=env,
        stdout=open(log_path, "w"),
        stderr=subprocess.STDOUT,
    )
    if wait_for_server(base_url):
        print(f"JARVIS backend ready at {base_url}")
        return
    print(f"JARVIS backend did not become ready at {base_url}")
    print(f"  Server log: {log_path}")
    sys.exit(1)


def ollama_base_url(env: dict) -> str:
    return env.get("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")


def is_ollama_reachable(env: dict, timeout: float = 1.0) -> bool:
    base_url = ollama_base_url(env)
    try:
        with urllib.request.urlopen(f"{base_url}/api/tags", timeout=timeout):
            return True
    except Exception as e:
        logger.debug("[JARVIS] Ollama unreachable at %s: %s", base_url, e)
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
            except Exception as e:
                logger.debug("Ollama unreachable at %s: %s", url, e)
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
    for _ in range(timeout_s):
        if is_ollama_reachable({}):
            return True
        time.sleep(1)
    return False


def ensure_local_stack_running(env: dict):
    ensure_ollama_running(env)
    ensure_server_running(env.get("JARVIS_SERVER", "http://127.0.0.1:8000"))


def stop_local_services(include_ollama: bool = False):
    if os.name == "nt":
        python_filter = (
            "Get-CimInstance Win32_Process | "
            "Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -match 'core\\.main:app' } | "
            "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
        )
        subprocess.run(["powershell", "-NoProfile", "-Command", python_filter], capture_output=True, text=True)
        subprocess.run(
            ["taskkill", "/f", "/im", "python.exe", "/fi", "CMD eq *core.main:app*"],
            capture_output=True, text=True,
        )
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
