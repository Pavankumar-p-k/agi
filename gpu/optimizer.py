# gpu/optimizer.py
#
# Run once before starting JARVIS:
#   python gpu/optimizer.py
#   python gpu/optimizer.py --benchmark

import os
import sys
import subprocess
import json
import time
import argparse
from core.model_router import get_ollama_url, resolve_model

RTX_4050_VRAM_GB = 6.0

# -- Env vars optimized for RTX 4050 Ada Lovelace -------------
OLLAMA_ENV_VARS = {
    "OLLAMA_NUM_GPU":           "99",    # all layers to GPU
    "OLLAMA_KEEP_ALIVE":        "300",   # keep model in VRAM 5 min
    "OLLAMA_NUM_PARALLEL":      "1",     # one request at a time (6GB limit)
    "OLLAMA_FLASH_ATTENTION":   "1",     # RTX 40 series speedup ~20%
    "OLLAMA_KV_CACHE_TYPE":     "q8_0", # halves KV cache VRAM cost
    "OLLAMA_MAX_LOADED_MODELS": "1",     # never load 2 big models at once
    "CUDA_VISIBLE_DEVICES":     "0",     # use RTX 4050 specifically
    "OLLAMA_GPU_OVERHEAD":      "0",
}

# -- Model set for multi-model routing --------------------------
MODELS_TO_PULL = [
    ("llama3.1:8b",        "Primary chat (8B)"),
    ("qwen2.5:7b",         "Analysis / decisioning (7B)"),
    ("mistral:7b",         "Creative writing (7B)"),
    ("qwen3:4b",           "Automation / tool use"),
    ("qwen2.5-coder:3b",   "Coding tasks"),
    ("deepseek-r1:1.5b",   "Reasoning / planning"),
    ("moondream",          "Vision"),
    ("phi3:mini",          "Quality / fast evaluation"),
    ("tinyllama",          "Classifier / fast fallback"),
]

# -- Optional removals (empty by default) ----------------------
MODELS_TO_REMOVE = []


def set_env():
    print("\n[GPU Optimizer] Setting environment variables:")
    for k, v in OLLAMA_ENV_VARS.items():
        os.environ[k] = v
        print(f"  {k} = {v}")

    # Write to .env file for persistence
    env_path = os.path.join(os.path.dirname(__file__), "../../.env")
    lines = []
    try:
        with open(env_path) as f:
            lines = f.readlines()
    except FileNotFoundError:
        raise RuntimeError("Placeholder/swallowed exception removed")

    existing_keys = {l.split("=")[0] for l in lines if "=" in l}
    with open(env_path, "a") as f:
        for k, v in OLLAMA_ENV_VARS.items():
            if k not in existing_keys:
                f.write(f"\n{k}={v}")

    print("\n[GPU Optimizer] OK Variables set + written to .env")


def pull_models():
    print("\n[GPU Optimizer] Pulling optimized model set for RTX 4050 6GB:")
    for model, reason in MODELS_TO_PULL:
        print(f"\n  Pulling {model}  ({reason})")
        result = subprocess.run(
            ["ollama", "pull", model],
            capture_output=False,
        )
        if result.returncode == 0:
            print(f"  OK {model} ready")
        else:
            print(f"  X {model} failed - check ollama is running")


def remove_old_models():
    print("\n[GPU Optimizer] Removing oversized models to free disk space:")
    for model in MODELS_TO_REMOVE:
        result = subprocess.run(
            ["ollama", "rm", model],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            print(f"  OK Removed {model}")
        else:
            print(f"  - {model} not installed (OK)")


def benchmark():
    print("\n[GPU Optimizer] Benchmarking models on RTX 4050...\n")
    import httpx

    test_prompt = "Write a Python function to reverse a string."
    results = []

    for model, _ in MODELS_TO_PULL:
        print(f"  Testing {model}...")
        try:
            t_start = time.time()
            target_model = resolve_model(model)
            r = httpx.post(
                f"{get_ollama_url(target_model)}/api/generate",
                json={
                    "model":   target_model,
                    "prompt":  test_prompt,
                    "stream":  False,
                    "options": {"num_predict": 100, "num_gpu": 99},
                },
                timeout=60.0,
            )
            elapsed = time.time() - t_start
            data    = r.json()
            tokens  = data.get("eval_count", 0)
            t_per_s = tokens / elapsed if elapsed > 0 else 0
            results.append((model, t_per_s, elapsed))
            print(f"    {tokens} tokens in {elapsed:.1f}s = "
                  f"{t_per_s:.0f} t/s")
        except Exception as e:
            print(f"    Error: {e}")

    print("\n  -- RESULTS ----------------------------------")
    results.sort(key=lambda x: -x[1])
    for rank, (model, tps, elapsed) in enumerate(results, 1):
        bar = "#" * min(40, int(tps / 2))
        print(f"  {rank}. {model:<25} {tps:>5.0f} t/s  {bar}")


def monitor():
    """Live VRAM monitor - runs until Ctrl+C"""
    print("\n[GPU Optimizer] Live VRAM monitor (Ctrl+C to stop)\n")
    try:
        while True:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.used,memory.free,"
                 "utilization.gpu,temperature.gpu",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True,
            )
            if result.returncode == 0:
                used, free, util, temp = result.stdout.strip().split(", ")
                total = int(used) + int(free)
                pct   = int(used) / total * 100
                bar   = "#" * int(pct / 5) + "." * (20 - int(pct / 5))
                print(f"\r  VRAM: {used}MB/{total}MB [{bar}] "
                      f"{pct:.0f}%  GPU:{util}%  Temp:{temp}C    ",
                      end="", flush=True)
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[Monitor] Stopped.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="JARVIS GPU Optimizer")
    parser.add_argument("--benchmark",    action="store_true")
    parser.add_argument("--monitor",      action="store_true")
    parser.add_argument("--pull",         action="store_true")
    parser.add_argument("--remove-old",   action="store_true")
    args = parser.parse_args()

    if args.benchmark:
        benchmark()
    elif args.monitor:
        monitor()
    elif args.pull:
        pull_models()
    elif args.remove_old:
        remove_old_models()
    else:
        # Default: full setup
        set_env()
        pull_models()
        print("\n[GPU Optimizer] OK RTX 4050 fully optimized for JARVIS")
        print("  Run benchmark:  python gpu/optimizer.py --benchmark")
        print("  Monitor VRAM:   python gpu/optimizer.py --monitor")
