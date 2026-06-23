# Model Selector Audit — TUI MODEL: none Investigation

## Symptom

The TUI sidebar displays `MODEL: none` even though:
- Ollama is running (PID 15288)
- 14 models are available including `llama3.1:8b`
- `/api/system/status` returns `"model": "ollama/llama3.1:8b"`
- The health check passes
- LiteLLM can call the model

## Root Cause: Field Name Mismatch

### Frontend (TUI) — `jarvis_tui/main.py:248`

```python
models = status.get("model_router", {}).get("models", [])
if models:
    sidebar.model_name = models[0]
```

The TUI expects the status endpoint to return:
```json
{
  "model_router": {
    "models": ["llama3.1:8b", "deepseek-r1:1.5b", ...]
  }
}
```

### Backend — `core/routes/utility.py:28-33`

The actual response is:
```json
{
  "status": "online",
  "ollama": "reachable",
  "model": "ollama/llama3.1:8b",
  "version": "0.1.0"
}
```

**There is no `"model_router"` key** — the backend uses `"model"` (a single string value, not a dict with a `"models"` array).

### Result

`status.get("model_router", {})` → `{}` (empty dict, key not found)
`{}.get("models", [])` → `[]` (empty list)
`if models:` → `False` → `sidebar.model_name` stays at `"none"`

## Fix Applied

### 1. TUI side — `jarvis_tui/main.py`

Changed to read `status.get("model")` directly and strip the `ollama/` provider prefix:

```python
model_val = status.get("model") or status.get("ollama", "")
if model_val and model_val not in ("unreachable", "offline", ""):
    display = model_val.split("/", 1)[1] if "/" in model_val else model_val
    sidebar.model_name = display
```

### 2. Backend side — `core/routes/utility.py`

Added the `"model_router"` key for forward compatibility with the TUI's original lookup pattern:

```python
return {
    "status": "online",
    "ollama": "reachable",
    "model": model,
    "model_router": {
        "models": [model.split("/", 1)[1] if "/" in model else model] if model and ollama_ok else [],
    },
    "version": "0.1.0",
}
```

## Data Flow Diagram

```
TUI (jarvis_tui)
  │
  ├── GET /api/system/status
  │     └── core/routes/utility.py:22  get_system_status()
  │           ├── ollama_ok = await health_check()  → True
  │           └── model = config.get("llm.chat_model")  → "ollama/llama3.1:8b"
  │
  ├── Response (before fix):
  │     {"status":"online","ollama":"reachable","model":"ollama/llama3.1:8b","version":"0.1.0"}
  │
  ├── TUI read (before fix):
  │     status.get("model_router", {}).get("models", [])
  │     → [] → sidebar.model_name stays "none"
  │
  ├── Response (after fix):
  │     {"status":"online","ollama":"reachable","model":"ollama/llama3.1:8b",
  │      "model_router":{"models":["llama3.1:8b"]},"version":"0.1.0"}
  │
  └── TUI read (after fix):
        status.get("model") → "ollama/llama3.1:8b"
        → strip prefix → "llama3.1:8b"
        → sidebar.model_name = "llama3.1:8b"
```

## Configuration Check

| Endpoint | Returns |
|----------|---------|
| `GET /api/system/status` | `model: "ollama/llama3.1:8b"`, `ollama: "reachable"` |
| `GET /api/models` | 16 models, `ollama_available: true` |
| `GET /api/models/groups` | 8 group→model mappings, all populated |

All three endpoints confirm correct model configuration. The issue was purely a frontend field name mismatch — not a connectivity or model availability problem.
