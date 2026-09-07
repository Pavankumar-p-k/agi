# ADR-001: ConfigurationService is the Sole Configuration Owner

**Status:** Accepted  
**Date:** 2026-07-05  
**Phase:** 1g  

## Context

The project had four overlapping configuration systems:
- `core/config_schema.py` (JarvisConfig — dataclass, loaded at import time)
- `core/configuration/service.py` (ConfigurationService — runtime, YAML+JSON+env+SettingsStore)
- `core/config_registry.py` (Config — bridge delegating to ConfigurationService)
- `core/config.py` (module-level constants — import-time bindings from JarvisConfig)

Each loaded overlapping sources independently, leading to stale values and inconsistent defaults.

## Decision

**ConfigurationService (`core.configuration.configuration`) is the canonical configuration API.**

1. `config_schema.py` → backward-compat shim delegating all attribute access to `configuration.get()`  
2. `config.py` → `__getattr__`-based module that resolves from `configuration.get()` at runtime  
3. `config_registry.py` → remains as the schema/entry registry used by ConfigurationService and the settings API  
4. New code MUST use `from core.configuration import configuration; configuration.get("key")`  

## Consequences

**Positive:**
- Single resolution chain: override > env > flat config > SettingsStore > auto-resolve > default
- Consistent defaults across all consumers
- `config.yaml`, `data/settings.json`, env vars, and `~/.jarvis/settings.json` all feed into one pipeline
- Settings API routes return consistent values

**Negative:**
- ~15 production files still import from deprecated shims (documented in `tests/architecture/test_enforce_canonical.py`)
- `core/config.py` constant resolution is lazy (happens on first `import` of each constant, not at module init)

**Migration:** Legacy shims to be removed in v4.0.
