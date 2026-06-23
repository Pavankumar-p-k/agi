# [ASSUMED] Response — Root Cause Analysis

## Classification

**CATEGORY: FALLBACK_BY_DESIGN** — not a placeholder, not a mock, not a test artifact. The `[ASSUMED]` prefix is an epistemic provenance tag applied by `EpistemicTagger` when the LLM returns an empty response and no explicit provenance is provided.

---

## File / Function / Line Number

| Component | File | Function | Line |
|-----------|------|----------|------|
| API route | `core/routes/chat.py` | `chat_route()` | 41 |
| Chat handler | `routers/chat.py` | `chat_handler()` | 89 |
| Brain reason | `brain/UnifiedBrain.py` | `reason()` | 81 |
| Reasoning engine | `brain/reasoning_engine.py` | `reason()` | 118 |
| LLM router | `core/llm_router.py` | `complete()` | 128 |
| LiteLLM acompletion | `core/llm_router.py` | `complete()` | 148 |
| Epistemic tagger | `brain/epistemic_tagger.py` | `tag_response()` | 63 |
| Tag source definition | `brain/epistemic_tagger.py` | `ResponseSource.INFERENCE` | 34 |
| Provenance fallback | `routers/chat.py` | `chat_handler()` | 132 |
| Empty provenance default | `core/schemas.py` | `ReasonResult.provenance` | 30 |

---

## Call Stack

```
TUI / HTTP Request "hi"
  → POST /api/chat
    → core/routes/chat.py:41  chat_route()
      → routers/chat.py:89    chat_handler()
        → brain/UnifiedBrain.py:81  reason()
          → brain/reasoning_engine.py:118  reason()
            → core/llm_router.py:128  complete("chat", messages, timeout=60)
              → core/llm_router.py:148  get_router().acompletion(model="chat", ...)
                └── LiteLLM Router → ollama/llama3.1:8b → http://localhost:11434
                └── ✗ FAIL: Ollama not running (connection refused / timeout)
              → core/llm_router.py:164  except Exception → Err(LLMError("connection refused"))
            → brain/reasoning_engine.py:143  raw = "".unwrap_or("") = ""
            → brain/reasoning_engine.py:175  _parse_cot("") → answer = ""
            → brain/reasoning_engine.py:184  ReasonResult(answer="", provenance={})
          → routers/chat.py:122  len(raw.answer) = 0 → final = ""
          → routers/chat.py:132  raw.provenance={} (falsy)
                                 → provenance = {"source": "inference", "confidence": 0.5}
          → routers/chat.py:133  epistemic_tagger.tag_response("", provenance)
            → brain/epistemic_tagger.py:73  clean = strip_tags("") = ""
            → brain/epistemic_tagger.py:84  base = ResponseSource.from_str("inference") = "ASSUMED"
            → brain/epistemic_tagger.py:111  return "[ASSUMED] " + "" = "[ASSUMED] "
          → returns {"response": "[ASSUMED] ", ...}
```

---

## Raw LLM Output

**None.** The LLM was never reached.

| Check | Result |
|-------|--------|
| Was `acompletion()` called? | Yes (line 148) |
| Did Ollama respond? | **No** — `localhost:11434` not listening |
| Was the exception caught? | Yes (line 164) |
| Was a fallback attempted? | **No** — `failover.enabled = False` |
| What was the raw content? | Empty string `""` |
| What did `_parse_cot` return? | `("", "")` |

**Ollama process status:** Not running (verified: connection to port 11434 times out).

---

## Final Returned Output

```json
{
  "response": "[ASSUMED] ",
  "intent": {"intent": "chat"},
  "action": {"executed": true},
  "model": "reasoning",
  "privacy_tier": "LOCAL",
  "epistemic_tags": ["ASSUMED"],
  "format_used": "prose",
  "multi_format": {
    "prose": "[ASSUMED] ",
    "json_data": null,
    "html": null,
    "artifact_type": null,
    "artifact_code": null
  }
}
```

HTTP 200. No 500 error. Response is instant (~2-5ms for connection refused + formatting).

---

## Why Tool Execution Is Skipped

The `chat_handler` in `routers/chat.py` does not use the tool execution loop. It calls `unified_brain.reason()` which is a pure LLM call (no tools). The agent loop with tool execution lives in `core/agent_loop.py` (used by `/api/agent/stream` and WebSocket `/ws/agent_stream`), not in the main `/api/chat` route.

---

## Why the Model Output Is NOT Used

The model never produced output. The chain is:

1. `complete()` returns `Err(LLMError("connect ECONNREFUSED ..."))` 
2. `.unwrap_or("")` converts the error into empty string `""`
3. `_parse_cot("")` returns empty answer
4. `ReasonResult(answer="")` carries empty answer
5. `chat_handler()` treats empty answer as "final" (doesn't enter three_pass because len < 200)
6. `epistemic_tagger.tag_response("", ...)` wraps empty string in `[ASSUMED]` tag

The `[ASSUMED]` text **is the tag only** — there is no actual response content beneath it.

---

## Why LiteLLM Fails

`get_router().acompletion()` tries to call:

- **Model group:** `"chat"` (resolved from config `model_groups.reasoning_group = "chat"`)
- **Actual model:** `ollama/llama3.1:8b` (resolved from env `CHAT_MODEL` or config `llm.chat_model`)
- **Target:** `http://localhost:11434/api/chat`

Ollama is not serving on `localhost:11434` (no process running), so the HTTP request either connection-refuses immediately or times out after the OS TCP timeout (~2-3 seconds locally). LiteLLM raises an exception; `complete()` catches it and returns `Err`.

---

## Why No 500 Error

The `except Exception` blocks throughout the chain convert failures into `Result` types (`Err`), not raised exceptions:

- `core/llm_router.py:164` — catches and returns `Err(LLMError(...))`
- `brain/reasoning_engine.py:144` — outer try/except catches, fallback also catches
- `routers/chat.py` — no try/except on the call; the function always returns a dict, never raises

The HTTP route `chat_route()` at `core/routes/chat.py:41` also has no explicit error handling for the result — it trusts `chat_handler` returns a dict, which it always does (via the provenance fallback and epistemic tagger).

---

## Why the Response is "Immediate"

1. Ollama is not running → TCP connection fails immediately → exception in < 100ms
2. Empty string processing + tag formatting is pure Python, sub-millisecond
3. No retry logic triggered (failover disabled, single attempt in `reasoning_engine.reason()`)

Total round-trip: ~5-50ms from HTTP receive to HTTP response.

---

## Fix

Start Ollama or set `CHAT_MODEL`/`REASONING_MODEL_GROUP` to a reachable provider:

```bash
# Start Ollama
ollama serve

# Or use a cloud model (set at least one API key in .env)
# Then set: REASONING_MODEL_GROUP=cloud
# Or override CHAT_MODEL=openai/gpt-4o
```
