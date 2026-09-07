# CONFIGURATION AND PROVIDER AUDIT — MJ Architecture

**Generated:** 2026-07-18  
**Scope:** Configuration system, provider registry, capability resolution, model routing  
**Method:** READ ONLY — evidence-based audit

---

## Configuration System Audit

### Canonical Owner
**`core/configuration/service.py:ConfigurationService`** (singleton `configuration`)

### Deprecated/Shim
- `core/config.py` — **DEPRECATED** shim with `__getattr__` delegating to `ConfigurationService`
- `core/config_registry.py` — **DEPRECATED** shim, delegates to `ConfigurationService`
- `core/config_schema.py` — **DEPRECATED** Pydantic models, delegates to `ConfigurationService`

### Configuration Sources (Priority Order)
1. **In-memory overrides** (`_overrides` dict) — `ConfigurationService.set()`
2. **Environment variables** (`_env_cache`) — scanned from `core.config_registry._REGISTRY`
3. **Flat config** (`_flat_config`) — merged from `config.yaml` + `data/settings.json`
4. **SettingsStore** (`~/.jarvis/settings.json`) — persisted user settings
5. **Registry defaults** (`core.config_registry._REGISTRY_MAP`) — hardcoded defaults

### Resolution Chain (`ConfigurationService.get()`)
```
1. _overrides
2. _env_cache (env vars)
3. _flat_config (config.yaml + settings.json)
4. SettingsStore (persisted user settings)
5. Auto-resolve via _CONFIG_TO_CAPABILITY → resolve(capability)
6. Registry default
```

### Secrets Management
- **Encrypted secrets**: `~/.jarvis/api_keys.json` + `oauth_tokens.json` (Fernet encryption via `core.secret_storage`)
- **Loaded at startup** → `_env_cache` → takes priority over config files
- **OAuth tokens**: separate `oauth_tokens.json`, same encryption

### Capability-Based Model Resolution
```python
ConfigurationService.resolve(capability: str) -> str  # returns "provider/model"
```
**Logic:**
1. Check `routing[capability]` preference
2. If `"auto"` → `_auto_resolve()`:
   - Prefer local Ollama if enabled
   - Else cloud (OpenAI/Anthropic) if not offline_only
2. If explicit provider → `_resolve_for_provider()`
3. Fallback to Ollama local default

### Hardcoded Model Mappings (Violations)
**File:** `core/configuration/service.py:431-444`
```python
_local_model_for_capability = {
    "chat": "qwen2.5:7b",
    "code": "qwen2.5-coder:3b",
    "analysis": "qwen2.5:7b",
    "reasoning": "deepseek-r1:1.5b",
    "vision": "moondream:latest",
    "grader": "phi3:mini",
    "embedding": "nomic-embed-text:latest",
    "orchestrator": "qwen2.5:7b",
    "fallback": "tinyllama",
    "cloud": "qwen2.5:7b",
}
```
**Violation:** Business logic knows specific model names. Should be data-driven.

---

## Provider System Audit

### Canonical Components
| Component | File | Status |
|---|---|---|
| `ProviderRegistry` | `core/providers/registry.py` | **CANONICAL** |
| `ProviderRouter` | `core/providers/router.py` | **CANONICAL** |
| `ProviderRouter.select()` | Evidence-based selection | **CANONICAL** |
| `ProviderRegistry.bootstrap()` | `core/providers/bootstrap.py` | **CANONICAL** |

### Provider Registry (`core/providers/registry.py`)
- **Capabilities**: 10 registered (chat, code, analysis, reasoning, vision, grader, embedding, orchestrator, fallback, cloud)
- **Providers registered**: 13 (forge, browser, research, automation, messaging, deployment, workspace, github, email, desktop, ollama, claude_code, codex)
- **Capabilities per provider**: Derived from `ExecutionProvider.capabilities().capability_names`
- **Persistence**: `~/.jarvis/provider_settings/registry.json` (enabled/disabled + priority)

### ProviderRouter Selection Algorithm
```python
select(capability, task, workflow_id, prefer_offline, record_decision):
  1. candidates = registry.get_providers_for_capability(capability)
  2. Filter: enabled, budget, memory.skip, health != DOWN
  3. Score each (7 dimensions):
     - historical_success (Bayesian)
     - benchmark_quality
     - health (1.0/0.5/0.5)
     - latency (1 - latency/10000)
     - cost (1 - cost/10)
     - budget (1 - daily_spent/daily_limit)
     - offline_availability (1.0/0.5)
     - priority (registry priority / 100)
  4. Weights: hist=0.20, bench=0.15, health=0.15, latency=0.15, cost=0.10, budget=0.10, offline=0.05, priority=0.10
  5. Calibration adjustment (additive)
  6. Record decision if record_decision=True
```

### Hardcoded Model Violations (Provider Adapters)
| Provider | File | Hardcoded Models |
|---|---|---|
| **Ollama** | `ollama_provider.py` | `qwen2.5:7b`, `qwen2.5-coder:3b`, `moondream:latest`, `deepseek-r1:1.5b`, `phi3:mini`, `nomic-embed-text:latest` |
| **ClaudeCode** | `claude_code.py` | `claude-3-5-sonnet-20241022` |
| **Codex** | `codex.py` | `gpt-4o` |
| **Forge** | `forge.py` | `qwen2.5-coder:3b` |
| **Browser** | `browser_provider.py` | `moondream:latest` |
| **Research** | `research_provider.py` | `llama3.1:8b` |

---

## Capability Registry Audit

**Canonical:** `core/capability/registry.py:CapabilityRegistry`

### Registered Capabilities (from `models.py`)
| Capability | Category | Risk | Permissions |
|---|---|---|---|
| `coding` | development | medium | filesystem.read, filesystem.write |
| `browser` | automation | high | network.http, desktop.window.read, desktop.mouse.move, desktop.keyboard.type |
| `research` | knowledge | low | network.http |
| `vision` | perception | medium | - |
| `deployment` | operations | critical | network.http, filesystem.read |
| `coding` | development | medium | filesystem.read, filesystem.write |
| `testing` | development | low | filesystem.read, filesystem.write |
| `deployment` | operations | critical | network.http, filesystem.read |
| `documentation` | development | low | filesystem.read, filesystem.write |
| `notifications` | communication | medium | network.http, network.smtp |
| `filesystem` | infrastructure | high | filesystem.read, filesystem.write |
| `desktop` | automation | critical | desktop.window.*, desktop.mouse.*, desktop.keyboard.*, desktop.screen.capture |
| `email` | communication | medium | network.smtp |
| `messaging` | communication | medium | network.http, network.websocket |
| `terminal` | infrastructure | critical | process.list, process.control, filesystem.read |
| `voice` | perception | low | - |
| `speech` | perception | low | - |
| `translation` | knowledge | low | network.http |
| `image_generation` | creative | medium | network.http |
| `automation` | infrastructure | high | all |
| `security` | analysis | medium | filesystem.read |

**Total:** 23 built-in capabilities

---

## Hardcoded Violations (Business Logic Knowing Model Names)

| File | Line | Violation |
|---|---|---|
| `core/configuration/service.py:431-444` | `_local_model_for_capability` | 11 hardcoded model names |
| `core/configuration/service.py:446-455` | `_resolve_for_provider` | OpenAI/Anthropic model names hardcoded |
| `core/providers/adapters/ollama_provider.py` | Lines 40-45 | `qwen2.5:7b`, `qwen2.5-coder:3b`, etc. |
| `providers/adapters/forge.py` | Line 48 | `"qwen2.5-coder:3b"` |
| `models/hybrid_models.py` | Lines 354-362 | `PLAN_MODEL`, `REASON_MODEL`, etc. |
| `core/llm_router.py` | `ROLE_MODELS` dict | 11 role→model mappings |
| `core/llm_router.py` | `MODEL_ALIASES` | 8 aliases |
| `core/providers/adapters/ollama_provider.py` | Lines 17-24 | `_MODEL_ALIASES` |
| `core/providers/adapters/research_provider.py` | `_get_ollama_model_for_task` | `llama3.1:8b`, `moondream:latest` |

---

## Capability Resolution Flow

```
User Request
    ↓
IntentStage.classify() → RequestMode (CHAT/CODEBASE/ACTION/AGENT)
    ↓
CapabilityRegistry.match_goal() → [capability_ids]
    ↓
CapabilitySelectionStage → ProviderRouter.select(capability, task)
    ↓
ProviderRouter.select()
  → Filter: enabled, budget, memory.skip, health!=DOWN
  → Score 7 dimensions (weights: hist=0.20, bench=0.15, health=0.15, latency=0.15, cost=0.10, budget=0.10, offline=0.05, priority=0.10)
  → Calibration adjustment
  → Select highest score
    ↓
ProviderRouter.select() → ExecutionProvider
    ↓
ExecutionStage → Provider.execute(task, context)
```

---

## Provider Capability Matrix

| Provider | Capabilities | Priority | Model(s) |
|---|---|---|---|
| `ollama` | chat, code, analysis, reasoning, vision, grader, embedding, orchestrator, fallback, cloud | 10 (highest) | qwen2.5:7b, qwen2.5-coder:3b, moondream, deepseek-r1:1.5b, etc. |
| `openai` | chat, code, vision, embedding | 50 | gpt-4o, gpt-4o, gpt-4o, text-embedding-3-small |
| `anthropic` | chat, code, vision | 60 | claude-sonnet-4-20250514 |
| `forge` | coding, build, test, validate, repair, analyze, refactor, scaffold | 100 | ollama/qwen2.5-coder:3b |
| `browser` | browser, web, search, scrape | 30 | (via browser tools) |
| `research` | research, analysis, synthesis | 20 | ollama/qwen2.5:7b |
| `automation` | automation, workflow, schedule | 15 | (uses desktop) |
| `messaging` | messaging, email, notify | 20 | (via channels) |
| `deployment` | deploy, build, test, deploy | 80 | - |
| `github` | github, issues, pr, repo | 50 | - |
| `email` | email, send_email | 30 | SMTP |
| `desktop` | desktop, window, mouse, keyboard, screen | 90 | pyautogui |
| `claude_code` | chat, code, analysis, reasoning | 50 | claude-sonnet-4 |
| `codex` | coding, codegen, implement | 70 | gpt-4o |

---

## Violations Summary

| Severity | Count | Examples |
|----------|-------|----------|
| **CRITICAL** (hardcoded models in config) | 9 locations | `config_schema.py`, `config_schema.py:116-134`, `llm_router.py`, `model_providers.py` |
| **HIGH** (provider hardcodes) | 8 providers | Each adapter has hardcoded models |
| **MEDIUM** | Capability→model mapping hardcoded | `_local_model_for_capability()`, `_resolve_for_provider()` |

---

## Future Canonical Architecture

### Configuration
- **Single source**: `ConfigurationService` only
- **Remove**: `core/config.py`, `core/config_registry.py`, `core/config_schema.py`, `core/config.py`
- **Model routing**: Data-driven via `ProviderRouter` + capability registry (no hardcoded models)

### Providers
- **Single registry**: `ProviderRegistry` (canonical)
- **Single router**: `ProviderRouter` with evidence-based selection
- **Provider adapters**: Move hardcoded models → config-driven (capability → model mapping in config)

### Capability Registry
- **Single source**: `core/capability/registry.py:CapabilityRegistry`
- **Dynamic registration**: Plugins can register capabilities
- **Intent mapping**: `_BUILTIN_INTENT_MAP` → capability IDs

---

## Action Items (Priority Order)

1. **CRITICAL**: Remove hardcoded model names from `ConfigurationService._local_model_for_capability()` → use provider capability metadata
2. **CRITICAL**: Provider adapters → read model from config, not hardcoded
3. **HIGH**: Consolidate `core/config.py` + `config_registry.py` + `config_schema.py` → single `ConfigurationService`
4. **HIGH**: Provider adapters → read model from config/registry, not hardcoded
4. **HIGH**: Move hardcoded capability→model mappings to config file
5. **MEDIUM**: Unify `jarvis_config` (Pydantic) + `ConfigurationService` → single source
5. **MEDIUM**: CapabilityRegistry → single source, dynamic registration
5. **MEDIUM**: Unify `llm_router` model routing → `ProviderRouter.select()`

---

*End of Configuration & Provider Audit*