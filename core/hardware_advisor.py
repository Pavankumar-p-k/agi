import os
import platform
import subprocess
import logging
import psutil
from typing import Dict, List, Any, AsyncGenerator

logger = logging.getLogger("jarvis.hardware_advisor")

MODEL_CATALOG = [
    {"name": "llama3.1:8b", "vram_gb": 5.0, "description": "Meta Llama 3.1 8B", "ollama_tag": "llama3.1:8b", "quant": "4-bit", "recommended_for": "General chat"},
    {"name": "llama3.2:3b", "vram_gb": 2.5, "description": "Meta Llama 3.2 3B", "ollama_tag": "llama3.2:3b", "quant": "4-bit", "recommended_for": "Lightweight chat"},
    {"name": "mistral:7b", "vram_gb": 4.5, "description": "Mistral 7B v0.3", "ollama_tag": "mistral:7b", "quant": "4-bit", "recommended_for": "General chat"},
    {"name": "qwen2.5-coder:7b", "vram_gb": 5.0, "description": "Qwen 2.5 Coder 7B", "ollama_tag": "qwen2.5-coder:7b", "quant": "4-bit", "recommended_for": "Coding"},
    {"name": "qwen2.5:7b", "vram_gb": 5.0, "description": "Qwen 2.5 7B", "ollama_tag": "qwen2.5:7b", "quant": "4-bit", "recommended_for": "General chat"},
    {"name": "phi3:mini", "vram_gb": 2.5, "description": "Microsoft Phi-3 Mini", "ollama_tag": "phi3:mini", "quant": "4-bit", "recommended_for": "Lightweight chat"},
    {"name": "deepseek-r1:1.5b", "vram_gb": 1.5, "description": "DeepSeek R1 1.5B", "ollama_tag": "deepseek-r1:1.5b", "quant": "4-bit", "recommended_for": "Reasoning"},
    {"name": "deepseek-r1:7b", "vram_gb": 5.0, "description": "DeepSeek R1 7B", "ollama_tag": "deepseek-r1:7b", "quant": "4-bit", "recommended_for": "Reasoning"},
    {"name": "gemma2:9b", "vram_gb": 6.0, "description": "Google Gemma 2 9B", "ollama_tag": "gemma2:9b", "quant": "4-bit", "recommended_for": "General chat"},
    {"name": "codellama:7b", "vram_gb": 4.5, "description": "CodeLlama 7B", "ollama_tag": "codellama:7b", "quant": "4-bit", "recommended_for": "Coding"},
    {"name": "llava:7b", "vram_gb": 5.0, "description": "LLaVA 7B Vision", "ollama_tag": "llava:7b", "quant": "4-bit", "recommended_for": "Multimodal"},
    {"name": "moondream:latest", "vram_gb": 1.5, "description": "Moondream 2 Vision", "ollama_tag": "moondream:latest", "quant": "4-bit", "recommended_for": "Multimodal"},
    {"name": "mixtral:8x7b", "vram_gb": 26.0, "description": "Mixtral 8x7B MoE", "ollama_tag": "mixtral:8x7b", "quant": "4-bit", "recommended_for": "High-end chat"},
    {"name": "llama3:70b", "vram_gb": 40.0, "description": "Meta Llama 3 70B", "ollama_tag": "llama3:70b", "quant": "4-bit", "recommended_for": "High-end chat"},
    {"name": "qwen2.5-coder:3b", "vram_gb": 2.5, "description": "Qwen 2.5 Coder 3B", "ollama_tag": "qwen2.5-coder:3b", "quant": "4-bit", "recommended_for": "Coding"},
    {"name": "llama3.1:70b", "vram_gb": 40.0, "description": "Meta Llama 3.1 70B", "ollama_tag": "llama3.1:70b", "quant": "4-bit", "recommended_for": "High-end chat"},
    {"name": "phi3:medium", "vram_gb": 8.0, "description": "Microsoft Phi-3 Medium", "ollama_tag": "phi3:medium", "quant": "4-bit", "recommended_for": "General chat"},
    {"name": "dolphin-mistral:7b", "vram_gb": 4.5, "description": "Dolphin Mistral 7B", "ollama_tag": "dolphin-mistral:7b", "quant": "4-bit", "recommended_for": "Uncensored chat"},
    {"name": "neural-chat:7b", "vram_gb": 4.5, "description": "Intel Neural Chat 7B", "ollama_tag": "neural-chat:7b", "quant": "4-bit", "recommended_for": "General chat"},
    {"name": "starling-lm:7b", "vram_gb": 4.5, "description": "Starling LM 7B", "ollama_tag": "starling-lm:7b", "quant": "4-bit", "recommended_for": "General chat"},
    {"name": "orca-mini:3b", "vram_gb": 2.0, "description": "Orca Mini 3B", "ollama_tag": "orca-mini:3b", "quant": "4-bit", "recommended_for": "Lightweight chat"},
    {"name": "tinyllama:1.1b", "vram_gb": 1.0, "description": "TinyLlama 1.1B", "ollama_tag": "tinyllama:1.1b", "quant": "4-bit", "recommended_for": "Lightweight chat"},
    {"name": "starcoder2:3b", "vram_gb": 2.0, "description": "StarCoder 2 3B", "ollama_tag": "starcoder2:3b", "quant": "4-bit", "recommended_for": "Coding"},
    {"name": "starcoder2:7b", "vram_gb": 5.0, "description": "StarCoder 2 7B", "ollama_tag": "starcoder2:7b", "quant": "4-bit", "recommended_for": "Coding"},
    {"name": "nomic-embed-text", "vram_gb": 0.5, "description": "Nomic Embed Text", "ollama_tag": "nomic-embed-text", "quant": "None", "recommended_for": "Embeddings"},
    {"name": "mxbai-embed-large", "vram_gb": 0.5, "description": "Mixedbread AI Embed Large", "ollama_tag": "mxbai-embed-large", "quant": "None", "recommended_for": "Embeddings"},
    {"name": "all-minilm", "vram_gb": 0.1, "description": "All-MiniLM L6 v2", "ollama_tag": "all-minilm", "quant": "None", "recommended_for": "Embeddings"},
    {"name": "openhermes:7b", "vram_gb": 4.5, "description": "OpenHermes 7B", "ollama_tag": "openhermes:7b", "quant": "4-bit", "recommended_for": "General chat"},
    {"name": "solar:10.7b", "vram_gb": 7.0, "description": "Solar 10.7B", "ollama_tag": "solar:10.7b", "quant": "4-bit", "recommended_for": "General chat"},
    {"name": "falcon:7b", "vram_gb": 4.5, "description": "Falcon 7B", "ollama_tag": "falcon:7b", "quant": "4-bit", "recommended_for": "General chat"},
]

def scan_hardware() -> Dict[str, Any]:
    """Detect GPU VRAM, RAM, and CPU info."""
    result = {
        "gpu_name": "Generic CPU / Integrated Graphics",
        "vram_total_gb": 0.0,
        "vram_free_gb": 0.0,
        "ram_gb": round(psutil.virtual_memory().total / (1024**3), 2),
        "cpu_count": psutil.cpu_count(logical=True),
        "platform": platform.system()
    }

    # Try pynvml (NVIDIA)
    try:
        import pynvml
        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        info = pynvml.nvmlDeviceGetMemoryInfo(handle)
        result["gpu_name"] = pynvml.nvmlDeviceGetName(handle)
        if isinstance(result["gpu_name"], bytes):
            result["gpu_name"] = result["gpu_name"].decode("utf-8")
        result["vram_total_gb"] = round(info.total / (1024**3), 2)
        result["vram_free_gb"] = round(info.free / (1024**3), 2)
        pynvml.nvmlShutdown()
        return result
    except Exception:
        pass

    # Fallback to torch
    try:
        import torch
        if torch.cuda.is_available():
            result["gpu_name"] = torch.cuda.get_device_name(0)
            result["vram_total_gb"] = round(torch.cuda.get_device_properties(0).total_memory / (1024**3), 2)
            result["vram_free_gb"] = round(torch.cuda.memory_reserved(0) / (1024**3), 2) # Approximation
            return result
    except Exception:
        pass

    # Final fallback: Estimation (assume 25% of RAM can be used for integrated VRAM)
    result["vram_total_gb"] = round(result["ram_gb"] * 0.25, 2)
    result["vram_free_gb"] = round(psutil.virtual_memory().available / (1024**3) * 0.25, 2)
    return result

def get_recommended_models(vram_gb: float) -> List[Dict[str, Any]]:
    """Return models that fit in VRAM, sorted by fit and headroom."""
    recommendations = []
    for model in MODEL_CATALOG:
        entry = model.copy()
        entry["fits_in_vram"] = model["vram_gb"] <= vram_gb
        entry["vram_headroom_gb"] = round(vram_gb - model["vram_gb"], 2)
        recommendations.append(entry)

    # Sorting: 1. fits first, 2. most headroom, 3. name
    recommendations.sort(key=lambda x: (not x["fits_in_vram"], -x["vram_headroom_gb"], x["name"]))
    return recommendations

async def pull_model_ollama(model_name: str) -> AsyncGenerator[str, None]:
    """Stream ollama pull output."""
    try:
        process = await subprocess.Popen(
            ["ollama", "pull", model_name],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        while True:
            line = await process.stdout.readline()
            if not line:
                break
            yield line.strip()
        
        await process.wait()
        if process.returncode != 0:
            raise RuntimeError(f"Ollama pull failed for {model_name}")
    except FileNotFoundError:
        yield "Error: Ollama not found. Please install it first."
    except Exception as e:
        yield f"Error pulling model: {str(e)}"

def list_installed_models() -> List[str]:
    """Return list of models currently in Ollama."""
    try:
        output = subprocess.check_output(["ollama", "list"], text=True, stderr=subprocess.STDOUT)
        lines = output.strip().split("\n")
        if len(lines) <= 1:
            return []
        
        models = []
        for line in lines[1:]: # Skip header
            parts = line.split()
            if parts:
                models.append(parts[0])
        return models
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []
