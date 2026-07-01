# Provider Manifest v2 — Specification

**Status:** ❄️ Frozen — no further changes to v2. Future work targets v2.1 or v3.  
**Version:** 2.0  
**Pipeline Version:** 2  
**Last Updated:** 2026-06-29  

---

## 1. Purpose

The Provider Manifest v2 defines the contract between a third-party provider and
the JARVIS runtime. Every provider — whether shipped with core, installed from a
marketplace, or developed locally — must declare a manifest that the provider
lifecycle pipeline validates before loading.

Manifest v2 is **backward compatible** with v1.  All existing v1 manifests
continue to load without modification.  v2 fields are additive.

---

## 2. Schema

### 2.1 Full schema

```yaml
# ── Identity ──────────────────────────────────────────────────────────────
id: "github"                    # required — lowercase, alphanumeric + hyphens
publisher: "jarvis-ai"          # required — globally unique tuple with id
version: "1.2.0"                # required — semver
name: "GitHub Provider"         # required — human-readable display name
description: "..."              # optional

# ── Compatibility ─────────────────────────────────────────────────────────
sdk_version: 2                  # required — manifest schema version (integer)
api_version: 1                  # required — capability API version (integer)
minimum_jarvis: "3.0.0"         # required — semver range
maximum_jarvis: "3.999.999"     # optional — semver upper bound

# ── Transport ─────────────────────────────────────────────────────────────
transport: "python"             # required — python | mcp | http | grpc | cli
entrypoint: "adapters/github.py" # required — path relative to manifest
endpoint: ""                    # optional — URL for http/grpc transports
authentication: {}              # optional — transport auth config (reserved)

# ── Permissions (declared) ────────────────────────────────────────────────
permissions:
  - "filesystem.read"
  - "filesystem.write"
  - "network.http"
  - "network.smtp"

# ── Platforms ─────────────────────────────────────────────────────────────
platforms:
  - "windows"
  - "linux"
  - "darwin"

# ── Capabilities (declared metadata — NOT source of truth) ────────────────
capabilities:
  - id: "github.clone"
    version: 1
  - id: "github.push"
    version: 1
  - id: "github.pull"
    version: 1

# ── Optional metadata ─────────────────────────────────────────────────────
author: "JARVIS Team"
homepage: "https://github.com/jarvis-ai/jarvis-provider-github"
license: "Apache-2.0"
repository: "https://github.com/jarvis-ai/jarvis-provider-github"
tags: ["git", "github", "version-control"]
features: ["clone", "push", "pull", "pr", "issues", "releases"]

# ── Dependencies ──────────────────────────────────────────────────────────
dependencies:
  - "httpx>=0.27"
  - "pygithub>=2.0"

# ── Reserved for future use ───────────────────────────────────────────────
signature:
  algorithm: ""                 # reserved — e.g. "ed25519"
  public_key: ""                # reserved
  digest: ""                    # reserved
sandbox: {}                     # reserved
priority: 100                   # optional — load order hint
conflicts: []                   # reserved — provider ID conflicts
configuration: {}               # reserved — provider-specific settings
```

### 2.2 Required fields

| Field     | Type   | Validation                              |
|-----------|--------|-----------------------------------------|
| `id`      | string | lowercase, alphanumeric + hyphens only  |
| `publisher` | string | non-empty                             |
| `version` | string | semver                                  |
| `sdk_version` | int | >= 1                                |
| `api_version` | int | >= 1                                |
| `minimum_jarvis` | string | semver                           |
| `transport` | string | one of defined transports           |
| `entrypoint` | string | non-empty file path                |
| `permissions` | string[] | non-empty                        |
| `platforms` | string[] | non-empty                       |

### 2.3 Optional fields

All other fields are optional.  Missing optional fields MUST NOT cause
rejection.

### 2.4 Backward compatibility with v1

A v1 manifest is any JSON/YAML file with `provider_id` (not `id`) and no
`sdk_version`.  The pipeline detects v1 manifests and:

1. Assigns `sdk_version: 1`
2. Maps `provider_id` → `id`
3. Assigns `publisher: "jarvis-core"`
4. Sets `api_version: 1`
5. Sets `minimum_jarvis: "1.0.0"`
6. Sets default `permissions: []` (no restriction)
7. Loads via existing adapter path resolution

v1 manifests are never mutated on disk.  Compatibility shims apply only at
load time.

---

## 3. Permission Model

### 3.1 Permission IDs

Permissions are dot-separated, hierarchical strings.

| Prefix        | Permission              | Description                        |
|---------------|-------------------------|------------------------------------|
| `filesystem`  | `filesystem.read`       | Read files on disk                 |
| `filesystem`  | `filesystem.write`      | Write files on disk                |
| `network`     | `network.http`          | HTTP/HTTPS requests                |
| `network`     | `network.smtp`          | SMTP email                         |
| `network`     | `network.websocket`     | WebSocket connections              |
| `clipboard`   | `clipboard.read`        | Read system clipboard              |
| `clipboard`   | `clipboard.write`       | Write system clipboard             |
| `desktop`     | `desktop.window.read`   | Read window titles, positions      |
| `desktop`     | `desktop.window.move`   | Move/resize windows                |
| `desktop`     | `desktop.mouse.move`    | Move mouse cursor                  |
| `desktop`     | `desktop.mouse.click`   | Click mouse buttons                |
| `desktop`     | `desktop.keyboard.type` | Simulate keyboard input            |
| `desktop`     | `desktop.screen.capture`| Take screenshots                   |
| `process`     | `process.list`          | List running processes             |
| `process`     | `process.control`       | Start/stop processes               |
| `browser`     | `browser.tabs.read`     | Read browser tab info              |
| `browser`     | `browser.tabs.control`  | Navigate, close, switch tabs       |
| `system`      | `system.environment`    | Read environment variables         |
| `system`      | `system.shell`          | Execute arbitrary shell commands   |

### 3.2 Declaration vs verification

**Declaration** (manifest-level): The provider states what permissions it needs.
Validated pre-load.  A provider missing a required permission declaration is
REJECTED.

**Verification** (runtime): The `PermissionManager` observes every
provider action and compares against the granted set.  Violations transition
the provider to QUARANTINED.  Violations are always logged to the audit trail.

### 3.3 Granularity rule

Generic wildcard permissions (`"all"`, `"*"`, `"everything"`) are not allowed.
Every permission must be explicit.

---

## 4. Capability IDs

### 4.1 Naming convention

```
<domain>.<action>
```

Rules:
- Lowercase only
- Dot-separated namespace and verb
- Hyphens allowed for compound words: `image.depth-map`
- No underscores
- No version suffix in the ID — version is in the capability object

Examples:
```
github.clone
github.push
github.pull
github.pr.create
github.pr.merge
github.issue.list
browser.navigate
browser.snapshot
workspace.window.list
workspace.clipboard.read
desktop.mouse.click
```

### 4.2 Versioned capability objects

```yaml
capabilities:
  - id: "github.push"
    version: 1
```

Provider code declares capabilities via `provider.capabilities()` which returns
`ProviderCapabilities` objects with the same `id` + `version` tuples.

### 4.3 Permanence

Once published, a capability ID must never be renamed.  Deprecate by adding
a new ID and version.  Old IDs remain valid indefinitely.

---

## 5. Provider Lifecycle

### 5.1 States

```
                    ┌──────────┐
                    │DISCOVERED│
                    └────┬─────┘
                         │
                    ┌────▼─────┐
                    │VALIDATED │
                    └────┬─────┘
                         │
              ┌──────────┼──────────┐
              ▼          ▼          ▼
         ┌────────┐┌──────────┐┌────────┐
         │ ACTIVE ││QUARANTINED││REJECTED│
         └────────┘└──────────┘└────────┘
```

- **DISCOVERED:**  Manifest file found on disk.  No validation performed.
- **VALIDATED:**  All pipeline stages passed.  Awaiting atomic registration.
- **ACTIVE:**  Fully registered.  Visible to router, planner, capability graph.
- **QUARANTINED:**  Runtime permission violation or repeated health failure.
  Preserved for diagnostics, automatic recovery, or admin override.
- **REJECTED:**  Validation failure.  Not retried automatically.

### 5.2 Transitions

| From         | Trigger              | To           | Side effects                     |
|--------------|----------------------|--------------|----------------------------------|
| DISCOVERED   | Stage failure        | REJECTED     | Diagnostics persisted            |
| DISCOVERED   | All stages pass      | VALIDATED    | Descriptor built                 |
| VALIDATED    | Atomic commit        | ACTIVE       | Registered in ProviderRegistry   |
| ACTIVE       | Permission violation | QUARANTINED  | Audit logged, removed from registry |
| ACTIVE       | Health failure (3×)  | QUARANTINED  | Diagnostics persisted            |
| QUARANTINED  | Admin override       | ACTIVE       | Re-registered                    |
| QUARANTINED  | Version update       | DISCOVERED   | Re-validation                    |
| QUARANTINED  | No recovery          | REJECTED     | Permanent                        |

### 5.3 Pipeline stages (ordered)

```
1. DISCOVERY
2. MANIFEST VALIDATION
3. COMPATIBILITY
4. PERMISSION DECLARATION
5. PROVIDER LOAD
6. SELF VERIFICATION
7. CAPABILITY DISCOVERY
8. RUNTIME PERMISSION REGISTRATION
9. ATOMIC REGISTRATION
```

Each stage receives a `ProviderDescriptor` and returns a `StageResult`.
Stages never mutate the descriptor — they return a new descriptor or a failure.

### 5.4 StageResult contract

```python
@dataclass
class StageResult:
    success: bool
    next_state: str          # "VALIDATED" | "REJECTED"
    diagnostics: list[str]   # human-readable audit trail
    metadata: dict           # stage-specific data (e.g. loaded instance)
```

---

## 6. ProviderDescriptor

### 6.1 Definition

The canonical immutable object passed through all pipeline stages after
manifest parsing.

```python
@dataclass(frozen=True)
class ProviderDescriptor:
    id: str
    publisher: str
    version: str
    sdk_version: int
    api_version: int
    transport: str
    entrypoint: str
    permissions: frozenset[str]
    declared_capabilities: tuple[dict, ...]
    platforms: tuple[str, ...]
    fingerprint: str
    manifest_path: str
    metadata: dict            # all other manifest fields
    instance: object | None   # populated after PROVIDER_LOAD stage
```

### 6.2 Immutability

Descriptors are frozen after creation.  Stages produce new descriptors via
`dataclasses.replace()`.  No in-place mutation is permitted.

### 6.3 Fingerprint computation

```
fingerprint = SHA256(
    manifest_raw_bytes   +
    adapter_file_bytes   +
    str(sdk_version)     +
    str(pipeline_version)
)
```

### 6.4 Temporary vs permanent registry

During boot, providers accumulate in a `TemporaryRegistry` (not externally
visible).  After all providers pass validation, `atomic_commit()` transfers
ACTIVE providers to the `ProviderRegistry` in a single operation.

---

## 7. Quarantine Diagnostics

When a provider transitions to QUARANTINED, the following must be persisted:

```
- provider id
- publisher
- version
- fingerprint (last known healthy)
- failing stage
- exception type and message
- traceback (if available)
- timestamp
- retry count
- pipeline version
- manifest version
```

A provider in QUARANTINED may self-recover if its version or fingerprint
changes (indicating an update).  Administrative override is always available.

---

## 8. Rejection Reports

Every rejected provider generates a structured report:

```json
{
    "provider": "github",
    "publisher": "jarvis-ai",
    "version": "1.2.0",
    "stage": "PermissionValidationStage",
    "reason": "Missing required permission 'filesystem.read' for declared capability 'github.clone'",
    "fingerprint": "a1b2c3d4...",
    "timestamp": "2026-06-29T10:00:00Z",
    "pipeline_version": 1,
    "manifest_version": 2,
    "diagnostics": [
        "Manifest parsed (v2)",
        "Compatibility check passed",
        "Permission declaration: REJECTED — filesystem.read not declared"
    ]
}
```

Rejection reports are persisted and available for diagnostic export.

---

## 9. Deterministic Registration Guarantees

Given:
- The same set of manifest files
- In the same directory
- With the same adapter files
- Under the same SDK and pipeline versions

Repeated startup MUST produce:
- Identical ACTIVE provider set (same IDs, versions, fingerprints)
- Identical capability graph
- Identical fingerprints
- Deterministic ordering (sorted by publisher + id + version)

This guarantee enables reproducible debugging and benchmarking.

---

## 10. Architectural Invariants (Merge Gates)

Before any Manifest v2 code is merged, these nine invariants must be
verified by dedicated tests:

1. **Backward compatibility:** All existing v1 manifests load unchanged.
2. **Schema validation:** v2 fields validate correctly; malformed v2 rejected.
3. **Atomic registration:** Failure at any stage leaves no partial state.
4. **Boot resilience:** A malformed provider cannot prevent JARVIS from booting.
5. **Duplicate ID rejection:** Duplicate provider IDs are detected and rejected.
6. **Duplicate capability handling:** Duplicate capability IDs detected.
7. **Runtime quarantine:** Permission violations quarantine + audit.
8. **No behavioral regression:** All existing provider tests pass unchanged.
9. **Deterministic registration:** Identical inputs → identical outputs every run.

---

## 11. Pipeline Version History

| Version | Date       | Changes |
|---------|------------|---------|
| 1       | 2026-06-29 | Initial pipeline — 9 stages, 5-state lifecycle |
