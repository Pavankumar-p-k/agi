# REQUEST HANG ROOT CAUSE — v1.1.0

**Date:** 2026-06-10  
**Reported:** User sent "hi" → no response after 1 hour  
**Method:** Process inspection + TCP connection analysis + direct API testing + code path tracing

---

## CLASSIFICATION: BLOCKED + INFINITE_LOOP (compound)

**Primary:** `send_to_backend()` silently discards response → user sees no reply  
**Secondary:** No timeout/feedback mechanism → user has no way to know request completed

---

## FULL TRACE

### Entry Point: TUI (Textual) → `POST /api/chat`

| Step | File | Line | Entered? | Exited? | Time | Waiting On |
|------|------|------|----------|---------|------|------------|
| User types "hi" + Enter | `input_bar.py` | 116 | ✅ | ✅ | instant | — |
| `on_input_submitted()` | `input_bar.py` | 116-131 | ✅ | ✅ | instant | — |
| `chat.add_message("YOU", "hi")` | `input_bar.py` | 124 | ✅ | ✅ | instant | — |
| `run_worker(send_to_backend("hi"))` | `input_bar.py` | 125 | ✅ | ✅ | instant | — |
| Worker: `send_to_backend("hi")` | `input_bar.py` | 133 | ✅ | ❌ **NEVER EXITS VISIBLY** | ∞ | `execute_prompt()` — but this returns |
| `jarvis_client.execute_prompt("hi")` | `jarvis_client.py` | 34-46 | ✅ | ✅ | **~31s** | `httpx.post("/api/chat")` |
| `httpx.AsyncClient.post("/api/chat")` | `jarvis_client.py` | 38 | ✅ | ✅ | ~31s | Server response |

### Server Side: `POST /api/chat`

| Step | File | Line | Entered? | Exited? | Time | Waiting On |
|------|------|------|----------|---------|------|------------|
| `chat_route()` | `core/routes/chat.py` | 41 | ✅ | ✅ | ~31s | `three_pass_handler()` |
| `chat_handler()` | `routers/chat.py` | 89 | ✅ | ✅ | ~31s | `unified_brain.reason()` |
| `unified_brain.reason("hi")` | `brain/UnifiedBrain.py` | 81 | ✅ | ✅ | ~30s | `reasoning_engine.reason()` |
| `reasoning_engine.reason("hi")` | `brain/reasoning_engine.py` | 118 | ✅ | ✅ | ~30s | `complete()` → Ollama |
| `complete("chat", ...)` | `core/llm_router.py` | 128 | ✅ | ✅ | ~30s | `get_router().acompletion()` → Ollama |
| Ollama inference | `localhost:11434` | — | ✅ | ✅ | **~27-31s** | GPU/model load (first inference) |
| `epistemic_tagger.tag_response()` | `brain/epistemic_tagger.py` | ~63 | ✅ | ✅ | instant | — |
| **Return response** | `routers/chat.py` | 162 | ✅ | ✅ | — | — |

### 🔴 ROOT CAUSE — Response Discarded

| Step | File | Line | Entered? | Exited? | Bug |
|------|------|------|----------|---------|-----|
| `execute_prompt()` returns dict | `jarvis_client.py` | 46 | ✅ | ✅ | Returns `{"status":200,"result":{"reply":"..."}}` |
| `send_to_backend()` receives result | `input_bar.py` | 135 | ✅ | ✅ | **RETURN VALUE DISCARDED — no variable assignment** |
| `chat.add_message("JARVIS", reply)` | **NEVER CALLED** | — | ❌ | ❌ | **Missing: response never displayed** |
| User sees | — | — | — | — | Only "YOU: hi", no JARVIS reply → assumes hang |

---

## 8-DIAGNOSTIC CHECKLIST

### 1. Last completed function
- **`execute_prompt()`** at `jarvis_client.py:34-46` — HTTP POST completed, server returned 200, JSON parsed

### 2. Current waiting function
- **Nothing is waiting.** The worker completed, but its return value was discarded. The TUI is idle.

### 3. Blocking dependency
- **None.** All I/O completed. The "hang" is a **display bug**, not a true execution hang.

### 4. Deadlock?
- **NO.** No circular dependencies, no lock contention.

### 5. Infinite retry?
- **NO.** Single POST, no retry loop in the TUI path.

### 6. Infinite stream?
- **NO.** Non-streaming endpoint (`POST /api/chat` returns full JSON).

### 7. Stuck Ollama request?
- **NO.** Ollama responds in ~27-31s (first inference cold start).

### 8. Stuck sub-agent?
- **NO.** No sub-agents in the TUI → `/api/chat` path.

---

## SECONDARY: Agent Stream `POST /api/agent/stream`

### 🔴 Provider Detection Bug

`_detect_provider("http://localhost:11434")` returns **`"openai"`** — NOT `"ollama"`.

**Root cause** — `_is_ollama_native_url()` at `core/llm_core.py` (line not yet checked):

```python
def _is_ollama_native_url(url: str) -> bool:
    ...
    local_ollama_host = host in {"localhost", "127.0.0.1", ...} or parsed.port == 11434
    return local_ollama_host and (path == "/api" or path.startswith("/api/"))
```

For `http://localhost:11434`:
- `path = ""` (no `/api` suffix) → `(path == "/api" or path.startswith("/api/"))` = **False**
- Result: **False** → falls through to `return "openai"`

**Consequence:** `stream_llm_with_fallback()` takes the `else` (non-Ollama) branch:
```python
target_url = url  # = "http://localhost:11434" (Ollama ROOT)
payload = {"model": "ollama/llama3.1:8b", "messages": [...], "stream": True}
```
- Ollama root returns **405 Method Not Allowed** for POST
- Model name `ollama/llama3.1:8b` returns **404 not found** even on correct endpoint

### ❌ Wrong endpoint even in Ollama path

Even if detected as Ollama, `_normalize_ollama_url("http://localhost:11434")` returns `"http://localhost:11434/chat"` — this is also wrong (correct is `/api/chat`).

---

## FIXES APPLIED

All four fixes applied and verified.

### Fix 1: TUI now displays JARVIS response (CRITICAL)

**File:** `jarvis_tui/app/widgets/input_bar.py:133-141`  
**Change:** Capture return value and display JARVIS reply

```python
# BEFORE: return value discarded
await self.app.jarvis_client.execute_prompt(message)

# AFTER: reply displayed in chat stream
result = await self.app.jarvis_client.execute_prompt(message)
reply = (result.get("result") or {}).get("reply") or ""
if reply.strip():
    chat = self.screen.query_one("#chat-stream")
    chat.add_message("JARVIS", reply, msg_type="agent")
```

### Fix 2: Ollama provider detection for bare `host:port` (CRITICAL)

**File:** `core/llm_providers.py:48-59` — `_is_ollama_native_url()`  
**Change:** Return `True` immediately if port is 11434 (Ollama default)

```python
# AFTER:
if parsed.port == 11434:
    return True
```

`http://localhost:11434` and `http://127.0.0.1:11434` now correctly detected as Ollama.

### Fix 3: Strip provider prefix from model name (CRITICAL)

**File:** `core/llm_core.py:68-75` — `stream_llm_with_fallback()`  
**Change:** Strip `ollama/`, `openai/`, `anthropic/`, etc. from model name

```python
if "/" in model and model.split("/", 1)[0].lower() in {"ollama", "openai", ...}:
    model = model.split("/", 1)[1]
```

`ollama/llama3.1:8b` → `llama3.1:8b` (Ollama accepts this)

### Fix 4: Normalize bare Ollama URL to `/api/chat` endpoint

**File:** `core/llm_providers.py:64-82` — `_ollama_api_root()`  
**Change:** Append `/api` when no path exists and URL points to Ollama

```python
if (parsed.port == 11434 or localhost) and not _base_path:
    return url + "/api"
```

`http://localhost:11434` → `http://localhost:11434/api/chat`

---

## FILES INVOLVED

| File | Function | Line | Role |
|------|----------|------|------|
| `jarvis_tui/app/widgets/input_bar.py` | `send_to_backend()` | 133-141 | **PRIMARY BUG** — discards response |
| `jarvis_tui/app/services/jarvis_client.py` | `execute_prompt()` | 34-46 | Returns response correctly (no bug) |
| `core/llm_core.py` | `_is_ollama_native_url()` | (unknown) | **SECONDARY BUG** — provider detection |
| `core/llm_core.py` | `_normalize_ollama_url()` | (unknown) | **SECONDARY BUG** — wrong endpoint path |
| `core/llm_core.py` | `stream_llm_with_fallback()` | 105 | **SECONDARY BUG** — model name prefix not stripped |
| `core/routes/chat.py` | `agent_stream()` | 64-96 | Calls `stream_agent_loop()` with wrong URL |
| `core/graph/nodes.py` | `think_node()` | 291 | Builds candidates from state |
