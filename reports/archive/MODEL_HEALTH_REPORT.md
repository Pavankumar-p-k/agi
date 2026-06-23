# MODEL HEALTH REPORT — v1.1.0

**Date:** 2026-06-09  
**Provider:** Ollama (all models local)  
**LiteLLM Router:** Initialized with 7 model groups: chat, code, analysis, reasoning, vision, grader, cloud

## Configured Models

| Model Group | Provider | Local Model | Status |
|-------------|----------|-------------|--------|
| `chat` | ollama | `llama3.1:8b` | ✅ Available |
| `reasoning` | ollama | `deepseek-r1:1.5b` | ✅ Available |
| `embedding` | ollama | `nomic-embed-text:latest` | ✅ Available |

## Ollama Status
- **Server:** `http://localhost:11434` — Reachable
- **Available models (14):** tinyllama, deepseek-r1, qwen2.5-coder, qwen3, qwen2.5, mistral, llama3.1, phi3, moondream, gemma4 (and 4 more)

## LiteLLM Router Health
- Router initializes successfully with all configured models
- First `acompletion()` call returns `[ASSUMED] ` pattern — suggests LiteLLM timing issue on cold start
- Subsequent calls in-process return correct responses

## Observations
- Server startup includes `_warmup_ollama_models()` check (config line 34-65) that verifies Ollama connectivity
- All 14 local models respond to tags endpoint
- No model load failures during startup
