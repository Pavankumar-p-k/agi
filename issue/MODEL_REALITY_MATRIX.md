# MODEL REALITY MATRIX — Runtime Audit

**Method:** Actual HTTP requests to running server + settings API  
**Date:** 2026-06-10

## Provider Status

| Provider | Configured | Reachable | Actually Called | Returns Tokens | Status |
|----------|-----------|-----------|----------------|----------------|--------|
| **Ollama** | YES (localhost:11434) | YES (14 models) | PARTIAL | NO — calls timeout/fail | PARTIAL |
| **LiteLLM Router** | YES | YES (initializes) | YES | NO — returns error text | BROKEN |
| **OpenAI** | YES (key set: sk-p****QKEA) | UNTESTED | NO (failover disabled) | NO | DISABLED |
| **Anthropic** | NO (key empty) | N/A | NO | NO | NOT CONFIGURED |

## Model Group Mapping (from /api/settings)

| Group | Model | Config Source | Runtime Status |
|-------|-------|--------------|----------------|
| chat | ollama/llama3.1:8b | env/settings | ATTEMPTED — fails |
| reasoning | ollama/llama3.1:8b | env/settings | USED BY CHAT — fails |
| analysis | ollama/qwen2.5:7b | env/settings | UNTESTED |
| code | ollama/qwen2.5-coder:3b | env/settings | UNTESTED |
| vision | ollama/moondream:latest | env/settings | UNTESTED |
| embedding | ollama/nomic-embed-text | env/settings | UNTESTED |
| grader | ollama/phi3:mini | env/settings | UNTESTED |
| orchestrator | ollama/qwen2.5:7b | env/settings | UNTESTED |
| fallback | ollama/llama3.1:8b | env/settings | UNTESTED |
| ping | tinyllama | env/settings | USED FOR HEALTH CHECKS |

## Actual Ollama Models (from Ollama API)

| Model | Size | Available |
|-------|------|-----------|
| llama3.1:8b | 4.9GB | YES |
| llama3.1:latest | 4.9GB | YES (alias) |
| qwen2.5:7b | 4.7GB | YES |
| qwen2.5-coder:3b | 1.9GB | YES |
| qwen3:4b | 2.5GB | YES |
| mistral:7b | 4.4GB | YES |
| mistral:latest | 4.4GB | YES (alias) |
| gemma4:e4b | 9.6GB | YES |
| deepseek-r1:1.5b | 1.1GB | YES |
| phi3:mini | 2.2GB | YES |
| tinyllama:latest | 638MB | YES |
| nomic-embed-text | 274MB | YES |
| moondream:latest | 1.7GB | YES |

## Root Cause of LLM Failure

The chat endpoint routes to `model_groups.reasoning_group = "chat"` which uses `llm.reasoning_model = ollama/llama3.1:8b`. Despite the model being available in Ollama, the LiteLLM Router's `acompletion()` call fails. The UnifiedBrain fallback catches the error and returns the string "LLM unreachable" as if it were a successful AI response.

**Verdict:** LiteLLM Router initializes but fails at runtime. Ollama is healthy. The bug is in the router-to-Ollama bridge.
