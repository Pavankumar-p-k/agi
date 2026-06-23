# Model Selection Flow

**Request:** `POST /api/chat` with `{"message": "hello", "session_id": "test"}`

## Flow Diagram (actual runtime values)

```
User
  │
  ▼
UI (TUI sidebar shows "MODEL: none" — never updated because request fails)
  │
  ▼
POST /api/chat  {"message": "hello", "session_id": "test"}
  │
  ▼
core/routes/chat.py:40  chat_route()
  │
  ├── build_unified_context("hello", session_id="test", extra_context="")
  │     └── ConversationManager(session_id="test")
  │
  ├── extract_intent("hello")
  │     └── {"intent": "chat"}
  │
  └── await three_pass_handler(req)   ← routers/chat.chat_handler
        │
        ▼
      routers/chat.py:116  await unified_brain.reason("hello", {"system_prompt": "..."})
        │
        ▼
      brain/UnifiedBrain.py:83  await self.reasoning.reason(goal="hello", context="...")
        │
        ▼
      brain/reasoning_engine.py:132  model_group = self._fallback_group
        │
        ├── self._fallback_group  =  _jarvis_config.get("model_groups.reasoning_group", "chat")
        │                             → resolves to "chat"  (code default in config_registry)
        │
        └── await complete("chat", messages=[...])
              │
              ▼
            core/llm_router.py:128  complete(model_group="chat")
              │
              ├── config: failover.enabled?  →  False (code default)
              │
              ├── resolved = model_group     →  "chat"
              │
              └── await get_router().acompletion(model="chat", ...)
                    │
                    ▼
                  core/llm_router.py:97  get_router()
                    │
                    ├── _router_instance is None → TRUE (first call)
                    │
                    └── Router(model_list=_build_model_list())
                          │
                          ▼
                        core/llm_router.py:76  _build_model_list()
                          │
                          ├── Reads llm.chat_model from config_registry
                          │     config_registry.get("llm.chat_model")
                          │       │
                          │       ├── override?  NO
                          │       ├── env CHAT_MODEL?  NO
                          │       ├── data/settings.json?  YES → "bulk-test-model"
                          │       ├── config.yaml?  NO
                          │       └── default → "ollama/llama3.1:8b" (never reached)
                          │
                          ├── _model_config("CHAT_MODEL", "bulk-test-model")
                          │     └── model="bulk-test-model" (no provider prefix)
                          │     └── provider="openai" (default when no / in model)
                          │     └── api_base=None
                          │     └── api_key=None (no OPENAI_API_KEY env var)
                          │
                          └── Model entry:
                                model_name="chat"
                                litellm_params={
                                  "model": "bulk-test-model",
                                  "api_key": None,
                                  "api_base": None,
                                  ...
                                }
                              │
                              ▼
                            LiteLLM Router.__init__()
                              │
                              └── get_llm_provider("bulk-test-model")
                                    │
                                    └── No "/" in "bulk-test-model"
                                    └── Not in known provider prefixes
                                    └── ► BadRequestError: LLM Provider NOT provided
                                          You passed model=bulk-test-model
```

## Configuration Resolution (Step by Step)

### Step 1: `config_registry.Config.get("llm.chat_model")`

```python
def get(self, key="llm.chat_model", default=None):
    # 1. In-memory overrides     → _CONFIG_SOURCES["overrides"]["llm.chat_model"] → NOT SET
    # 2. Environment variable    → CHAT_MODEL → NOT SET
    # 3. data/settings.json      → "bulk-test-model"     ← ★ WINNER
    # 4. config.yaml             → NOT SET
    # 5. Code default            → "ollama/llama3.1:8b"  (never reached)
    return "bulk-test-model"
```

### Step 2: `_model_config("CHAT_MODEL", "bulk-test-model")`

```python
raw = os.getenv("CHAT_MODEL", "bulk-test-model")  → "bulk-test-model"
model = "bulk-test-model"
provider = model.split("/", 1)[0] if "/" in model else "openai"  → "openai"
api_key = os.getenv("OPENAI_API_KEY")  → None
api_base = None  # no " @ " in raw, not ollama provider

params = {
    "model": "bulk-test-model",   # ← NO provider prefix!
    "api_key": None,
    "api_base": None,
    "max_tokens": 4096,
    "temperature": 0.7,
}
```

### Step 3: LiteLLM Router deployment creation

```python
deployment = {
    "model_name": "chat",
    "litellm_params": {
        "model": "bulk-test-model",  # ← Cannot determine provider
    }
}
litellm.get_llm_provider("bulk-test-model")
→ Exception: "LLM Provider NOT provided. You passed model=bulk-test-model"
```

## Key Insight

The model is never successfully selected. The configuration chain resolves to `"bulk-test-model"` from `data/settings.json`, but this value is **not a valid model identifier** — it lacks the required `provider/` prefix that LiteLLM needs to determine which provider to call.

## Summary of All Runtime Values

| Variable | Value | Source |
|----------|-------|--------|
| `llm.chat_model` | `"bulk-test-model"` | `data/settings.json` |
| `llm.code_model` | `"ollama/qwen2.5-coder:3b"` | code default |
| `llm.reasoning_model` | `"ollama/llama3.1:8b"` | `data/settings.json` |
| `model_groups.reasoning_group` | `"chat"` | code default |
| `failover.enabled` | `False` | code default |
| `CHAT_MODEL` env var | not set | — |
| `OPENAI_API_KEY` env var | not set | — |
| `LiteLLM model_name` used | `"chat"` | from `model_group` parameter |
| `LiteLLM model` resolved to | `"bulk-test-model"` | from `_build_model_list()` |
| TUI sidebar model display | `"none"` | reactive default, never updated |
