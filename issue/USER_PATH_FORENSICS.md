# USER PATH FORENSICS — "hi" → "LLM unreachable"

## Actual Runtime Path

### Layer 1: CLI → HTTP
```
CLI (jarvis.py → cli_commands.py)
  → urllib.request POST http://127.0.0.1:8000/api/chat
  → Body: {"message": "hi", "tier": "local", "session_id": "<uuid>"}
  → Timeout: 120s
```

### Layer 2: Route Registration
Two competing `POST /api/chat` handlers — both registered:

| Order | File | Handler | Function |
|-------|------|---------|----------|
| 1st (line 428) | `core/routes/chat.py` | `chat_route` | ✅ Wins (first match in Starlette route list) |
| 2nd (line 442) | `core/routes/operations.py` | `chat_endpoint` | ❌ Shadowed — never reached |

**Proof:** Response contains `model=reasoning`, `epistemic_tags=["ERROR"]`, `multi_format` — this format ONLY comes from `routers/chat.py:chat_handler`, NOT from `operations.py:chat_endpoint`.

### Layer 3: Handler (chat_route → chat_handler)
```
core/routes/chat.py:40 → chat_route(req)
  ├── build_unified_context(req.message, session_id, extra_context)  # SIDE EFFECT — return value DISCARDED
  │     ├── ConversationManager(session_id).load()
  │     ├── memory.recall(message, user_id=session_id)
  │     └── ragflow_search(message, top_k=5)  ← HITS OLLAMA before main LLM call
  ├── extract_intent(req.message)                                      # SIDE EFFECT — return value DISCARDED
  │     └── calls instructor→AsyncOpenAI→Ollama/qwen2.5:7b            ← HITS OLLAMA with DIFFERENT model
  └── three_pass_handler(req) → routers/chat.py:chat_handler()
        ├── match_skill("hi") → None
        ├── format_classifier.classify("hi") → "prose"
        ├── unified_brain.reason("hi", {"system_prompt": get_prompt("chat")})
        │     └── brain/UnifiedBrain.py:81 → reason()
        │           └── brain/reasoning_engine.py:119 → ReasonResult
        │                 ├── [SERVER PATH] if self._warmed:       ← True! warmup() ran during lifespan
        │                 │     └── self._ollama_alive()          ← 3s timeout httpx.AsyncClient
        │                 ├── complete(model_group="chat", ...)   ← _fallback_group="chat"
        │                 │     └── core/llm_router.py:142 → complete()
        │                 │           ├── jarvis_config.failover.enabled check
        │                 │           ├── plugin_registry hooks
        │                 │           ├── get_router().acompletion(model="chat", ...)  ← LiteLLM
        │                 │           └── returns Ok(str) or Err(LLMError)
        │                 └── returns ReasonResult(answer=..., provenance=...)
        ├── if len(raw.answer) > 200 → three_pass()
        ├── else → final = raw.answer
        ├── error detection: raw.provenance.get("source") == "error" || empty answer
        └── return dict with model="reasoning", response=...
```

### Layer 4: Model Group Resolution
```
chat_handler calls unified_brain.reason("hi", {"system_prompt": ...})
  → UnifiedBrain.reason() converts context dict to JSON string
  → reasoning_engine.reason(goal="hi", context='{\n  "system_prompt": "You are JARVIS..."\n}')
    → model_group = self._fallback_group = "chat"   (config key "model_groups.reasoning_group" → default "chat")
    → complete("chat", messages=[...])
      → LiteLLM Router.acompletion(model="chat", ...)
        → Router resolves "chat" → litellm_params: {"model": "ollama/llama3.1:8b", ...}
        → httpx POST to OLLAMA_HOST/api/chat with model=llama3.1:8b
```

## Why Isolated Tests Pass but Real User Path Fails

### Test vs Production Differences

| Aspect | Direct Python Test | Real HTTP Server |
|--------|-------------------|------------------|
| `reasoning_engine._warmed` | `False` (fresh import) | `True` (warmup() ran in lifespan) |
| `_ollama_alive()` called? | No (`_warmed=False` skip) | Yes (3s timeout httpx client) |
| Prologue calls before handler | None | `build_unified_context` + `extract_intent` |
| `get_prompt("chat")` returned | Short test prompt | Full production prompt |
| Async event loop state | Clean | Full of background tasks |
| Model loading state | First call loads model | warmup already loaded deepseek-r1 but llama3.1 may be cold |
| Ollama concurrent requests | 1 at a time | Multiple: ragflow_search + extract_intent + chat_handler |

### Most Likely Root Cause

**The prologue calls `build_unified_context` and `extract_intent` hit Ollama FIRST with different models (nomic-embed-text for RAG, qwen2.5:7b for intent), which either:**

1. **Trigger the failover path**: If the combined latency of prologue calls + `_ollama_alive()` 3s timeout + model loading delays causes the `complete()` call to reach the failover path, and failover has no working API keys → returns "unreachable"

2. **Exhaust Ollama's concurrent request capacity**: With multiple simultaneous Ollama requests from different coroutines, some may time out or get queued

3. **Cause a timeout cascade**: The prologue calls eat into the `complete()` timeout budget

### Confirmed Bugs Found (Contributing Factors)

| File | Line | Bug |
|------|------|-----|
| `core/privacy_classifier.py` | 44, 62 | `tier_1_patterns` set in `_ensure_nlp()` but `classify()` accesses it without calling `_ensure_nlp()` → `AttributeError` crash |
| `core/routes/operations.py` | 84 | `model_group = "cloud" if model == "cloud" else "local"` — `"local"` is NOT a registered LiteLLM model name (should be `"chat"`) |
| `core/routes/operations.py` | 71 | Registers duplicate `POST /api/chat` — shadowed by `core/routes/chat.py` handler (dead code) |
| `brain/reasoning_engine.py` | 60 | `httpx.AsyncClient(timeout=3)` — 3s timeout for `_ollama_alive()` is too tight for first request on cold model |
| `brain/reasoning_engine.py` | 134 | `model_group = self._fallback_group` defaults to `"chat"` — warmup tests `"reasoning"` but actual calls use `"chat"` |

## Summary

**Direct tests pass because they skip the prologue (build_unified_context + extract_intent), skip the warmup check (_warmed=False), and hit Ollama with a single clean request. The real HTTP path hits Ollama 2-3 times before the main LLM call, with different models and concurrent requests, in a stateful server where warmup has already run.**

The fix requires tracing which prologue call actually triggers the failure — but from code evidence, the most likely culprit is the interaction between `build_unified_context` (RAG search hits Ollama) + `warmup()` state + `_ollama_alive()` timeout.
