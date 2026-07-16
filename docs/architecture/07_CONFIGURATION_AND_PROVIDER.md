# Phase 7: Configuration & Provider Architecture Audit

**Status**: READ ONLY — no code was modified.  
**Date**: 2026-07-15  
**Scope**: Configuration, Settings, Environment, Providers, Capability Resolution, Model Resolution, Provider Routing, Hardcoded Models, Hardcoded Providers.

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Configuration Architecture](#2-configuration-architecture)
3. [Settings Architecture](#3-settings-architecture)
4. [Environment Variable Landscape](#4-environment-variable-landscape)
5. [Provider Architecture](#5-provider-architecture)
6. [Capability Resolution](#6-capability-resolution)
7. [Model Resolution](#7-model-resolution)
8. [Provider Routing](#8-provider-routing)
9. [Hardcoded Model Names Catalog](#9-hardcoded-model-names-catalog)
10. [Hardcoded Provider Names Catalog](#10-hardcoded-provider-names-catalog)
11. [One Future Architecture](#11-one-future-architecture)
12. [Action Summary](#12-action-summary)

---

## 1. Executive Summary

The configuration, provider, and model resolution landscape has **six distinct router/resolution systems**, **three legacy configuration shims**, and **hundreds of hardcoded model/provider names** scattered across business logic. There is no single source of truth for what model runs for what capability.

### Overall Health Scores

| Area | Score | Rationale |
|------|-------|-----------|
| ConfigurationService (canonical) | 7/10 | Clean 6-tier resolution, but coexists with 2 legacy systems |
| SettingsStore (Pydantic) | 7/10 | Proper schema, but only 8 sub-models — many config keys outside |
| ConfigRegistry defaults | 6/10 | Good metadata, but values duplicate SettingsStore |
| LiteLLM Router (`llm_router.py`) | 6/10 | Good abstraction, but hardcodes 11 local model fallbacks |
| ModelRouter (`model_providers/router.py`) | 5/10 | Clean interface, but hardcodes provider→class map + fallback model |
| HybridModelPlatform | 4/10 | Hardcodes provider order, preferred providers, cost estimates |
| FailoverRouter (`llm_failover.py`) | 4/10 | Hardcodes 22 provider names, per-group model mappings |
| ProviderRouter (`providers/router.py`) | 8/10 | Evidence-based scoring, no hardcoded model names |
| `core/config.py` (deprecated) | 1/10 | Dead shim, routes through to ConfigurationService |
| `core/config_schema.py` (deprecated) | 2/10 | 15 dataclasses with hardcoded defaults, still imported by active code |
| `core/config_registry.py` (deprecated) | 3/10 | Registry metadata is canonical; Config class/singleton is dead |

### Key Findings

- **F-1**: Three configuration systems coexist (ConfigRegistry, SettingsStore, raw `os.getenv` calls in ~50+ files)
- **F-2**: Business logic in 20+ files knows specific model names (gpt-4o, claude-sonnet-4, qwen2.5:7b, deepseek-r1:1.5b, etc.)
- **F-3**: 6 separate resolution/routing systems with overlapping and sometimes contradictory logic
- **F-4**: 2 parallel provider abstractions (ModelProvider for LLMs, ExecutionProvider for functional capabilities) with different registration and resolution mechanisms
- **F-5**: No single Capability → Model → Provider mapping table — every system duplicates the mapping
- **F-6**: Env var cache is stale after import — changes after `ConfigurationService.load()` are invisible
- **F-7**: Registry defaults in `_REGISTRY_MAP` and Pydantic defaults in `JarvisSettings` can diverge
- **F-8**: `.env.local` override semantics are inverted (`.env` wins over `.env.local`)

---

## 2. Configuration Architecture

### 2.1 The Three Coexisting Systems

```
┌──────────────────────────────────────────────────────────────────────────┐
│  SYSTEM A: ConfigurationService (canonical)                             │
│  File: core/configuration/service.py                                    │
│  Singleton: from core.configuration import configuration                │
│                                                                         │
│  6-tier resolution:                                                     │
│    1. _overrides dict (runtime set())                                   │
│    2. _env_cache (env vars scanned at load())                           │
│    3. _flat_config (config.yaml + data/settings.json)                   │
│    4. SettingsStore (~/.jarvis/settings.json, Pydantic-validated)       │
│    5. Auto-resolve capability (dynamic model routing)                   │
│    6. Registry default (_REGISTRY_MAP)                                  │
│                                                                         │
│  API: get(key), set(key, val, persist), resolve(capability)             │
│  Events: publishes CONFIG_CHANGED, CONFIG_RELOADED to global_event_bus  │
└──────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────┐
│  SYSTEM B: SettingsStore (Pydantic-backed)                              │
│  File: core/settings/store.py                                           │
│  Schema: core/settings/schema.py → JarvisSettings (8 sub-models)       │
│                                                                         │
│  Lazy-loaded from ~/.jarvis/settings.json                               │
│  API: get(key), set(key, val), load(), save()                           │
│  Used by: ConfigurationService.get() at tier 4                          │
└──────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────┐
│  SYSTEM C: Legacy Shims (deprecated, still imported)                    │
│                                                                         │
│  core/config.py         → routes through to ConfigurationService        │
│  core/config_schema.py  → dataclass defaults, routes to CS             │
│  core/config_registry.py→ _REGISTRY metadata is canonical; Config(class)│
│                           and config(singleton) are deprecated wraps    │
│                                                                         │
│  Each imports from the other, creating a circular-import spiderweb.     │
│  Each has its own set of hardcoded defaults that can diverge.           │
└──────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Configuration Startup Chain

```
utils/env_loader.py: load_env_files()        (import-time side effect)
  ├── Reads .env       → os.environ.setdefault
  └── Reads .env.local → os.environ.setdefault

core/main.py:
  ├── load_dotenv(~/.jarvis/.env or ./env)
  └── init_config()
        └── configuration.load(config.yaml, settings.json)
              ├── _load_yaml(config.yaml)
              ├── _load_settings_json(settings.json)
              ├── _scan_env_vars()              → one-time scan of _REGISTRY env_vars
              ├── _init_settings_store()         → loads ~/.jarvis/settings.json
              └── _load_providers()              → loads ~/.jarvis/providers.json
```

### 2.3 Config File Inventory

| File | Purpose | Managed By |
|------|---------|------------|
| `.env` | Primary env vars (gitignored) | User / dev |
| `.env.example` | Template for .env | Git-tracked |
| `.env.local` | Local overrides (gitignored) | User (BROKEN — .env wins) |
| `config.yaml` | Plugin system config | ConfigRegistry |
| `data/settings.json` | Runtime persisted settings | ConfigurationService.set() |
| `~/.jarvis/settings.json` | Pydantic-validated runtime config | SettingsStore |
| `~/.jarvis/providers.json` | Provider enablement + routing preferences | ConfigurationService |
| `~/.jarvis/plugin_settings.json` | Per-plugin key-value store | PluginSettingsStore |
| `~/.jarvis/api_keys.json` | API key vault (encrypted) | ApiKeyVault |
| `config/roles.yaml` | RBAC policies | AuthZ system |

### 2.4 Configuration Gaps

| ID | Description | Severity |
|----|-------------|----------|
| C-1 | No file watching — config edits at runtime are undetected | Medium |
| C-2 | Two REST config endpoints (`/config` and `/settings`) with different backends | Medium |
| C-3 | Direct `os.getenv()` calls in ~50+ files bypass the registry | High |
| C-4 | Env var cache is a one-time snapshot; runtime env changes invisible | Medium |
| C-5 | Registry defaults and Pydantic defaults can diverge — no cross-validation | High |
| C-6 | `.env.local` uses `setdefault` so `.env` values win (inverted semantics) | Low |

---

## 3. Settings Architecture

### 3.1 Settings Schema (`core/settings/schema.py`)

```python
class JarvisSettings(BaseModel):         # Root model
    llm: LLMSettings = Field(default_factory=LLMSettings)
    agi: AGISettings = Field(default_factory=AGISettings)
    dnd: DNDSettings = Field(default_factory=DNDSettings)
    memory: MemorySettings = Field(default_factory=MemorySettings)
    voice: VoiceSettings = Field(default_factory=VoiceSettings)
    server: ServerSettings = Field(default_factory=ServerSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    ui: UISettings = Field(default_factory=UISettings)
```

### 3.2 Settings API Endpoints

| Endpoint | File | Method | Backend |
|----------|------|--------|---------|
| `GET /api/settings` | `core/routes/settings.py` | Returns all categories + model groups | SettingsStore |
| `PUT /api/settings` | `core/routes/settings.py` | Update settings | SettingsStore |
| `GET /api/config` | `core/routes/settings.py` (alternative) | Returns ConfigRegistry entries | ConfigRegistry |
| `PATCH /api/settings` | `api/settings_routes.py` | Partial update | SettingsStore |
| `RESET /api/settings` | `api/settings_routes.py` | Reset to defaults | SettingsStore |

**F-4**: Two REST endpoints with different backends — settings mutations through `/settings` may not be visible through `/config` and vice versa.

---

## 4. Environment Variable Landscape

### 4.1 API Keys (auto-discovered)

The system auto-discovers providers by scanning `*_API_KEY` env vars:

| Pattern | Example | Files |
|---------|---------|-------|
| `{NAME}_API_KEY` | `OPENAI_API_KEY` | `llm_failover.py:52`, `config_registry.py`, `agent_launcher.py` |
| `JARVIS_{NAME}_API_KEY` | `JARVIS_OPENAI_API_KEY` | `config_schema.py:318` |

Known LLM providers (hardcoded in `llm_failover.py:38-43`): openai, anthropic, google, gemini, cohere, ai21, aleph_alpha, replicate, huggingface, together, mistral, perplexity, deepseek, groq, xai, sambanova, cerebras, fireworks, llamaapi, voyage, jina, ollama, azure, bedrock, vertexai

### 4.2 Model Selection Env Vars

| Env Var | Maps to Config Key | Default |
|---------|--------------------|---------|
| `CHAT_MODEL` | `llm.chat_model` | `ollama/qwen2.5:7b` |
| `CODE_MODEL` | `llm.code_model` | `ollama/qwen2.5:7b` |
| `ANALYSIS_MODEL` | `llm.analysis_model` | `ollama/qwen2.5:7b` |
| `REASONING_MODEL` | `llm.reasoning_model` | `ollama/deepseek-r1:1.5b` |
| `VISION_MODEL` | `llm.vision_model` | `ollama/moondream:latest` |
| `EMBEDDING_MODEL` | `llm.embedding_model` | `ollama/nomic-embed-text:latest` |
| `GRADER_MODEL` | `llm.grader_model` | `ollama/phi3:mini` |
| `ORCHESTRATOR_MODEL` | `llm.orchestrator_model` | `ollama/qwen2.5:7b` |
| `FALLBACK_MODEL` | `llm.fallback_model` | `ollama/qwen2.5:7b` |
| `TEACHER_MODEL` | `role_models.teacher` | `ollama/qwen2.5:7b` |
| `MODEL_MODE` | `model.mode` | `local` |

### 4.3 Ollama-Specific Env Vars

| Env Var | Default | Purpose |
|---------|---------|---------|
| `OLLAMA_URL` / `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_MODEL_ENDPOINTS` | (none) | Multi-instance model→URL mapping |
| `OLLAMA_MULTI_INSTANCE` | (none) | Enable multi-instance mode |
| `OLLAMA_TIMEOUT` | `120` | Request timeout |
| `OLLAMA_KEEP_ALIVE` | `5m` | Model keep-alive duration |
| `OLLAMA_NUM_GPU` | (none) | GPU layer count |
| `OLLAMA_NUM_PARALLEL` | (none) | Parallel requests |
| `OLLAMA_FLASH_ATTENTION` | (none) | Flash attention |
| `OLLAMA_KV_CACHE_TYPE` | (none) | KV cache quantization |
| `OLLAMA_MAX_LOADED_MODELS` | (none) | Max concurrently loaded |
| `OLLAMA_GPU_OVERHEAD` | (none) | GPU memory overhead |

### 4.4 Failover Env Vars

| Env Var | Default | Purpose |
|---------|---------|---------|
| `FAILOVER_ENABLED` | `False` | Enable cloud failover |
| `FAILOVER_OPENAI_MODEL` | `gpt-4o-mini` | OpenAI failover model |
| `FAILOVER_ANTHROPIC_MODEL` | `claude-3-haiku-20240307` | Anthropic failover model |
| `FAILOVER_COOLDOWN` | `60` | Cooldown after failure |
| `FAILOVER_MAX_RETRIES` | `3` | Max retries |

### 4.5 Other Notable Env Vars

| Env Var | Default | Category |
|---------|---------|----------|
| `JARVIS_HOST` | `127.0.0.1` | Server |
| `JARVIS_PORT` | `8000` | Server |
| `JARVIS_DEV_MODE` | `True` | Server |
| `JARVIS_SECRET_KEY` | `""` | Server |
| `LOG_LEVEL` | `INFO` | Logging |
| `BROWSER_ENABLED` / `BROWSER_HEADED` | various | Browser |
| `SEARXNG_URL` | `http://localhost:8888` | Search |
| `TAVILY_API_KEY` / `BRAVE_API_KEY` | (none) | Search |
| `MEMORY_PROVIDER` | `mem0` | Memory |
| `MEMORY_RECALL_LIMIT` | `10` | Memory |
| `TELEGRAM_BOT_TOKEN` / `DISCORD_TOKEN` / `SLACK_BOT_TOKEN` | (none) | Channels |
| `GITHUB_TOKEN` | (none) | GitHub |
| `VOICE_ENABLED` / `TTS_PROVIDER` / `STT_PROVIDER` | various | Voice |
| `JARVIS_API_TOKEN` / `API_TOKEN` | (none) | Auth |
| `CHROMADB_HOST` / `CHROMADB_PORT` | `localhost:8100` | Vector DB |
| `SUPABASE_URL` / `SUPABASE_KEY` | (none) | Cloud DB |
| `DEEPGRAM_API_KEY` / `AZURE_SPEECH_KEY` / `AZURE_SPEECH_REGION` | (none) | Speech |
| `META_WHATSAPP_TOKEN` / `META_WHATSAPP_PHONE_ID` | (none) | WhatsApp |
| `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` / `TWILIO_WHATSAPP_FROM` | (none) | Twilio |
| `RAGFLOW_BASE_URL` / `RAGFLOW_API_KEY` | `http://localhost:9380` | RAG |
| `STABILITY_API_KEY` / `REPLICATE_API_TOKEN` / `TOGETHER_API_KEY` | (none) | Image gen |
| `EMBEDDING_URL` / `EMBEDDING_MODEL` | (none) | Embeddings |

---

## 5. Provider Architecture

### 5.1 Two Parallel Provider Abstractions

```
┌────────────────────────────────────────────────────────────────────────────┐
│          ModelProvider (ABC)                 ExecutionProvider (ABC)       │
│          core/model_providers/base.py        core/providers/base.py        │
│                                                                           │
│  Purpose: LLM text generation               Purpose: Functional capabilities│
│  Methods: generate(), stream(),              Methods: execute(),           │
│           embeddings(), vision(),                     handle_tool(),        │
│           health_check()                             capabilities(),         │
│                                                      health(),              │
│                                                      estimate_cost()         │
│                                                                           │
│  Concrete implementations:                    Concrete implementations:     │
│  - OpenAIProvider (openai)                    - ForgeProvider (coding)      │
│  - AnthropicProvider (anthropic)              - BrowserProvider (web)      │
│  - OllamaProvider (ollama)                    - ResearchProvider           │
│  - GeminiProvider (gemini)                    - AutomationProvider         │
│  - GroqProvider (groq)                        - MessagingProvider          │
│  - OpenRouterProvider (openrouter)            - EmailProvider              │
│                                               - DesktopProvider            │
│                                               - GitHubProvider             │
│                                               - DeploymentProvider         │
│                                               - WorkspaceProvider          │
│                                               - ClaudeCodeProvider (ext)   │
│                                               - CodexProvider (ext)        │
└────────────────────────────────────────────────────────────────────────────┘
```

### 5.2 Provider Registration (`core/providers/bootstrap.py`)

Registration order at startup:
1. `register_internal_providers()` — 10 hardcoded imports and registrations
2. `register_external_providers()` — claude_code, codex (conditional on installation)
3. `bootstrap_v2_providers()` — SDK pipeline from `~/.jarvis/providers/` manifests
4. `scan_provider_plugins()` — legacy v1 manifest fallback
5. `register_sdk_providers()` — SDK-based auto-discovery

### 5.3 Provider Registry Capability Index

The `ProviderRegistry` maintains a capability→provider index. When a new provider is registered, its `capabilities()` method is queried and the index is updated. This enables `get_providers_for_capability(capability)` lookups.

**Gap**: ExecutionProvider capabilities are registered here, but ModelProvider capabilities (chat, code, vision, etc.) are NOT — they use a separate resolution system.

### 5.4 Provider Boot Sequence

```
bootstrap_providers()
  ├── register_internal_providers()    10 providers, priority=10
  ├── register_external_providers()    2 providers, priority=50-60
  ├── bootstrap_v2_providers()         SDK manifests from ~/.jarvis/providers/
  ├── scan_provider_plugins()          Legacy v1 JSON manifests
  └── register_sdk_providers()         SDK auto-discovery
```

---

## 6. Capability Resolution

There are **6 separate resolution systems**, each with its own capability→model/provider mapping. This is the core architectural problem.

### 6.1 ConfigurationService.resolve(capability) → "provider/model"

**File**: `core/configuration/service.py:364-375`

```
resolve(capability)
  → reads routing preference from providers.json
  → if "auto": _auto_resolve(capability)
      → ollama enabled? → _local_model_for_capability() → "ollama/qwen2.5:7b"
      → not offline_only? → try openai/anthropic → _resolve_for_provider()
      → fallback → "ollama/qwen2.5:7b"
  → if explicit provider: _resolve_for_provider(provider, capability)
```

**Hardcoded models**: `qwen2.5:7b`, `qwen2.5-coder:3b`, `deepseek-r1:1.5b`, `moondream:latest`, `phi3:mini`, `nomic-embed-text:latest`, `tinyllama`, `gpt-4o`, `claude-sonnet-4-20250514`, `text-embedding-3-small`

**Hardcoded providers**: `ollama`, `openai`, `anthropic`

### 6.2 LiteLLM Router — model_for_role(role) → model name

**File**: `core/llm_router.py:79-87`

```
ROLE_MODELS = {
    "chat": "llama3.1:8b", "analysis": "qwen2.5:7b",
    "reasoning": "deepseek-r1:1.5b", "planning": "qwen3:4b",
    "code": "qwen2.5:7b", "creative": "mistral:7b",
    "vision": "moondream:latest", "classifier": "tinyllama",
    "emotion": "tinyllama", "quality": "phi3:mini",
    "fallback": "tinyllama",
}
```

**Hardcoded models**: 11 models, all Ollama local models.

### 6.3 ModelRouter.select(task) → (provider, model)

**File**: `core/model_providers/router.py:156-175`

```
select(task)
  → get_profile(task) → TaskProfile(primary="local", fallback="cloud")
  → _resolve_provider_name("local") → "ollama"
  → check health → if healthy: provider.default_model
  → if not: _resolve_provider_name("cloud")
      → iterate ["openai", "anthropic", "openrouter", "groq", "gemini"]
  → final fallback: ("ollama", "qwen2.5-coder:3b")
```

**Hardcoded models**: `qwen2.5-coder:3b`

**Hardcoded providers**: `ollama`, `openai`, `anthropic`, `openrouter`, `groq`, `gemini`

### 6.4 HybridModelPlatform.generate(task, messages) → ModelResult

**File**: `core/model_providers/hybrid.py:144-175, 206-214`

```
_pick_for_mode(task)
  → LOCAL mode: "ollama"
  → CLOUD mode:
      → check PREFERRED_PROVIDERS {VISION→openai, CODING→anthropic, REASONING→anthropic}
      → iterate ["openai", "anthropic", "openrouter", "groq", "gemini"]
  → HYBRID mode:
      → COMPLEX_TASKS? → preferred provider or iterate cloud list
      → SIMPLE_TASKS? → "ollama"
  → fallback: "ollama"
```

**Hardcoded providers**: `ollama`, `openai`, `anthropic`, `openrouter`, `groq`, `gemini` (in explicit order, 2 places)

**Hardcoded preferred providers**: VISION→openai, CODING→anthropic, REASONING→anthropic

### 6.5 FailoverRouter.complete(model_group, messages) → Result

**File**: `core/llm_failover.py:256-284`

```
_resolve_model(model_group, provider)
  → per-group mapping:
      chat:    openai→"openai/gpt-4o", anthropic→"anthropic/claude-3-5-sonnet-20240620", ollama→"ollama/llama3.1:8b"
      code:    openai→"openai/gpt-4o", anthropic→"anthropic/claude-3-5-sonnet-20240620"
      analysis:openai→"openai/gpt-4o", anthropic→"anthropic/claude-3-5-sonnet-20240620"
      reasoning:openai→"openai/o1", anthropic→"anthropic/claude-3-5-sonnet-20240620", deepseek→"deepseek/deepseek-reasoner"
```

**Hardcoded models**: `gpt-4o`, `claude-3-5-sonnet-20240620`, `llama3.1:8b`, `o1`, `deepseek-reasoner`

**Hardcoded providers**: 22 in `_KNOWN_LLM_PROVIDERS`; 4 used in model resolution

### 6.6 ProviderRouter.select(capability) → ExecutionProvider

**File**: `core/providers/router.py:108-176`

This is the **cleanest** system — it uses evidence-based scoring with 7 dimensions, reads from the ProviderRegistry capability index, and has no hardcoded model or provider names. It selects `ExecutionProvider` instances, not models.

**Score**: 8/10 — the model to follow for the One Future Architecture.

---

## 7. Model Resolution

### 7.1 How a Chat Request Resolves (example)

When a user sends a chat message, the model is selected through one of these paths:

```
USER MESSAGE
  │
  ├─→ workflow/planner → ModelRouter.select(TaskType.CHAT)
  │     → resolve "local" → ollama
  │     → ollama.default_model (gpt-4o if OpenAIProvider, etc.)
  │
  ├─→ LLMRouter.complete() → litellm.Router(model_list from env vars)
  │     → reads CHAT_MODEL env var → "ollama/qwen2.5:7b"
  │     → reads model endpoints → routes to local Ollama
  │
  ├─→ HybridModelPlatform.generate(TaskType.CHAT)
  │     → _pick_for_mode → depends on mode
  │     → provider.default_model
  │
  ├─→ ConfigurationService.get("llm.chat_model")
  │     → 6-tier resolution → "ollama/qwen2.5:7b"
  │
  └─→ FailoverRouter.complete("chat", messages)
        → _resolve_model("chat", provider) →
          openai: "openai/gpt-4o"
          anthropic: "anthropic/claude-3-5-sonnet-20240620"
          ollama: "ollama/llama3.1:8b"

NOTE: These paths may disagree on which model runs.
```

### 7.2 Model→Context Window Mapping

**File**: `core/model_context.py:52-169`

~70 hardcoded model→context size entries across 14 providers (Anthropic, OpenAI, DeepSeek, Google, Mistral, xAI, Meta, Qwen, Cohere, Perplexity, MiniMax, Moonshot, Microsoft, Nvidia, Yi, Nous).

**Severity**: LOW — context windows are relatively stable per model family. But this still couples business logic to specific model version strings (e.g. `claude-sonnet-4`, `gpt-4.1`).

### 7.3 Model Behavior Helpers

**File**: `core/llm_providers.py:254-274`

```python
_MAX_COMPLETION_TOKENS_MODELS = {"o1", "o3", "o4", "gpt-4.5", "gpt-5"}
_FIXED_TEMPERATURE_MODELS = ("o1", "o3", "o4", "gpt-5")
_THINKING_MODEL_PATTERNS = ("qwen3", "qwq", "deepseek-r1", "deepseek-reasoner", "minimax", "m2-reap", "gemma")
```

These control API behavior (which parameters to send) based on model name. This is **necessary** business logic (different APIs require different request shapes), but model names leak into the generic provider layer.

---

## 8. Provider Routing

### 8.1 Router Comparison

| Router | Selects | Resolution Method | Hardcoded Models | Hardcoded Providers | Health Score |
|--------|---------|-------------------|------------------|---------------------|--------------|
| `ProviderRouter` | ExecutionProvider | Evidence-based scoring (7 dims) | None | None | 8/10 |
| `ConfigurationService` | provider/model string | Config + capability mapping | 10 local + 4 cloud | 3 (ollama, openai, anthropic) | 6/10 |
| `ModelRouter` | (ModelProvider, model) | Task profile + health check | 1 fallback | 6 | 5/10 |
| `HybridModelPlatform` | ModelProvider name | Mode + task type + preferred | None | 6 (ordered) + 3 preferred | 4/10 |
| `LiteLLM Router` | model via litellm | Env var + config + aliases | 11 local models | Implicit (via model prefix) | 6/10 |
| `FailoverRouter` | (profile, model string) | AuthProfile iteration + model map | 5 cloud models | 22 known + 4 resolved | 4/10 |

### 8.2 ProviderRouter Scoring Dimensions

From `core/providers/router.py:39-48`:

```python
_WEIGHTS = {
    "historical_success":    0.20,   # Past performance for this capability
    "benchmark_quality":     0.15,   # Benchmark scores
    "health":                0.15,   # Current health status
    "latency":               0.15,   # Response time
    "cost":                  0.10,   # Cost per request
    "budget":                0.10,   # Remaining budget
    "offline_availability":  0.05,   # Works offline?
    "priority":              0.10,   # Admin-set priority
}
```

This is the **ONE model to follow** for the future architecture. It has zero hardcoded model/provider names, uses configurable weights, records decisions for self-improvement, and supports calibration.

---

## 9. Hardcoded Model Names Catalog

Every place business logic knows specific model names. **DRIFT** markers indicate where the value differs from the canonical registry.

### 9.1 `core/configuration/service.py` — Canonical Config (10 violations)

| Line | Code | Reality Score |
|------|------|---------------|
| 394 | `chat → "qwen2.5:7b"` | 7/10 (registry default matches) |
| 395 | `code → "qwen2.5-coder:3b"` | 7/10 |
| 396 | `analysis → "qwen2.5:7b"` | 7/10 |
| 397 | `reasoning → "deepseek-r1:1.5b"` | 7/10 |
| 398 | `vision → "moondream:latest"` | 7/10 |
| 399 | `grader → "phi3:mini"` | 7/10 |
| 400 | `embedding → "nomic-embed-text:latest"` | 7/10 |
| 401 | `orchestrator → "qwen2.5:7b"` | 7/10 |
| 402 | `fallback → "tinyllama"` | 7/10 |
| 403 | `cloud → "qwen2.5:7b"` | 5/10 (DRIFT — cloud should be cloud model) |
| 411 | `openai chat/code/vision → "gpt-4o"` | 7/10 |
| 411 | `openai embedding → "text-embedding-3-small"` | 7/10 |
| 412 | `anthropic chat/code/vision → "claude-sonnet-4-20250514"` | 7/10 |

### 9.2 `core/config_registry.py` — Registry Defaults (11 violations)

| Line | Key | Default | Reality Score |
|------|-----|---------|---------------|
| 46 | `llm.chat_model` | `ollama/qwen2.5:7b` | 7/10 |
| 47 | `llm.code_model` | `ollama/qwen2.5:7b` | 7/10 |
| 48 | `llm.analysis_model` | `ollama/qwen2.5:7b` | 7/10 |
| 49 | `llm.reasoning_model` | `ollama/deepseek-r1:1.5b` | 7/10 |
| 50 | `llm.vision_model` | `ollama/moondream:latest` | 7/10 |
| 51 | `llm.embedding_model` | `ollama/nomic-embed-text:latest` | 7/10 |
| 52 | `llm.grader_model` | `ollama/phi3:mini` | 7/10 |
| 53 | `llm.orchestrator_model` | `ollama/qwen2.5:7b` | 7/10 |
| 54 | `llm.fallback_model` | `ollama/qwen2.5:7b` | 7/10 |
| 56 | `llm.ping_model` | `tinyllama` | 7/10 |
| 62 | `role_models.default` | `ollama/llama3.1:8b` | 7/10 |
| 117 | `failover.openai_model` | `gpt-4o-mini` | 7/10 |
| 118 | `failover.anthropic_model` | `claude-3-haiku-20240307` | 7/10 |

### 9.3 `core/llm_router.py` — LiteLLM Router (28 violations)

| Line | Code | Type |
|------|------|------|
| 43-53 | `DEFAULT_MODEL_ENDPOINTS` — 10 model→URL mappings | Default endpoints |
| 56-68 | `MODEL_ALIASES` — 12 alias entries | Aliases (acceptable) |
| 79-87 | `ROLE_MODELS` — 12 roles × 1 model each | **Core business logic** |
| 89-98 | `MODEL_FALLBACKS` — 10 models × 1-3 fallbacks each | **Core business logic** |

### 9.4 `core/llm_failover.py` — Failover Router (8 violations)

| Line | Code | Type |
|------|------|------|
| 169 | Probe model: `gpt-4o-mini` (openai) / `claude-3-haiku-20240307` (anthropic) | Probe |
| 260-262 | `chat` → `openai/gpt-4o`, `anthropic/claude-3-5-sonnet-20240620`, `ollama/llama3.1:8b` | **Core business logic** |
| 265-266 | `code` → `openai/gpt-4o`, `anthropic/claude-3-5-sonnet-20240620` | **Core business logic** |
| 268-269 | `analysis` → `openai/gpt-4o`, `anthropic/claude-3-5-sonnet-20240620` | **Core business logic** |
| 273-275 | `reasoning` → `openai/o1`, `anthropic/claude-3-5-sonnet-20240620`, `deepseek/deepseek-reasoner` | **Core business logic** |

### 9.5 `core/llm_providers.py` — Provider API Behavior (5 violations)

| Line | Code | Type |
|------|------|------|
| 254 | `_MAX_COMPLETION_TOKENS_MODELS = {"o1", "o3", "o4", "gpt-4.5", "gpt-5"}` | API behavior (may be necessary) |
| 264 | `_FIXED_TEMPERATURE_MODELS = ("o1", "o3", "o4", "gpt-5")` | API behavior (may be necessary) |
| 274 | `_THINKING_MODEL_PATTERNS = ("qwen3", "qwq", "deepseek-r1", ...)` | API behavior (may be necessary) |
| 28-32 | `ANTHROPIC_MODELS` list — 7 model names | Whitelist |

### 9.6 `core/model_providers/openai.py` — OpenAI Provider (9 violations)

| Line | Code | Type |
|------|------|------|
| 17 | `default_model = "gpt-4o"` | Provider default |
| 22-25 | `_models = ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo", "o1", "o3", "o4-mini", "gpt-4.1", "gpt-4.1-mini"]` | Model list |
| 89 | `embed_model = "text-embedding-3-small"` | Hardcoded in embeddings() |

### 9.7 `core/model_providers/anthropic.py` — Anthropic Provider (7 violations)

| Line | Code | Type |
|------|------|------|
| 15-20 | `ANTHROPIC_MODELS` list — 7 model names | Model list |
| 25 | `default_model = "claude-sonnet-4-20250514"` | Provider default |

### 9.8 `core/model_context.py` — Context Window Lookup (~70 violations)

| Lines | Models | Count |
|-------|--------|-------|
| 54-64 | Anthropic (claude-sonnet-4-5 through claude-3-haiku) | 10 |
| 67-80 | OpenAI (gpt-5 through o3-mini) | 14 |
| 81-130 | DeepSeek, Google, Mistral, xAI, Meta, Qwen, Cohere, Perplexity, MiniMax, Moonshot, Microsoft, Nvidia, Yi, Nous, open community | ~45 |

### 9.9 Other Files

| File | Line | Model | Type |
|------|------|-------|------|
| `routers/screen.py:62` | `["moondream:latest", "moondream", "llava:7b", "llava"]` | Vision model fallback |
| `core/config_schema.py:62-73` | 9 model→port mappings | Deprecated defaults |
| `models/hybrid_models.py:353-362` | 7 model→task mappings | Legacy |
| `benchmarks/*.py` | `AGENT_MODEL` default `qwen2.5:7b` (8 files) | Benchmark defaults |

### 9.10 Total Hardcoded Model Name Count

| Category | Count | Severity |
|----------|-------|----------|
| Local model defaults (ollama) | ~25 | Medium — sensible defaults for local dev |
| Cloud model defaults (openai/anthropic) | ~15 | Medium — version pinning |
| API behavior model lists | ~20 | Low — may be necessary for API compat |
| Context window lookup | ~70 | Low — stable per model family |
| Model aliases/mappings | ~30 | Medium — logic coupling |
| **Total** | **~160** | **High** — spread across 20+ files |

---

## 10. Hardcoded Provider Names Catalog

### 10.1 `core/configuration/service.py` (3 providers)

| Line | Provider(s) | Type |
|------|------------|------|
| 48-68 | `ollama`, `openai`, `anthropic` | Default provider configs |
| 386 | `("openai", "anthropic")` | Cloud fallback order |

### 10.2 `core/model_providers/hybrid.py` (6 providers)

| Line | Provider(s) | Type |
|------|------------|------|
| 52-56 | `VISION→openai`, `CODING→anthropic`, `REASONING→anthropic` | Preferred providers |
| 154 | `["openai", "anthropic", "openrouter", "groq", "gemini"]` | Cloud fallback order |
| 207 | `["ollama", "openai", "anthropic", "openrouter", "groq", "gemini"]` | Full fallback order |

### 10.3 `core/model_providers/router.py` (6 providers)

| Line | Provider(s) | Type |
|------|------------|------|
| 86-93 | `ollama, openai, anthropic, gemini, groq, openrouter` | Provider→class mapping |
| 136 | `ollama, openai, anthropic, gemini, groq, openrouter` | Health check order |
| 149 | `["openai", "anthropic", "openrouter", "groq", "gemini"]` | Cloud resolution order |

### 10.4 `core/model_providers/base.py` (6 providers)

| Line | Provider(s) | Type |
|------|------------|------|
| 82-88 | `ollama, openai, anthropic, gemini, groq, openrouter` | health_check_all() |

### 10.5 `core/providers/bootstrap.py` (12 providers)

| Line | Provider(s) | Type |
|------|------------|------|
| 14-33 | forge, browser, research, automation, messaging, deployment, workspace, github, email, desktop | Internal registration |
| 38-53 | claude_code, codex | External registration |

### 10.6 `core/llm_failover.py` (22 providers)

| Line | Provider(s) | Type |
|------|------------|------|
| 38-43 | 22 provider names in `_KNOWN_LLM_PROVIDERS` | Auto-discovery filter |

### 10.7 `core/agent_registry.py` (8 agents)

| Line | Agent(s) | Type |
|------|----------|------|
| 113-178 | codex, aider, opencode, gemini, copilot, gh, jules, shell | Hardcoded agent definitions |
| 189-216 | Task→agent name mapping | Capability routing |

### 10.8 `core/doctor.py` (5 providers)

| Line | Provider(s) | Type |
|------|------------|------|
| 109 | OPENAI, ANTHROPIC, GEMINI, GROQ, OPENROUTER | Health check list |

### 10.9 `core/agent_launcher.py` (6 providers)

| Line | Provider(s) | Type |
|------|------------|------|
| 38-70 | gemini, claude/opencode, codex, aider, copilot, gh | Provider→API key mapping |

### 10.10 `core/providers/store.py` (12 providers)

| Line | Provider(s) | Type |
|------|------------|------|
| Entire file | claude-code, codex, jules, aider, gemini-cli, playwright, docker, telegram, vercel, supabase | Known external providers |

---

## 11. One Future Architecture

### 11.1 Principle

**Business logic must never know model names or provider names.**

The architecture must have:
1. A **single** Capability→Provider→Model resolution chain
2. All model/provider names in **config only** (env vars, config files, settings store)
3. Provider selection by **evidenced-based scoring** (matching `ProviderRouter`)
4. Model selection by **capability tag**, not by name

### 11.2 The Unified Resolution Chain

```
USER REQUEST / TASK
       │
       ▼
┌──────────────────────────────────────┐
│ 1. Capability Registry               │
│    intent → capability tag           │
│    (e.g. "write code" → "coding")    │
└──────────────┬───────────────────────┘
               │
               ▼
┌──────────────────────────────────────┐
│ 2. Unified Router (NEW)              │
│    capability tag →                  │
│      (Provider, model_name)          │
│                                      │
│    ├─ Evidence-based scoring ────────┤
│    │  (matching ProviderRouter)      │
│    │  - historical_success           │
│    │  - benchmark_quality            │
│    │  - health, latency, cost        │
│    │  - budget, offline_avail        │
│    ├─ Config-driven weights ─────────┤
│    └─ Calibration engine ────────────┘
└──────────────┬───────────────────────┘
               │
               ▼
┌──────────────────────────────────────┐
│ 3. Provider Adapter Layer            │
│    (unified ModelProvider +          │
│     ExecutionProvider under          │
│     single ABC)                      │
└──────────────┬───────────────────────┘
               │
               ▼
┌──────────────────────────────────────┐
│ 4. Execution                         │
│    provider.execute(model, task)     │
└──────────────────────────────────────┘
```

### 11.3 Concrete Migration Plan

#### Phase A: Unified Router (replace 5 routers)

Create `core/router/` with:
- `UnifiedRouter` — single evidence-based selector
- `TaskProfile` — config for each capability (weights, fallback chain, budget)
- `DecisionRecorder` — audit trail (already exists at `core/providers/feedback/`)

**Replace**:
- `ConfigurationService.resolve()` → delegate to UnifiedRouter
- `ModelRouter.select()` → delegate
- `HybridModelPlatform._pick_for_mode()` → delegate
- `LiteLLM Router` → keep for LiteLLM integration, but model selection through UnifiedRouter
- `FailoverRouter._resolve_model()` → delegate

#### Phase B: Single Provider ABC

Merge `ModelProvider` and `ExecutionProvider` under a single ABC:
```python
class Provider(ABC):
    provider_id: str
    capabilities: list[str]
    async def execute(capability: str, input: Any, **kwargs) -> Result
    async def health() -> ProviderHealth
    async def estimate_cost(capability: str) -> float
    async def estimate_latency(capability: str) -> float
```

#### Phase C: Config-Only Model Names

Remove every hardcoded model name from `.py` files:

| Source | Migration Target |
|--------|-----------------|
| `_local_model_for_capability()` | Config entries per capability |
| `_resolve_for_provider()` | Config entries per provider |
| `ROLE_MODELS` in `llm_router.py` | Config entries |
| `MODEL_FALLBACKS` | Config entries + auto-discovery |
| `DEFAULT_MODEL_ENDPOINTS` | Env var `OLLAMA_MODEL_ENDPOINTS` |
| `ANTHROPIC_MODELS` in provider | API-based model discovery |
| `_models` in `OpenAIProvider` | API-based model discovery |
| `KNOWN_CONTEXT_WINDOWS` | API-based context discovery |
| `_MAX_COMPLETION_TOKENS_MODELS` | Provider metadata |
| `_FIXED_TEMPERATURE_MODELS` | Provider metadata |
| `_THINKING_MODEL_PATTERNS` | Provider metadata |

#### Phase D: Clean Up Configuration

| Action | Detail |
|--------|--------|
| Delete `core/config.py` | Already a dead shim |
| Delete `core/config_schema.py` | Deprecated dataclasses; merge into SettingsStore |
| Delete `core/config_registry.py` Config class | Keep `_REGISTRY` metadata, delete `Config` singleton |
| Remove `core/config_init.py` | Inline into `ConfigurationService.load()` |
| Fix `.env.local` semantics | Load `.env.local` last so it overrides `.env` |
| Add file watcher | Watch config files for hot-reload |
| Merge REST endpoints | Single `/api/config` backed by ConfigurationService |

#### Phase E: Provider→Capability Mapping

Replace hardcoded bootstrap imports with manifest-based:
- `register_internal_providers()` → read from `~/.jarvis/providers.json` or built-in manifest
- `register_external_providers()` → already manifest-based, good
- `agent_registry.py` agents → migrate to ExecutionProvider adapters

### 11.4 Target Architecture Diagram

```
┌────────────────────────────────────────────────────────────────────────────┐
│                         CONFIG LAYER                                      │
│  ConfigurationService (canonical) ← SettingsStore (Pydantic)              │
│  ├─ env vars (overridable)                                                │
│  ├─ config files (JSON/YAML)                                             │
│  ├─ settings store (~/.jarvis/settings.json)                             │
│  └─ runtime overrides                                                     │
└─────────────────────────┬──────────────────────────────────────────────────┘
                          │
                          ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                         ROUTER LAYER                                      │
│  UnifiedRouter (single entry point)                                       │
│  ├─ capability tag → (provider, model_name)                              │
│  ├─ evidence-based scoring (8 dimensions)                                │
│  ├─ config-driven weights                                                 │
│  ├─ calibration engine                                                    │
│  ├─ decision recorder                                                     │
│  └─ fallback chain (config-only, no hardcoded names)                     │
└─────────────────────────┬──────────────────────────────────────────────────┘
                          │
                          ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                      PROVIDER LAYER                                      │
│  Provider (unified ABC)                                                   │
│  ├─ ModelProvider subclasses (LLM generation)                            │
│  ├─ ExecutionProvider subclasses (functional capabilities)               │
│  └─ External/plugin providers (SDK-based)                                │
└─────────────────────────┬──────────────────────────────────────────────────┘
                          │
                          ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                      INFRASTRUCTURE                                      │
│  ProviderRegistry (capability index)                                      │
│  ProviderMemory (performance history)                                     │
│  ProviderBudgetManager (cost tracking)                                    │
│  BenchmarkStore (quality scores)                                          │
└────────────────────────────────────────────────────────────────────────────┘
```

---

## 12. Action Summary

### Priority 1: Create UnifiedRouter

Replace 5 overlapping resolution systems with one evidence-based router. Zero hardcoded model/provider names.

### Priority 2: Remove Model Names from Business Logic

Every file listed in Section 9 must move model names to config. Target files:
- `core/configuration/service.py` — `_local_model_for_capability()` and `_resolve_for_provider()` → config entries
- `core/llm_router.py` — `ROLE_MODELS`, `MODEL_FALLBACKS` → config entries
- `core/llm_failover.py` — `_resolve_model()` → config entries
- `core/llm_providers.py` — `_MAX_COMPLETION_TOKENS_MODELS` et al → provider metadata

### Priority 3: Remove Provider Names from Business Logic

Every file listed in Section 10 must use the ProviderRegistry capability index instead of hardcoded provider lists.

### Priority 4: Clean Up Legacy Config

Delete `core/config.py`, `core/config_schema.py`, clean up `core/config_registry.py`.

### Priority 5: Single Provider ABC

Merge `ModelProvider` and `ExecutionProvider` under one unified interface.

### Priority 6: Fix Configuration Gaps

File watcher, unified REST endpoints, fix `.env.local` semantics, cross-validate defaults.

---

*End of Phase 7 — READ ONLY audit. No code was modified.*
