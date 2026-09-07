# Configuration Audit — Phase 5 (Document 13)

> **Purpose:** Trace every configuration source, precedence hierarchy, runtime override mechanism, and config schema in the system. Identify sources of config drift, missing validation, and stale values.
>
> **Scope:** All configuration paths: YAML files, JSON files, environment variables, SQLite-stored config, in-memory overrides, CLI arguments, and hardcoded defaults.

---

## Table of Contents

1. [Configuration Sources Overview](#1-configuration-sources-overview)
2. [Configuration Registry & Schema Systems](#2-configuration-registry--schema-systems)
3. [Precedence Hierarchy & Resolution](#3-precedence-hierarchy--resolution)
4. [Configuration File Inventory](#4-configuration-file-inventory)
5. [Environment Variable Inventory](#5-environment-variable-inventory)
6. [Config Mutations & Runtime Overrides](#6-config-mutations--runtime-overrides)
7. [Findings & Recommendations](#7-findings--recommendations)

---

## 1. Configuration Sources Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                     FOUR CONFIG SYSTEMS                              │
├──────────────────┬───────────────────┬──────────────────┬───────────┤
│  ConfigRegistry  │  SettingsStore    │  Environment     │  CLI Args │
│  (core/          │  (core/settings/  │  (os.environ)    │  (argparse│
│  config_registry │  store.py)        │                  │   /click) │
│  .py)            │                   │                  │           │
├──────────────────┼───────────────────┼──────────────────┼───────────┤
│ Backed by:       │ Backed by:        │ Backed by:       │ Volatile  │
│ YAML + JSON      │ ~/.jarvis/        │ Process env      │ (per-run) │
│ files + SQLite   │ settings.json     │ block            │           │
│                   │                   │                  │           │
│ Access:          │ Access:           │ Access:          │ Access:   │
│ configuration    │ SettingsStore     │ os.environ.get() │ parsed    │
│ .get() / .set()  │ .get() / .set()   │                  │ args      │
│                   │                   │                  │           │
│ Schema:          │ Schema:           │ Schema:          │ None      │
│ ConfigEntry      │ Pydantic          │ _REGISTRY_MAP    │           │
│ dataclass        │ BaseModel         │ in               │           │
│                   │                   │ config_registry  │           │
└──────────────────┴───────────────────┴──────────────────┴───────────┘
```

---

## 2. Configuration Registry & Schema Systems

### 2.1 ConfigRegistry (`core/config_registry.py`)

A centralized registry of all configuration keys with their metadata:

```python
@dataclass
class ConfigEntry:
    key: str                         # "server.port"
    default: Any                     # 8000
    type: type | str                 # int
    description: str                 # "Port for the HTTP server"
    env_var: str | None              # "JARVIS_PORT"
    category: str                    # "server", "memory", "auth", etc.
    sensitive: bool = False          # If True, mask in logs
    immutable: bool = False          # If True, cannot be changed at runtime
```

Keys are registered in `_REGISTRY_MAP` — a module-level dict. Example entries:

```python
_REGISTRY_MAP = {
    "server.port": ConfigEntry("server.port", 8000, int, "HTTP server port", "JARVIS_PORT", "server"),
    "server.host": ConfigEntry("server.host", "0.0.0.0", str, "HTTP server host", "JARVIS_HOST", "server"),
    "server.debug": ConfigEntry("server.debug", False, bool, "Debug mode", "JARVIS_DEBUG", "server"),
    "memory.tiered.enabled": ConfigEntry("memory.tiered.enabled", True, bool, "Enable tiered memory", None, "memory"),
    "memory.tiered.hot_size": ConfigEntry("memory.tiered.hot_size", 10, int, "Hot tier max entries", None, "memory"),
    "auth.token_expiry_hours": ConfigEntry("auth.token_expiry_hours", 168, int, "Session token TTL", "JARVIS_TOKEN_EXPIRY", "auth"),
    "auth.session_file": ConfigEntry("auth.session_file", "sessions.json", str, "Session persistence file", None, "auth"),
    "planning.max_steps": ConfigEntry("planning.max_steps", 10, int, "Max planning steps", None, "planning"),
    "workflow.max_retries": ConfigEntry("workflow.max_retries", 3, int, "Workflow step max retries", None, "workflow"),
    "openai.api_key": ConfigEntry("openai.api_key", "", str, "OpenAI API key", "OPENAI_API_KEY", "llm", True),
    "openai.model": ConfigEntry("openai.model", "gpt-4", str, "OpenAI model name", "OPENAI_MODEL", "llm"),
    # ... 50+ more entries
}
```

### 2.2 ConfigSchema (`core/config_schema.py`)

A Pydantic-based schema layer that sits **alongside** ConfigRegistry:

```python
class ConfigSchema(BaseModel):
    server: ServerConfig       # Pydantic nested model
    memory: MemoryConfig
    auth: AuthConfig
    workflow: WorkflowConfig
    planning: PlanningConfig
    llm: LLMConfig
    monitoring: MonitoringConfig
    features: FeatureFlags

    class ServerConfig(BaseModel):
        port: int = 8000
        host: str = "0.0.0.0"
        debug: bool = False
        cors_origins: list[str] = ["*"]

    class MemoryConfig(BaseModel):
        tiered_enabled: bool = True
        hot_size: int = 10
        # ... more
```

### 2.3 Relationship Between Registry and Schema

- **ConfigRegistry** (`config_registry.py`): flat key-value store with metadata (env_var, type, sensitive flag). Used by `configuration.get()` at runtime.
- **ConfigSchema** (`config_schema.py`): Pydantic structured model. Used for validation and type coercion.
- **These two systems are NOT integrated.** `ConfigSchema` defines defaults independently from `_REGISTRY_MAP`. A change to one does not automatically propagate to the other.

---

## 3. Precedence Hierarchy & Resolution

### 3.1 Resolution Order

When `configuration.get("server.port")` is called:

```
1. In-memory overrides         ← configuration.set() call (highest)
       │
2. Environment cache           ← os.environ, scanned at load time
       │
3. Flat config (YAML+JSON)     ← _flatten() of config_yaml + settings.json
       │
4. SettingsStore               ← ~/.jarvis/settings.json (Pydantic-backed)
       │
5. Auto-resolve capability     ← dynamic model routing
       │
6. Registry default            ← _REGISTRY_MAP[key].default
       │
7. Caller default              ← get(key, default=...) argument (lowest)
```

### 3.2 Environment Variable Scanning

```python
def _scan_env_vars():
    for entry in _REGISTRY_MAP.values():
        if entry.env_var and entry.env_var in os.environ:
            _env_cache[entry.key] = os.environ[entry.env_var]
```

**Scanned ONCE at module load time.** Environment variables set after import are NOT picked up unless `configuration.reload()` is called.

### 3.3 YAML Loading

```python
def _load_yaml():
    config = {}
    yaml_path = os.environ.get("JARVIS_CONFIG", "config.yaml")
    if Path(yaml_path).exists():
        with open(yaml_path) as f:
            config = yaml.safe_load(f)
    json_path = Path("data/settings.json")
    if json_path.exists():
        with open(json_path) as f:
            json_config = json.load(f)
            config = _deep_merge(config, json_config)
    return config
```

### 3.4 SettingsStore

```python
class SettingsStore:
    path: Path = Path.home() / ".jarvis" / "settings.json"
    _settings: dict = {}

    def load(self):
        if self.path.exists():
            self._settings = json.loads(self.path.read_text())
        else:
            self._settings = {}

    def get(self, key: str, default=None):
        keys = key.split(".")
        val = self._settings
        for k in keys:
            if isinstance(val, dict):
                val = val.get(k)
            else:
                return default
        return val if val is not None else default

    def set(self, key: str, value):
        keys = key.split(".")
        target = self._settings
        for k in keys[:-1]:
            target = target.setdefault(k, {})
        target[keys[-1]] = value
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._settings, indent=2))
```

---

## 4. Configuration File Inventory

### 4.1 YAML Files

| File | Path | Contents | Always Loaded? |
|------|------|----------|---------------|
| `config.yaml` | Project root | Main config: server, auth, memory, workflow, llm, plugins | Yes (or JARVIS_CONFIG override) |
| `alembic.ini` | Project root | DB migration connection strings | Only by Alembic CLI |
| `.opencode/config.yaml` | Project root | opencode tool config | Only by opencode |

### 4.2 JSON Files

| File | Path | Contents | Always Loaded? |
|------|------|----------|---------------|
| `data/settings.json` | Project root | User-facing settings (runtime overrides) | Yes (merged into YAML) |
| `~/.jarvis/settings.json` | User home | Persistent user config (SettingsStore) | Yes (lower priority) |
| `sessions.json` | Project root | Auth session persistence | Yes (loaded by AuthManager) |
| `auth.json` | Project root | Auth config (users, passwords) | Yes (loaded by AuthManager) |

### 4.3 SQLite-Based Config

| Database | Table | Purpose |
|----------|-------|---------|
| `system.db` | `settings` | Key-value config persisted via SQLAlchemy |
| `~/.jarvis/settings.db` | settings | SettingsStore legacy support |

---

## 5. Environment Variable Inventory

### 5.1 Canonical Env Vars (from _REGISTRY_MAP)

| Env Var | Config Key | Default | Purpose |
|---------|-----------|---------|---------|
| `JARVIS_PORT` | server.port | 8000 | HTTP server port |
| `JARVIS_HOST` | server.host | 0.0.0.0 | HTTP bind address |
| `JARVIS_DEBUG` | server.debug | false | Debug mode |
| `JARVIS_WORKERS` | server.workers | 1 | HTTP worker count |
| `JARVIS_LOG_LEVEL` | logging.level | INFO | Log verbosity |
| `JARVIS_CONFIG` | loader.path | config.yaml | Config file path |
| `JARVIS_DATA_DIR` | storage.data_dir | ./data | Data directory |
| `JARVIS_TOKEN_EXPIRY` | auth.token_expiry_hours | 168 | Session TTL |
| `JARVIS_MAX_TOKENS` | llm.max_tokens | 4096 | Max LLM response tokens |
| `JARVIS_TEMPERATURE` | llm.temperature | 0.7 | LLM temperature |
| `OPENAI_API_KEY` | openai.api_key | "" | OpenAI API key |
| `OPENAI_MODEL` | openai.model | gpt-4 | OpenAI model ID |
| `ANTHROPIC_API_KEY` | anthropic.api_key | "" | Anthropic API key |
| `ANTHROPIC_MODEL` | anthropic.model | claude-3-opus | Anthropic model ID |
| `OLLAMA_BASE_URL` | ollama.base_url | http://localhost:11434 | Ollama server URL |
| `OLLAMA_MODEL` | ollama.model | llama3 | Ollama model ID |
| `MEM0_API_KEY` | mem0.api_key | "" | Mem0 API key |
| `QDRANT_URL` | vector_store.url | localhost | Qdrant server URL |
| `AUTH_TYPE` | auth.type | session | Auth backend type |
| `SECRET_KEY` | auth.secret_key | (random) | Session signing key |

### 5.2 Non-Registered Env Vars (read directly, not in _REGISTRY_MAP)

| Env Var | Where Read | Purpose |
|---------|-----------|---------|
| `PATH` | Various shell tools | Tool execution path |
| `HOME` | Path resolution | User home directory |
| `USERPROFILE` | Path resolution (Windows) | User home directory |
| `APPDATA` | Path resolution (Windows) | App data directory |
| `PYTHONPATH` | Python interpreter | Module resolution path |

---

## 6. Config Mutations & Runtime Overrides

### 6.1 Mutation Points

| Operation | System | Persisted? | Durable? |
|-----------|--------|------------|----------|
| `configuration.set(key, value)` | ConfigRegistry | Optional (via `persist=True`) | Yes, to `data/settings.json` |
| `SettingsStore.set(key, value)` | SettingsStore | Always | Yes, to `~/.jarvis/settings.json` |
| AuthManager: session add/remove | AuthManager | Always | Yes, to `sessions.json` |
| AuthManager: user add/remove | AuthManager | Always | Yes, to `auth.json` |
| `os.environ[key] = value` | OS | No | Lost on process restart |
| REST API config endpoint | HTTP | Via ConfigRegistry | Yes, to `data/settings.json` |
| REST API settings endpoint | HTTP | Via SettingsStore | Yes, to `~/.jarvis/settings.json` |

### 6.2 Config Drift Points

| Source of Drift | Mechanism | Impact |
|-----------------|-----------|--------|
| `configuration.set()` vs `SettingsStore.set()` called for same key | Different storage backends | One may succeed, other fail = inconsistent state |
| `data/settings.json` and `~/.jarvis/settings.json` both have the same key | Merged in _load_yaml(), but SettingsStore reads independently | Configuration.get() and SettingsStore.get() return different values |
| Env var changed after import | Not rescanned | Stale value used until reload() |
| Config file edited while running | Not watched | Stale until restart |
| REST config endpoint vs settings endpoint | Two endpoints, different backends | User confusion about which endpoint to use |

---

## 7. Findings & Recommendations

### F-1: Two Parallel Config Systems with Different Precedence

ConfigRegistry (flat, YAML+ENV+defaults) and SettingsStore (Pydantic, user home JSON) have overlapping keys but different storage backends and different precedence. A key could exist in both with different values.

**R-1:** Unify into a single ConfigService that owns all three layers:
- **Layer 1** (highest): In-memory runtime overrides
- **Layer 2**: Environment variables (live-read, not cached at import)
- **Layer 3**: YAML config file
- **Layer 4**: Pydantic-validated settings file

Make `configuration.get()`, `configuration.set()`, and `SettingsStore.get/set` all route through the same service.

### F-2: Env Vars Scanned Once at Import Time

`_scan_env_vars()` runs once at module load. Any env var change after import is invisible until `reload()`.

**R-2:** Remove the env cache. Read `os.environ.get(entry.env_var)` on every `get()` call. (Cost: ~50 dict lookups per `get()` — negligible.)

### F-3: ConfigSchema and ConfigRegistry Have Duplicate Defaults

A key's default is defined in both `_REGISTRY_MAP` and `ConfigSchema`. These can diverge.

**R-3:** Make `ConfigSchema` the single source of truth for defaults. Generate `_REGISTRY_MAP` from the Pydantic schema via reflection.

### F-4: Two REST Config Endpoints with Different Backends

The HTTP server exposes both a `/config` endpoint (backed by ConfigRegistry) and a `/settings` endpoint (backed by SettingsStore). Users and tools don't know which to use.

**R-4:** Route both endpoints through the unified ConfigService. Deprecate the SettingsStore endpoint.

### F-5: Config File Not Watched for Changes

If a user edits `config.yaml` while the server is running, changes are not picked up.

**R-5:** Add file watcher (e.g., `watchdog`) for config files. Publish `config.reloaded` event on file change. Live-reload non-immutable values.

### F-6: SQLite-Sourced Config Bypasses Registry

`system.db:settings` table stores key-value pairs read by raw SQLAlchemy queries, bypassing ConfigRegistry entirely.

**R-6:** Route all SQLite config reads through the unified ConfigService. Remove direct `session.query(Setting).all()` calls.

### F-7: Sensitive Values Logged in Plaintext

`openai.api_key` is marked `sensitive=True` in `_REGISTRY_MAP`, but there is no consistent masking mechanism — individual callers are responsible for redaction.

**R-7:** Implement automatic masking in `configuration.get()` for entries with `sensitive=True`. Return `"****"` unless the caller explicitly requests the raw value.
