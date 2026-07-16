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
"""
routers/setup.py
----------------
Zero-terminal setup API for JARVIS.

Endpoints:
  GET  /api/setup/hardware      - detect RAM, GPU, disk, OS
  GET  /api/setup/recommend     - suggest best model for this machine
  GET  /api/setup/ollama-status - is Ollama installed + running?
  POST /api/setup/install-ollama - install Ollama silently (no terminal)
  POST /api/setup/pull-model    - download model with SSE progress stream
  GET  /api/setup/models        - list installed Ollama models
  POST /api/setup/auto-wire     - link downloaded model to JARVIS config
  GET  /api/setup/complete      - has first-time setup been done?

Add to core/main.py:
  from routers.setup import router as setup_router
  app.include_router(setup_router)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

import httpx
import psutil
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/setup", tags=["setup"])

# ─────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────

OLLAMA_BASE = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
SETUP_DONE_FILE = Path("data/.setup_complete")

# Model catalogue — ordered by RAM requirement ascending
# Each entry: id, display_name, size_gb, min_ram_gb, needs_gpu, description
MODEL_CATALOGUE = [
    {
        "id": "qwen2:0.5b",
        "name": "Qwen2 0.5B",
        "size_gb": 0.4,
        "min_ram_gb": 2,
        "needs_gpu": False,
        "description": "Ultra-light. Works on any machine. Basic Q&A.",
        "tier": "minimal",
    },
    {
        "id": "tinyllama:1.1b",
        "name": "TinyLlama 1.1B",
        "size_gb": 0.6,
        "min_ram_gb": 3,
        "needs_gpu": False,
        "description": "Very light. Good for simple commands and quick answers.",
        "tier": "minimal",
    },
    {
        "id": "phi3:mini",
        "name": "Phi-3 Mini",
        "size_gb": 2.2,
        "min_ram_gb": 6,
        "needs_gpu": False,
        "description": "Microsoft's small model. Surprisingly smart for its size.",
        "tier": "light",
    },
    {
        "id": "llama3.2:3b",
        "name": "Llama 3.2 3B",
        "size_gb": 2.0,
        "min_ram_gb": 6,
        "needs_gpu": False,
        "description": "Meta's latest small model. Best balance for CPU-only machines.",
        "tier": "light",
        "recommended_cpu": True,
    },
    {
        "id": "llama3.1:8b",
        "name": "Llama 3.1 8B",
        "size_gb": 4.7,
        "min_ram_gb": 10,
        "needs_gpu": False,
        "description": "The sweet spot. Smart, fast enough on modern CPUs, great on GPU.",
        "tier": "balanced",
        "recommended_gpu": True,
    },
    {
        "id": "qwen2.5:7b",
        "name": "Qwen 2.5 7B",
        "size_gb": 4.4,
        "min_ram_gb": 10,
        "needs_gpu": False,
        "description": "Excellent coding + reasoning. Good alternative to Llama 3.1 8B.",
        "tier": "balanced",
    },
    {
        "id": "mistral:7b",
        "name": "Mistral 7B",
        "size_gb": 4.1,
        "min_ram_gb": 10,
        "needs_gpu": False,
        "description": "Fast and capable. Great for European languages too.",
        "tier": "balanced",
    },
    {
        "id": "llama3.1:70b",
        "name": "Llama 3.1 70B",
        "size_gb": 40.0,
        "min_ram_gb": 48,
        "needs_gpu": True,
        "description": "Near GPT-4 quality. Needs a serious GPU (RTX 3090+) or 64GB RAM.",
        "tier": "powerful",
    },
]

# Vision models (for screen understanding)
VISION_MODELS = [
    {
        "id": "llava:7b",
        "name": "LLaVA 7B",
        "size_gb": 4.5,
        "min_ram_gb": 8,
        "description": "Screen understanding, image Q&A. Required for Win+J feature.",
        "role": "vision",
    },
    {
        "id": "moondream:1.8b",
        "name": "Moondream 1.8B",
        "size_gb": 1.5,
        "min_ram_gb": 4,
        "description": "Lightweight vision model. Less accurate but works on 4GB RAM.",
        "role": "vision",
    },
]

# Embedding model — always recommend this for memory
EMBED_MODEL = {
    "id": "nomic-embed-text",
    "name": "Nomic Embed",
    "size_gb": 0.3,
    "min_ram_gb": 2,
    "description": "Powers JARVIS memory and semantic search. Very lightweight.",
    "role": "embedding",
}


# ─────────────────────────────────────────────
# Hardware Detection
# ─────────────────────────────────────────────

def _detect_gpu() -> dict:
    """Detect GPU — tries nvidia-smi, then rocm-smi, then Apple Metal."""
    gpu = {"name": None, "vram_gb": None, "type": "none"}

    # NVIDIA
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name,memory.total",
             "--format=csv,noheader,nounits"],
            timeout=5, stderr=subprocess.DEVNULL
        ).decode().strip()
        if out:
            parts = out.split(",")
            gpu["name"] = parts[0].strip()
            gpu["vram_gb"] = round(float(parts[1].strip()) / 1024, 1)
            gpu["type"] = "nvidia"
            return gpu
    except Exception as e:
        logger.warning("[routers.setu] install_dependencies failed: %s", e)

    # AMD ROCm
    try:
        out = subprocess.check_output(
            ["rocm-smi", "--showmeminfo", "vram", "--csv"],
            timeout=5, stderr=subprocess.DEVNULL
        ).decode()
        if "VRAM" in out:
            gpu["type"] = "amd"
            gpu["name"] = "AMD GPU (ROCm)"
            return gpu
    except Exception as e:
        logger.warning("[routers.setu] install_dependencies failed: %s", e)

    # Apple Silicon
    if platform.system() == "Darwin" and platform.machine() == "arm64":
        gpu["type"] = "apple_silicon"
        gpu["name"] = "Apple Silicon (unified memory)"
        # On Apple Silicon, GPU shares RAM — report total as vram
        gpu["vram_gb"] = round(psutil.virtual_memory().total / (1024 ** 3), 1)

    return gpu


def _get_hardware() -> dict:
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage(str(Path.home()))

    ram_gb = round(mem.total / (1024 ** 3), 1)
    free_ram_gb = round(mem.available / (1024 ** 3), 1)
    disk_free_gb = round(disk.free / (1024 ** 3), 1)

    cpu_brand = platform.processor() or platform.machine()
    try:
        # Better CPU name on Linux
        with open("/proc/cpuinfo") as f:
            for line in f:
                if "model name" in line:
                    cpu_brand = line.split(":")[1].strip()
                    break
    except Exception as e:
        logger.warning("[routers.setu] configure_environment failed: %s", e)

    gpu = _detect_gpu()

    return {
        "ram_gb": ram_gb,
        "free_ram_gb": free_ram_gb,
        "disk_free_gb": disk_free_gb,
        "cpu": cpu_brand,
        "cpu_cores": psutil.cpu_count(logical=False),
        "os": f"{platform.system()} {platform.release()}",
        "os_type": platform.system().lower(),  # windows / darwin / linux
        "python": sys.version.split()[0],
        "gpu": gpu,
        "architecture": platform.machine(),
    }


def _recommend_models(hw: dict) -> dict:
    """
    Pick the best chat model, vision model, and embedding model
    based on detected hardware. Returns plain-English explanation.
    """
    ram = hw["ram_gb"]
    gpu = hw["gpu"]
    has_gpu = gpu["type"] != "none"
    vram = gpu.get("vram_gb") or 0

    # Effective memory for model loading
    effective_gb = vram if has_gpu and vram > 4 else ram

    # Pick best chat model
    chat_model = MODEL_CATALOGUE[0]  # fallback: smallest
    for m in reversed(MODEL_CATALOGUE):
        if effective_gb >= m["min_ram_gb"] + 2:  # +2GB buffer for OS
            chat_model = m
            break

    # Pick vision model
    vision_model = None
    for v in VISION_MODELS:
        if effective_gb >= v["min_ram_gb"] + 2:
            vision_model = v
            break

    # Build explanation in plain English
    if has_gpu:
        explanation = (
            f"Your {gpu['name']} ({vram}GB VRAM) will run JARVIS fast. "
            f"I'm recommending {chat_model['name']} which uses {chat_model['size_gb']}GB."
        )
    elif ram >= 16:
        explanation = (
            f"You have {ram}GB RAM — enough for a capable model. "
            f"CPU mode will be a bit slower but fully functional."
        )
    elif ram >= 8:
        explanation = (
            f"You have {ram}GB RAM. {chat_model['name']} is the best fit — "
            f"smart responses in 2–5 seconds."
        )
    else:
        explanation = (
            f"Your machine has {ram}GB RAM so I'm picking the lightest model "
            f"that still works well. You can always upgrade later."
        )

    models_to_install = [chat_model, EMBED_MODEL]
    if vision_model:
        models_to_install.append(vision_model)

    total_size = round(sum(m["size_gb"] for m in models_to_install), 1)

    return {
        "chat_model": chat_model,
        "vision_model": vision_model,
        "embed_model": EMBED_MODEL,
        "models_to_install": models_to_install,
        "total_download_gb": total_size,
        "explanation": explanation,
        "disk_ok": hw["disk_free_gb"] > total_size + 2,
        "disk_needed_gb": total_size + 1,
        "disk_free_gb": hw["disk_free_gb"],
    }


# ─────────────────────────────────────────────
# Ollama Helpers
# ─────────────────────────────────────────────

async def _ollama_running() -> bool:
    try:
        async with httpx.AsyncClient(timeout=3) as c:
            r = await c.get(f"{OLLAMA_BASE}/api/tags")
            return r.status_code == 200
    except Exception as e:
        logger.warning("[routers.setup] ollama running check failed: %s", e)
        return False


async def _installed_models() -> list[str]:
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.get(f"{OLLAMA_BASE}/api/tags")
            data = r.json()
            return [m["name"] for m in data.get("models", [])]
    except Exception as e:
        logger.warning("[routers.setup] installed models check failed: %s", e)
        return []


def _ollama_installed() -> bool:
    return shutil.which("ollama") is not None


def _get_ollama_install_cmd() -> list[str] | None:
    """Returns silent install command per OS, or None if unsupported."""
    os_type = platform.system().lower()
    if os_type == "linux":
        # Official one-liner
        return ["sh", "-c", "curl -fsSL https://ollama.com/install.sh | sh"]
    elif os_type == "darwin":
        # brew if available, else direct download
        if shutil.which("brew"):
            return ["brew", "install", "ollama"]
        return None  # macOS needs GUI installer
    elif os_type == "windows":
        # winget silent install
        if shutil.which("winget"):
            return ["winget", "install", "-e", "--id", "Ollama.Ollama", "--silent"]
        return None
    return None


# ─────────────────────────────────────────────
# API Routes
# ─────────────────────────────────────────────

@router.get("/hardware")
async def get_hardware():
    """Detect this machine's specs. Used by the setup wizard."""
    try:
        hw = _get_hardware()
        return {"ok": True, "hardware": hw}
    except Exception as e:
        logger.exception("Hardware detection failed")
        return {"ok": False, "error": str(e)}


@router.get("/recommend")
async def get_recommendation():
    """
    Returns the best model recommendation for this machine.
    Plain English explanation included — shown directly to user.
    """
    try:
        hw = _get_hardware()
        rec = _recommend_models(hw)
        installed = await _installed_models()

        # Mark which recommended models are already installed
        for m in rec["models_to_install"]:
            m["installed"] = any(
                m["id"] in inst or inst.startswith(m["id"].split(":")[0])
                for inst in installed
            )

        return {"ok": True, "hardware": hw, "recommendation": rec}
    except Exception as e:
        logger.exception("Recommendation failed")
        return {"ok": False, "error": str(e)}


@router.get("/ollama-status")
async def ollama_status():
    """Check if Ollama is installed and running."""
    installed = _ollama_installed()
    running = await _ollama_running() if installed else False
    models = await _installed_models() if running else []

    return {
        "ok": True,
        "ollama_installed": installed,
        "ollama_running": running,
        "models": models,
        "can_auto_install": _get_ollama_install_cmd() is not None,
        "os": platform.system().lower(),
    }


@router.post("/install-ollama")
async def install_ollama():
    """
    Install Ollama silently — no terminal needed.
    Streams back status as SSE.
    """
    if _ollama_installed():
        return {"ok": True, "message": "Ollama is already installed"}

    cmd = _get_ollama_install_cmd()
    if not cmd:
        return {
            "ok": False,
            "message": "Automatic install not available on this OS. Please visit https://ollama.com/download",
            "download_url": "https://ollama.com/download",
        }

    async def _stream():
        yield _sse("status", {"step": "downloading", "message": "Downloading Ollama installer..."})
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            async for line in proc.stdout:
                text = line.decode(errors="replace").strip()
                if text:
                    yield _sse("log", {"line": text})

            await proc.wait()
            if proc.returncode == 0:
                # Start Ollama service
                await asyncio.create_subprocess_exec(
                    "ollama", "serve",
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await asyncio.sleep(2)
                running = await _ollama_running()
                yield _sse("done", {
                    "success": True,
                    "running": running,
                    "message": "Ollama installed and started successfully!"
                })
            else:
                yield _sse("done", {
                    "success": False,
                    "message": "Install failed. Please visit https://ollama.com/download",
                    "download_url": "https://ollama.com/download",
                })
        except Exception as e:
            yield _sse("done", {"success": False, "message": str(e)})

    return StreamingResponse(_stream(), media_type="text/event-stream")


class PullModelRequest(BaseModel):
    model_id: str


@router.post("/pull-model")
async def pull_model(req: PullModelRequest):
    """
    Pull (download) an Ollama model with real-time SSE progress.
    The Electron dot pulses while this runs.
    """
    model_id = req.model_id.strip()
    if not model_id:
        return {"ok": False, "error": "model_id required"}

    if not await _ollama_running():
        return {"ok": False, "error": "Ollama is not running. Start it first."}

    async def _stream():
        yield _sse("start", {
            "model": model_id,
            "message": f"Starting download of {model_id}..."
        })

        try:
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream(
                    "POST",
                    f"{OLLAMA_BASE}/api/pull",
                    json={"name": model_id, "stream": True},
                ) as response:
                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            data = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        status = data.get("status", "")
                        total = data.get("total", 0)
                        completed = data.get("completed", 0)

                        if total > 0:
                            pct = round((completed / total) * 100, 1)
                            downloaded_gb = round(completed / (1024 ** 3), 2)
                            total_gb = round(total / (1024 ** 3), 2)
                            yield _sse("progress", {
                                "status": status,
                                "percent": pct,
                                "downloaded_gb": downloaded_gb,
                                "total_gb": total_gb,
                                "message": f"Downloading... {pct}% ({downloaded_gb}GB / {total_gb}GB)",
                            })
                        else:
                            yield _sse("progress", {
                                "status": status,
                                "percent": None,
                                "message": status,
                            })

                        if data.get("status") == "success" or "error" in data:
                            break

            # Verify it's actually available
            installed = await _installed_models()
            success = any(
                model_id in m or m.startswith(model_id.split(":")[0])
                for m in installed
            )
            yield _sse("done", {
                "success": success,
                "model": model_id,
                "message": (
                    f"{model_id} is ready!" if success
                    else f"Download may have failed. Try again."
                ),
            })

        except Exception as e:
            logger.exception("Model pull failed: %s", model_id)
            yield _sse("done", {"success": False, "model": model_id, "message": str(e)})

    return StreamingResponse(_stream(), media_type="text/event-stream")


@router.get("/models")
async def list_models():
    """List all installed Ollama models."""
    running = await _ollama_running()
    if not running:
        return {"ok": False, "error": "Ollama not running", "models": []}
    models = await _installed_models()
    return {"ok": True, "models": models}


class AutoWireRequest(BaseModel):
    chat_model: str
    vision_model: str | None = None
    embed_model: str | None = None


@router.post("/auto-wire")
async def auto_wire(req: AutoWireRequest):
    """
    After model download completes, wire it into JARVIS settings automatically.
    No .env editing, no config files — just call this endpoint.
    """
    try:
        from core.settings import get_settings_store
        store = get_settings_store()

        updates = {}

        # Wire chat model
        if req.chat_model:
            store.set("llm.default_model", req.chat_model)
            updates["chat_model"] = req.chat_model

        # Wire vision model
        if req.vision_model:
            store.set("llm.vision_model", req.vision_model)
            updates["vision_model"] = req.vision_model

        # Wire embedding model
        if req.embed_model:
            store.set("llm.embed_model", req.embed_model)
            updates["embed_model"] = req.embed_model

        store.save()

        # Also update the running LLM router without restart
        try:
            from core.llm_router import refresh_router
            await refresh_router()
        except Exception as e:
            logger.warning("[routers.setup] router refresh failed (best-effort): %s", e)

        logger.info("[auto-wire] Wired models: %s", updates)
        return {
            "ok": True,
            "wired": updates,
            "message": "Models connected to JARVIS. No restart needed.",
            "restart_required": False,
        }

    except Exception as e:
        logger.exception("Auto-wire failed")
        return {"ok": False, "error": str(e)}


@router.post("/complete")
async def mark_setup_complete():
    """Mark first-time setup as done — hides the setup wizard."""
    SETUP_DONE_FILE.parent.mkdir(parents=True, exist_ok=True)
    SETUP_DONE_FILE.touch()
    return {"ok": True}


@router.get("/complete")
async def is_setup_complete():
    """Returns whether setup wizard should be shown."""
    done = SETUP_DONE_FILE.exists()
    if done:
        return {"complete": True}

    # Also check if any model is already installed — skip wizard if so
    if await _ollama_running():
        models = await _installed_models()
        if models:
            SETUP_DONE_FILE.touch()
            return {"complete": True, "auto_detected": True, "models": models}

    return {"complete": False}


# ─────────────────────────────────────────────
# SSE Helper
# ─────────────────────────────────────────────

def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"
