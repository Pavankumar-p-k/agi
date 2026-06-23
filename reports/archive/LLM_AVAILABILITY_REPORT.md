# LLM Availability Report

## Verification Timestamp

**Date:** 2026-06-10
**Tester:** JARVIS Audit

---

## 1. Ollama Installed?

**YES**

```
Location: C:\Users\peter\AppData\Local\Programs\Ollama\ollama.exe
Version:  0.20.7
```

## 2. Ollama Running?

| State | Detail |
|-------|--------|
| **At audit start** | **NO** — no `ollama.exe` process, no Windows service registered |
| **After manual start** | **YES** — `ollama serve` started successfully |
| Windows service | Not installed (`Get-Service ollama` returns nothing) |

**Note:** Ollama must be started manually (`ollama serve`) or installed as a Windows service for persistence across reboots.

## 3. Port 11434 Reachable?

| State | Detail |
|-------|--------|
| **At audit start** | **NO** — `Invoke-WebRequest http://localhost:11434/api/tags` → connection refused / timeout |
| **After manual start** | **YES** — HTTP 200 in ~10ms |
| GPU detected | NVIDIA GeForce RTX 4050 Laptop GPU (6.0 GiB VRAM, CUDA compute 8.9) |

## 4. Configured Model Exists?

| Config Key | Default Value | Available in Ollama? |
|------------|---------------|---------------------|
| `llm.chat_model` | `ollama/llama3.1:8b` | **YES** (`llama3.1:8b` listed) |
| `llm.reasoning_model` | `ollama/deepseek-r1:1.5b` | **YES** (`deepseek-r1:1.5b` listed) |
| `model_groups.reasoning_group` | `chat` | Resolves to `ollama/llama3.1:8b` |

All 14 cached models in Ollama:

```
gemma4:e4b, nomic-embed-text, mistral, tinyllama, moondream,
deepseek-r1:1.5b, qwen2.5-coder:3b, qwen3:4b, llama3.1,
tinyllama:1.1b, qwen2.5:7b, llama3.1:8b, mistral:7b, phi3:mini
```

## 5. Test Prompt Successful?

| Test | Result |
|------|--------|
| Direct Ollama API (`llama3.1:8b`) | **PASS** — returned "HELLO_OK" |
| Direct Ollama API (`deepseek-r1:1.5b`) | **PASS** — returned "OK" |
| LiteLLM Router (`complete("chat", ...)`) | **PASS** — returned "LITELLM_OK" |

## 6. JARVIS Can Call Ollama Successfully?

**YES** — LiteLLM Router resolves `ollama/llama3.1:8b`, calls `http://localhost:11434`, and returns valid responses.

**However:** The failover module (`FailoverRouter`) probes cloud provider profiles (openai, gemini, groq) based on empty `*_API_KEY` env vars, causing unnecessary cooldown delays and log noise before falling back to the direct Ollama call. This does **not** block functionality but wastes ~6 seconds on each first request.

---

## Summary Table

| Check | Status |
|-------|--------|
| Ollama installed? | **YES** (v0.20.7) |
| Ollama running? | **YES** (started manually; no service) |
| Port 11434 reachable? | **YES** (HTTP 200) |
| Configured model exists? | **YES** (llama3.1:8b, deepseek-r1:1.5b) |
| Test prompt successful? | **YES** (direct API + LiteLLM both pass) |
| JARVIS → Ollama works? | **YES** |

## Recommendation

Install Ollama as a Windows service for auto-start on boot:

```powershell
ollama serve --install-service
```
