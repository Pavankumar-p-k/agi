# Ollama Connectivity Audit

## 1. Which process owns port 11434?

```
> netstat -ano | findstr 11434
TCP    127.0.0.1:11434    0.0.0.0:0    LISTENING    15288
TCP    127.0.0.1:11434    127.0.0.1:54903  ESTABLISHED  15288
TCP    127.0.0.1:54903    127.0.0.1:11434  ESTABLISHED  28084
```

| PID | Process | Role |
|-----|---------|------|
| **15288** | `ollama.exe` | Ollama server — owns the listening socket |
| **28084** | `python.exe` | JARVIS Python process — established connection to Ollama |

**Process 15288 confirmed:** `ollama.exe` (119,492 KB, running as user console session 27).

**Verdict:** Port 11434 is owned by Ollama. No conflict.

---

## 2. Can JARVIS reach `http://127.0.0.1:11434/api/tags`?

```
> curl http://127.0.0.1:11434/api/tags
HTTP 200  (8.5ms)
Models: gemma4:e4b, nomic-embed-text, mistral, tinyllama, moondream,
        deepseek-r1:1.5b, qwen2.5-coder:3b, qwen3:4b, llama3.1,
        tinyllama:1.1b, qwen2.5:7b, llama3.1:8b, mistral:7b, phi3:mini
```

**Also tested via LiteLLM from within Python:**
```
> complete("chat", [{"role":"user","content":"ping"}])
Ok("LITELLM_OK")
```

**Verdict:** JARVIS CAN reach Ollama at `127.0.0.1:11434`. Both direct HTTP and LiteLLM Router work.

---

## 3. What exact URL is configured in JARVIS for Ollama?

| Source | Key | Value |
|--------|-----|-------|
| Config schema (default) | `ollama.base_url` | `http://localhost:11434` |
| Config registry | `ollama.base_url` | `http://localhost:11434` |
| Env var | `OLLAMA_HOST` | **(not set)** |
| Env var | `OLLAMA_URL` | **(not set)** |
| Env var | `OLLAMA_BASE_URL` | **(not set)** |
| Env var | `LLM_BASE_URL` | **(not set)** |

**Verdict:** JARVIS uses the default `http://localhost:11434`. No env var override exists. The URL is correct — `localhost` resolves to `127.0.0.1`, which is where Ollama listens.

**However:** note that the `health_check()` in `core/llm_router.py:236` first pings `/api/tags` then calls `acompletion()` with model="chat". If either step fails, health check reports `False`. Currently:
```
> health_check() = True
```

---

## 4. Why does TUI show MODEL: none when models exist?

**Root cause:** Field name mismatch.

The TUI (`jarvis_tui/main.py:248`) reads:
```python
models = status.get("model_router", {}).get("models", [])
```

The backend (`core/routes/utility.py:28-33`) returns:
```json
{
  "status": "online",
  "ollama": "reachable",
  "model": "ollama/llama3.1:8b",
  "version": "0.1.0"
}
```

There is **no** `"model_router"` key and **no** `"models"` array. The status response uses `"model"` (a single string), not `"model_router": {"models": [...]}`.

**Fix applied:**
- `jarvis_tui/main.py`: Changed to read `status.get("model")` and strip provider prefix (`ollama/`) for display
- `core/routes/utility.py`: Added `"model_router": {"models": [...]}` to the response for forward compatibility

**Before fix:** `sidebar.model_name` stays at default `"none"` because `status.get("model_router", {}).get("models", [])` returns `[]`.
**After fix:** `sidebar.model_name` = `"llama3.1:8b"`.

---

## 5. Does the backend health check pass or fail?

```
> python -c "from core.llm_router import health_check; ..."
health_check() returned: True
```

| Test | Result |
|------|--------|
| `/api/tags` ping | **PASS** (HTTP 200) |
| LiteLLM `acompletion("chat", "ping")` | **PASS** (returns Ok) |
| `health_check()` function | **True** |
| `/api/system/status` → `ollama` field | `"reachable"` |
| `/api/models` → `ollama_available` | `True` |

**Verdict:** Backend health check passes. All 5 checks confirm Ollama is reachable and functional.

---

## Summary

| Question | Answer |
|----------|--------|
| Ollama running? | **YES** — PID 15288, listening on 127.0.0.1:11434 |
| Port 11434 conflict? | **NO** — owned by ollama.exe |
| JARVIS config URL correct? | **YES** — `http://localhost:11434` (no env override) |
| JARVIS can reach Ollama? | **YES** — HTTP 200, LiteLLM Ok() |
| TUI shows correct model? | **FIXED** — was `"none"` due to field name mismatch, now reads `status.model` |

The original `[ASSUMED]` issue occurred because **Ollama was not running at audit start**. Once started, all connectivity checks pass. The TUI `MODEL: none` was a separate frontend-backend field name mismatch, now fixed.
