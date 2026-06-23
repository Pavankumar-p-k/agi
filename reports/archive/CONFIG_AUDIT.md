# CONFIG AUDIT

Trace every configuration path: file → env var → default → runtime override.
Determine which settings are real, which are ignored, and which are duplicated.
All claims verified by reading actual code with file:line references.

---

## Config Architecture

```
                    ┌──────────────────────┐
                    │   CLI --flag args    │  (highest priority)
                    └──────────┬───────────┘
                               │
                    ┌──────────▼───────────┐
                    │   Environment Vars    │
                    │   JARVIS_* / OPENAI_  │
                    └──────────┬───────────┘
                               │
                    ┌──────────▼───────────┐
                    │  ~/.jarvis/          │
                    │  settings.json       │  (persisted at runtime)
                    └──────────┬───────────┘
                               │
                    ┌──────────▼───────────┐
                    │  config/default.yaml  │  (shipped with code)
                    │  config/*.yaml        │
                    └──────────┬───────────┘
                               │
                    ┌──────────▼───────────┐
                    │   Code Defaults       │  (lowest priority)
                    │   (config_schema.py)  │
                    └──────────────────────┘
```

---

## Config Systems: The Dual Problem

### System A: ConfigRegistry (Runtime)

**File:** `core/config_registry.py`

**Mechanism:** Singleton with 5-level priority chain:
1. Runtime overrides (in-memory dict)
2. Environment variables (`JARVIS_*`, `OPENAI_API_KEY`, etc.)
3. `~/.jarvis/settings.json`
4. `config/*.yaml`
5. Code defaults (hardcoded in `ConfigEntry` definitions)

**Fields:** 50+ `ConfigEntry` definitions across categories:
- LLM models (11 entries)
- Voice (30+ entries)
- Failover (6 entries)
- Tools (3 entries)
- Memory (3 entries)
- Server (4 entries)
- Ollama (3 entries)

**Evidence:** `config_registry.py:57-161` — all ConfigEntry definitions.

### System B: SettingsStore (REST API)

**File:** `core/settings/store.py`

**Mechanism:** Pydantic model (`JarvisSettings`) persisted as `~/.jarvis/settings.json`.
- Has `load()` / `save()` / `get()` / `set()` / `reset()` / `export()` / `import_from_json()`
- Validates types via pydantic
- Publishes `settings.changed` events on modification

**Fields:** 10+ sub-models:
- `LLMSettings`, `AGISettings`, `DNDSettings`, `MemorySettings`
- `VoiceSettings`, `ServerSettings`, `LoggingSettings`, `UISettings`
- API keys for 10+ services

### System C: JarvisConfig (Schema)

**File:** `core/config_schema.py`

**Mechanism:** Pydantic dataclass with `_load_all()` merging YAML + JSON + env vars + CLI overrides.
- `JarvisConfig` - top-level config with sub-configs:
  - `ServerConfig`, `DatabaseConfig`, `OllamaConfig`, `PluginConfig`
  - `HardwareConfig`, `BuildSystemConfig`, `LLMConfig`, `LLMFallback`
  - `SearchConfig`, `ResearchConfig`, `FeatureConfig`, `VoiceConfig`
  - `SandboxConfig`, `FailoverConfig`, `AuthProfile`
- Singleton: `jarvis_config = JarvisConfig.load()`

---

## Settings Overlap Matrix

| Setting | ConfigRegistry | SettingsStore | JarvisConfig | Notes |
|---------|---------------|---------------|--------------|-------|
| `chat_model` | ✅ `llm.chat_model` | ✅ `LLMSettings.default_model` | ✅ `LLMConfig.chat_model` | **Triplicated** |
| `code_model` | ✅ `llm.code_model` | ✅ `LLMSettings.coder_model` | ✅ `LLMConfig.code_model` | **Triplicated** |
| `server.host` | ✅ `server.host` | ✅ `ServerSettings.host` | ✅ `ServerConfig.host` | **Triplicated** |
| `server.port` | ✅ `server.port` | ✅ `ServerSettings.port` | ✅ `ServerConfig.port` | **Triplicated** |
| `voice.enabled` | ✅ `voice.enabled` | ✅ `VoiceSettings.enabled` | ✅ `VoiceConfig.stt_enabled`/`tts_enabled` | **Quadruplicated** |
| `voice.stt_provider` | ✅ `voice.stt_provider` | ✅ `VoiceSettings.stt_model` | ✅ `VoiceConfig.stt_provider` | **Triplicated** |
| `voice.tts_provider` | ✅ `voice.tts_provider` | ✅ `VoiceSettings.tts_engine` | ✅ `VoiceConfig.tts_provider` | **Triplicated** |
| `ollama.base_url` | ✅ `ollama.base_url` | ✅ `LLMSettings.ollama_host` | ✅ `OllamaConfig.url` | **Triplicated** |
| `memory.backend` | ✅ `memory.provider` | ✅ `MemorySettings.backend` | — | **Duplicated** |
| `openai_api_key` | ✅ `failover.openai_api_key` | ✅ `JarvisSettings.openai_api_key` | ✅ `get_api_key("openai")` | **Triplicated** |

**Total duplicated settings: ~30 out of ~80 unique settings.**

---

## Orphan Settings (Declared But Never Read)

Settings that are defined in config files or models but never accessed in runtime code:

| Setting | Declared In | Read By | Status |
|---------|-------------|---------|--------|
| `DNDSettings.dnd_mode` | `settings/schema.py:40` | Not found in runtime code | **IGNORED** |
| `DNDSettings.dnd_hours` | `settings/schema.py:41` | Not found in runtime code | **IGNORED** |
| `AGISettings.confidence_threshold` | `settings/schema.py:34` | Not found in runtime code | **IGNORED** |
| `AGISettings.max_agents` | `settings/schema.py:35` | Not found in runtime code | **IGNORED** |
| `HardwareConfig.face_recognition_model` | `config_schema.py:74` | Not found in runtime code | **IGNORED** |
| `HardwareConfig.face_detection_backend` | `config_schema.py:75` | Not found in runtime code | **IGNORED** |
| `ResearchConfig.max_tokens` | `config_schema.py:153` | Not found in runtime code | **IGNORED** |
| `ResearchConfig.timeouts` | `config_schema.py:154` | Not found in runtime code | **IGNORED** |
| `FeatureConfig.sensitive_filter` | `config_schema.py:163` | Not found in runtime code | **IGNORED** |
| `FeatureConfig.gallery` | `config_schema.py:164` | Not found in runtime code | **IGNORED** |
| `SandboxPolicy.network` | `config_schema.py:186` | Not found in runtime code | **IGNORED** |
| `SandboxPolicy.memory` | `config_schema.py:189` | Not found in runtime code | **IGNORED** |
| `SandboxPolicy.cpu` | `config_schema.py:190` | Not found in runtime code | **IGNORED** |
| `AuthProfile.cooldown` | `config_schema.py:212` | Not found in runtime code | **IGNORED** |
| `FailoverConfig.cooldown_backoff` | `config_schema.py:220` | Not found in runtime code | **IGNORED** |
| `FeatureConfig.deep_research` | `config_schema.py:161` | Not found in runtime code | **IGNORED** |

---

## Orphan Env Vars

Environment variables declared in config but never read:

| Env Var | Declared In | Read By | Status |
|---------|-------------|---------|--------|
| `JARVIS_VOSK_MODEL_PATH` | `config_registry.py` | Not found in runtime code | **IGNORED** |
| `JARVIS_FIREBASE_CREDENTIALS` | `config_registry.py:54` | Not found in runtime code | **IGNORED** |

---

## Config File Dump

### `config/default.yaml`

Not read directly — contents are merged by `JarvisConfig._load_all()` and `ConfigRegistry`.

### `~/.jarvis/settings.json`

Created at runtime. Schema determined by `JarvisSettings` pydantic model.
Contains: LLM models, voice settings, memory settings, server settings, API keys.

---

## Runtime Override Points

| Override | File:Line | Persists? |
|----------|-----------|-----------|
| CLI `--model` flag | `jarvis.py:35-40` | No (per-command) |
| `SettingsStore.set()` | `settings/store.py:161` | Yes (JSON file) |
| `ConfigRegistry.set()` | `config_registry.py:318` | Optional (JSON file) |
| `config_registry.set(persist=True)` | `config_registry.py:341` | Yes (JSON file) |
| API `PUT /api/settings/{key}` | `routes/settings.py:79` | Yes |
| API `PATCH /settings/{key}` | `api/settings_routes.py:35` | Yes |

---

## Config Load Path (Sequence)

| Step | Source | File:Line | Persistence |
|------|--------|-----------|-------------|
| 1 | Code defaults | `config_schema.py:33-220` | Static |
| 2 | `config/default.yaml` | `config_schema.py:320-350` | Static |
| 3 | `~/.jarvis/settings.json` | `config_schema.py:325` | **User-persisted** |
| 4 | `JARVIS_*` env vars | `config_schema.py:361-371` | Environment |
| 5 | CLI overrides | `config_schema.py:374` | Per-run |
| 6 | `config_registry.load()` | `config_registry.py:238-280` | Merges all sources |

---

## Recommendations

1. **Consolidate to one config system** — eliminate duplication between `config_registry`, `settings/store.py`, and `config_schema.py`
2. **Remove orphan settings** — delete settings never read by any runtime code (or implement the features they control)
3. **Add settings usage tracking** — log which settings are accessed to identify more orphans
4. **Standardize env var naming** — currently mixed: `JARVIS_*`, `OPENAI_*`, `ANTHROPIC_*`, `OLLAMA_*`
5. **Add config validation** — warn on unknown/unused settings
6. **Single source of truth** — choose `ConfigRegistry` as the canonical runtime source and deprecate the others
