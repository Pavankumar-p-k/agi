"""Component detection — no external dependencies beyond stdlib + psutil."""

from __future__ import annotations

import json
import logging
import os
import platform
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from core.setup.report import (
    CheckResult,
    ComponentStatus,
    HardwareInfo,
    ModelRecommendation,
    SetupPhase,
    SetupReport,
)

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────

ROOT = Path(__file__).resolve().parents[2]
JARVIS_CONFIG_DIR = Path.home() / ".jarvis"
DATA_DIR = JARVIS_CONFIG_DIR / "data"
SETUP_MARKER = DATA_DIR / ".setup_complete"
CLI_CONFIG_PATH = JARVIS_CONFIG_DIR / "config.json"
SETTINGS_PATH = DATA_DIR / "settings.json"
OLLAMA_BASE = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

# Model catalogue — ordered by RAM requirement ascending
_MODEL_CATALOGUE: list[dict[str, Any]] = [
    {"id": "qwen2:0.5b", "name": "Qwen2 0.5B", "size_gb": 0.4, "min_ram_gb": 2, "needs_gpu": False},
    {"id": "tinyllama:1.1b", "name": "TinyLlama 1.1B", "size_gb": 0.6, "min_ram_gb": 3, "needs_gpu": False},
    {"id": "phi3:mini", "name": "Phi-3 Mini", "size_gb": 2.2, "min_ram_gb": 6, "needs_gpu": False},
    {"id": "llama3.2:3b", "name": "Llama 3.2 3B", "size_gb": 2.0, "min_ram_gb": 6, "needs_gpu": False},
    {"id": "qwen2.5:7b", "name": "Qwen 2.5 7B", "size_gb": 4.4, "min_ram_gb": 10, "needs_gpu": False},
    {"id": "mistral:7b", "name": "Mistral 7B", "size_gb": 4.1, "min_ram_gb": 10, "needs_gpu": False},
    {"id": "llama3.1:8b", "name": "Llama 3.1 8B", "size_gb": 4.7, "min_ram_gb": 12, "needs_gpu": False},
    {"id": "codellama:13b", "name": "Code Llama 13B", "size_gb": 7.3, "min_ram_gb": 18, "needs_gpu": True},
]


# ── Individual detectors ───────────────────────────────

def detect_python() -> CheckResult:
    ok = sys.version_info >= (3, 10)
    return CheckResult(
        "Python",
        ComponentStatus.OK if ok else ComponentStatus.ERROR,
        f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "JARVIS requires Python 3.10+" if not ok else "",
    )


def detect_git() -> CheckResult:
    try:
        r = subprocess.run(["git", "--version"], capture_output=True, timeout=5, text=True)
        if r.returncode == 0:
            return CheckResult("Git", ComponentStatus.OK, r.stdout.strip())
        return CheckResult("Git", ComponentStatus.MISSING, "not found", "Install git from https://git-scm.com")
    except FileNotFoundError:
        return CheckResult("Git", ComponentStatus.MISSING, "not found", "Install git from https://git-scm.com")
    except subprocess.TimeoutExpired:
        return CheckResult("Git", ComponentStatus.ERROR, "timed out")


def detect_ollama_installed() -> CheckResult:
    if shutil.which("ollama"):
        return CheckResult("Ollama", ComponentStatus.OK, "binary found")
    return CheckResult("Ollama", ComponentStatus.MISSING,
                        "not found", "Install from https://ollama.com")


def detect_ollama_running() -> CheckResult:
    try:
        with urllib.request.urlopen(f"{OLLAMA_BASE}/api/tags", timeout=3) as resp:
            if resp.status == 200:
                return CheckResult("Ollama service", ComponentStatus.OK, "running")
        return CheckResult("Ollama service", ComponentStatus.ERROR, "not responding")
    except (urllib.error.URLError, urllib.error.HTTPError, OSError):
        return CheckResult("Ollama service", ComponentStatus.MISSING,
                           "not running", "Start Ollama with: ollama serve")


def detect_ollama_models() -> tuple[CheckResult, list[str]]:
    try:
        with urllib.request.urlopen(f"{OLLAMA_BASE}/api/tags", timeout=5) as resp:
            data = json.loads(resp.read().decode())
            models = [m["name"] for m in data.get("models", [])]
            if models:
                return (
                    CheckResult("AI Models", ComponentStatus.OK, f"{len(models)} found: {', '.join(models[:3])}..."),
                    models,
                )
            return (
                CheckResult("AI Models", ComponentStatus.MISSING, "no models installed",
                            "Pull a model: ollama pull llama3.2:3b"),
                [],
            )
    except (urllib.error.URLError, json.JSONDecodeError, OSError):
        return (
            CheckResult("AI Models", ComponentStatus.ERROR, "could not query Ollama"),
            [],
        )


def detect_playwright() -> CheckResult:
    try:
        import playwright
    except ImportError:
        pass
    else:
        return CheckResult("Playwright", ComponentStatus.OK, "package installed")
    try:
        r = subprocess.run(["playwright", "--version"], capture_output=True, timeout=5, text=True)
        if r.returncode == 0:
            return CheckResult("Playwright", ComponentStatus.OK, f"installed ({r.stdout.strip()})")
        return CheckResult("Playwright", ComponentStatus.MISSING, "not found",
                           "Install: pip install playwright && playwright install chromium")
    except FileNotFoundError:
        return CheckResult("Playwright", ComponentStatus.MISSING, "not found",
                           "Install: pip install playwright && playwright install chromium")
    except subprocess.TimeoutExpired:
        return CheckResult("Playwright", ComponentStatus.MISSING, "CLI timed out",
                           "Install: pip install playwright && playwright install chromium")


def detect_docker() -> CheckResult:
    try:
        r = subprocess.run(["docker", "info"], capture_output=True, timeout=5)
        if r.returncode == 0:
            return CheckResult("Docker", ComponentStatus.OK, "available")
        return CheckResult("Docker", ComponentStatus.MISSING, "not running",
                           "Start Docker Desktop or install from https://docker.com")
    except FileNotFoundError:
        return CheckResult("Docker", ComponentStatus.MISSING, "not found",
                           "Install from https://docker.com")
    except subprocess.TimeoutExpired:
        return CheckResult("Docker", ComponentStatus.ERROR, "timed out")


def detect_config() -> CheckResult:
    """Check if JARVIS has been configured before."""
    if SETUP_MARKER.exists():
        try:
            data = json.loads(SETUP_MARKER.read_text(encoding="utf-8"))
            phase = data.get("phase", data.get("completed", False) and "complete" or "not_started")
            if phase in ("complete", "in_progress", "failed"):
                return CheckResult("Configuration", ComponentStatus.OK, f"setup {phase}")
            if phase == "not_started":
                return CheckResult("Configuration", ComponentStatus.MISSING,
                                    "setup marker exists but not started (corrupted?)",
                                    "Run jarvis setup to reconfigure")
        except (json.JSONDecodeError, OSError):
            pass
        return CheckResult("Configuration", ComponentStatus.OK, "setup marker found")
    if SETTINGS_PATH.exists():
        return CheckResult("Configuration", ComponentStatus.OK, "settings found")
    if CLI_CONFIG_PATH.exists():
        return CheckResult("Configuration", ComponentStatus.OK, "CLI config found")
    return CheckResult("Configuration", ComponentStatus.MISSING,
                       "not configured", "Run jarvis setup to configure")


def detect_api_keys() -> tuple[CheckResult, bool]:
    keys = {
        "OPENAI_API_KEY": "OpenAI",
        "ANTHROPIC_API_KEY": "Anthropic",
        "GEMINI_API_KEY": "Gemini",
    }
    found = [v for k, v in keys.items() if os.getenv(k)]
    if found:
        return CheckResult("API Keys", ComponentStatus.OK, f"{', '.join(found)} configured"), True
    return CheckResult("API Keys", ComponentStatus.MISSING,
                       "none configured (local mode works without them)"), False


def detect_hardware() -> HardwareInfo:
    info = HardwareInfo()
    try:
        import psutil
        mem = psutil.virtual_memory()
        info.ram_gb = round(mem.total / (1024 ** 3), 1)
        info.free_ram_gb = round(mem.available / (1024 ** 3), 1)
        disk = psutil.disk_usage(str(Path.home()))
        info.disk_free_gb = round(disk.free / (1024 ** 3), 1)
        info.cpu = platform.processor() or platform.machine()
        info.cpu_cores = psutil.cpu_count(logical=False) or 0
    except ImportError:
        info.ram_gb = 0
    info.os = f"{platform.system()} {platform.release()}"

    # GPU detection
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            timeout=5, stderr=subprocess.DEVNULL, text=True,
        ).strip()
        if out:
            parts = out.split(",")
            info.gpu_name = parts[0].strip()
            info.gpu_vram_gb = round(float(parts[1].strip()) / 1024, 1)
            info.gpu_type = "nvidia"
    except Exception:
        if platform.system() == "Darwin" and platform.machine() == "arm64":
            info.gpu_type = "apple_silicon"
            info.gpu_name = "Apple Silicon"
            try:
                import psutil
                info.gpu_vram_gb = round(psutil.virtual_memory().total / (1024 ** 3), 1)
            except ImportError:
                pass

    return info


def recommend_model(hw: HardwareInfo) -> ModelRecommendation:
    ram = hw.ram_gb
    has_gpu = hw.gpu_type != "none"
    vram = hw.gpu_vram_gb
    effective = vram if has_gpu and vram > 4 else ram

    best = _MODEL_CATALOGUE[0]
    for m in reversed(_MODEL_CATALOGUE):
        if effective >= m["min_ram_gb"] + 2:
            best = m
            break

    if has_gpu and vram > 4:
        reason = f"GPU with {vram}GB VRAM — {best['name']} recommended"
    elif ram >= 16:
        reason = f"{ram}GB RAM — {best['name']} recommended"
    elif ram >= 8:
        reason = f"{ram}GB RAM — {best['name']} is the best fit"
    else:
        reason = f"{ram}GB RAM — {best['name']} (lightest capable model)"

    return ModelRecommendation(
        model_id=best["id"],
        name=best["name"],
        size_gb=best["size_gb"],
        min_ram_gb=best["min_ram_gb"],
        reason=reason,
    )


# ── Aggregated detection ──────────────────────────────

def is_first_run() -> bool:
    """True if setup has never been started (no state file)."""
    if not SETUP_MARKER.exists():
        return True
    try:
        data = json.loads(SETUP_MARKER.read_text(encoding="utf-8"))
        phase = data.get("phase", "not_started")
        # backward compat: old "completed": true files
        if data.get("completed", False):
            return False
        return phase == "not_started"
    except (json.JSONDecodeError, OSError):
        return True


def detect_all() -> SetupReport:
    report = SetupReport()
    report.is_first_run = is_first_run()
    report.python = detect_python()
    report.git = detect_git()
    report.ollama_installed = detect_ollama_installed()
    report.ollama_running = detect_ollama_running()
    report.models, report.installed_models = detect_ollama_models()
    report.playwright = detect_playwright()
    report.docker = detect_docker()
    report.config = detect_config()
    report.api_keys, report.has_api_keys = detect_api_keys()
    report.hardware = detect_hardware()
    report.recommended_model = recommend_model(report.hardware)
    return report
