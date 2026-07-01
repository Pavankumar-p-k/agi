# ADR-001: Provider Lifecycle Pipeline

**Status:** Accepted · Frozen  
**Date:** 2026-06-29  
**Author:** JARVIS Architecture Team  

---

## Context

JARVIS loads providers at startup through `bootstrap_providers()`. Before Phase A, the
registration path was an unstructured sequence of `register()` calls:

```python
provider_registry.register(ForgeProvider(), priority=10)
provider_registry.register(BrowserProvider(), priority=10)
```

Each call directly inserted into `ProviderRegistry`, making it externally visible
immediately. If a provider failed mid-load, the registry contained a partially
built state — some providers registered, others missing, with no indication of
which had failed or why.

The system needed:

1. A **deterministic pipeline** with per-stage validation, not a monolithic
   registration function.
2. **Failure isolation** — a broken provider must never prevent working providers
   from loading.
3. **Observability** into why a provider was rejected (diagnostics, not logs).
4. **Retry support** — a transient failure should quarantine, not permanently
   reject.
5. **Atomic registration** — no caller should ever see a half-built registry.

---

## Decision

### 1. Stage objects replace monolithic registration

**Before:** One large function with nested `if/elif/else` for validation, loading,
capability scanning, and registration.

**After:** Nine discrete stage classes, each with one responsibility:

```
DiscoveryStage           — find and parse the manifest file
ManifestValidationStage  — validate v2 schema or convert v1→v2
CompatibilityStage       — check SDK version, transport, entrypoint
PermissionDeclarationStage — validate declared permission IDs
ProviderLoadStage        — import and instantiate the adapter module
SelfVerificationStage    — call health() + capabilities(), compare vs manifest
CapabilityDiscoveryStage — enumerate runtime capabilities from instantiated provider
RuntimePermissionRegistrationStage — grant permissions in PermissionManager
AtomicRegistrationStage  — commit to ProviderRegistry via TemporaryRegistry
```

Each stage returns a `StageResult(success, next_state, diagnostics, metadata)`.
Stages **never throw exceptions** for flow control — errors are encoded in
`StageResult`. This makes the pipeline fully deterministic.

### 2. Five-state lifecycle replaces boolean flags

**Before:** A provider was either "registered" or "not registered."

**After:** Five explicit states:

| State | Meaning |
|-------|---------|
| DISCOVERED | Manifest file found on disk |
| VALIDATED | All pipeline stages passed |
| ACTIVE | Atomic commit completed |
| QUARANTINED | Failure with recovery potential |
| REJECTED | Permanent validation failure |

A provider in QUARANTINED preserves full diagnostics: failing stage, exception,
retry count, last healthy fingerprint. If the fingerprint changes (indicating a
version update), the provider is retried automatically.

### 3. TemporaryRegistry enables atomic registration

**Why:** Direct `provider_registry.register()` calls made every provider
externally visible the moment it was called. A failure after the 5th of 9
providers left 4 registered, 5 unregistered, and no audit trail.

**Solution:** Providers accumulate in `TemporaryRegistry._staged` during
pipeline execution. Only `commit()` transfers them to `ProviderRegistry` and
`CapabilityRegistry`. External callers (router, planner, capability graph) see
only ACTIVE providers.

Failure at any point: `TemporaryRegistry.unstage()` removes the provider.
No partial state is ever visible.

### 4. Quarantine replaces silent skip

**Before:** A failing provider was silently skipped with a log message. No
diagnostics, no retry mechanism, no way to inspect the failure later.

**After:** Failed providers transition to QUARANTINED with a full diagnostic
record. The `QuarantineStore` is JSON-persisted to `~/.jarvis/quarantine/`.
Administrators can inspect, clear, or manually promote quarantined providers.

Quarantine supports three recovery paths:

| Path | Trigger |
|------|---------|
| Version update | New fingerprint != quarantined fingerprint |
| Admin override | Manual promote via CLI/API |
| Retry limit exhausted | Permanent REJECTED |

### 5. Pipeline version is part of the fingerprint

The fingerprint includes `pipeline_version` so that a pipeline update
invalidates all previous fingerprints. This prevents stale quarantine records
from blocking updated providers.

### 6. Backward compatibility is mandatory

v1 manifests (those without `sdk_version`) are detected and converted at load
time via `v1_to_v2()`. The conversion is a runtime shim — v1 manifests are
never mutated on disk. All existing providers (`ForgeProvider`, `BrowserProvider`,
etc.) continue to load through the same pipeline with zero code changes.

---

## Consequences

### Positive

1. **Failure isolation proven** — the `test_bad_provider_does_not_block_good_provider`
   test confirms that a broken provider (invalid transport, unknown platform,
   wildcard permissions) does not prevent a valid provider from reaching ACTIVE.

2. **Deterministic startup** — same manifests × same files × same pipeline version
   → identical ACTIVE set every time. Proven by fingerprint comparison tests.

3. **Diagnostics-first design** — every rejection and quarantine carries a
   structured diagnostic trail (stage, reason, fingerprint, timestamp). No more
   digging through log files to understand why a provider failed.

4. **Atomicity** — `TemporaryRegistry` guarantees that either every provider
   commits or none do (within a single pipeline run). The registry is never in
   an intermediate state.

5. **Extensibility** — adding a new stage (e.g., `SandboxValidationStage`) is a
   single class with a `run()` method. No existing stage code needs to change.

### Negative

1. **Pipeline is synchronous** — `asyncio.run()` wraps async `health()` calls.
   When JARVIS becomes fully async, the pipeline should become async from top
   to bottom. This is deferred to Phase B.

2. **Persistence coupling** — `QuarantineStore` writes to `~/.jarvis/quarantine/`.
   If JARVIS moves to a different data directory scheme, quarantine must be
   migrated.

3. **No hot reload** — The pipeline runs once at boot. Adding a provider after
   boot requires a full re-pipeline. This is acceptable for Phase A but should
   be addressed before marketplace support.

---

## Rejected Alternatives

### 1. Monolithic registration function

Rejected because: No failure isolation, no diagnostics, no retry, no atomicity.
Any failure cascaded to the entire boot sequence.

### 2. Decorator-based registration

Rejected because: Decorators run at import time, making failure handling
impossible. Import order becomes an implicit dependency. Tests cannot
easily mock or reorder providers.

### 3. Event-driven pipeline

Rejected because: Event-based registration makes determinism harder to prove.
The synchronous stage pipeline is simpler, easier to trace, and easier to test.
Event-driven can be layered on top later if needed.

### 4. SQLite-backed quarantine

Rejected because: Quarantine data must survive a database reset. JSON files
in `~/.jarvis/quarantine/` are independent of the workflow database, making
them resilient to DB corruption or migration.

---

## Related Documents

- [Provider Manifest v2 Specification](../specs/provider-manifest-v2.md) — frozen
- `provider_sdk/stages.py` — stage implementations
- `provider_sdk/lifecycle.py` — ProviderLifecycleManager
- `provider_sdk/quarantine.py` — QuarantineStore
- `provider_sdk/registration.py` — TemporaryRegistry
- `core/providers/bootstrap.py` — boot sequence wiring
- `tests/architecture/` — 65 merge gate tests

---

## Architecture Diagram

```
                         Bootstrap
                             │
                    ┌────────▼────────┐
                    │  Pipeline       │
                    │  (9 stages)     │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │TemporaryRegistry│
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │ ProviderRegistry │
                    │(external visible)│
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
         Router         Planner      CapabilityGraph
```

```
                 Pipeline Stage Flow

Discovery ──► Manifest ──► Compat ──► Permissions
    │          Validation    Check      Declaration
    ▼
 Provider ──► Self ──► Capability ──► Runtime ──► Atomic
  Load      Verify    Discovery     Perms       Commit
                                     │
                                     ▼
                              QUARANTINED
                               (on failure)
```
