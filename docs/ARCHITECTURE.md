# JARVIS Architecture

## Core Flow

```
Goal
  │
  ▼
Planner
  │  — classifies intent, selects template, decomposes into sub-goals
  ▼
Capability Graph
  │  — maps sub-goals to required capabilities
  ▼
Permission Manager
  │  — checks user/agent has rights for each capability
  ▼
Negotiation
  │  — scores candidate providers for each capability
  ▼
Provider Router
  │  — selects best provider per capability (health, confidence, cost)
  ▼
Provider
  │  — executes via adapter (python, http, mcp, grpc, cli)
  ▼
Artifacts
  │  — persists outputs (files, logs, screenshots, emails)
  ▼
Learning
     — extracts patterns, updates knowledge, calibrates confidence
```

Every pull request should preserve this flow.

---

## Architecture Freeze (v3.x)

The following contracts are stable and must not change until v4:

1. **Goal → Planner → Capability → Permission → Negotiation → Provider → Learning** — the execution pipeline
2. **Provider SDK manifest v2** — `provider.yaml` schema, adapter interface, capability registration
3. **Capability IDs and negotiation model** — how capabilities are requested, scored, and assigned
4. **Permission model and policy engine** — 24 permission types, user/agent ACLs, runtime enforcement
5. **Desktop SafetyManager contract** — 3-layer safety (risk classifier, sandbox, snapshot/rollback)
6. **Public APIs and provider interfaces** — REST endpoints, WebSocket channels, tool schemas

New features must build ON these contracts, not replace them.

---

## Key Design Decisions

- **Planner authority > model size** — deterministic enforcement outperforms LLM-only sequencing
- **Capability, never provider** — the user requests "publish my website", not "use GitHubProvider"
- **Providers are replaceable** — every provider can be swapped without changing capability code
- **Offline is always possible** — core flow works with Ollama and local providers only
- **Evidence over opinions** — routing decisions come from measurable calibration data
- **Learn from everything** — every execution updates at least one learning subsystem

## Implementation Map

| Component | Location | Purpose |
|-----------|----------|---------|
| Planner | `core/planner/` | Intent classification, template matching, decomposition |
| Capability Graph | `core/capabilities/` | Capability registry and resolution |
| Permission Manager | `core/permissions/` | ACLs, policy engine, runtime checks |
| Negotiation | `core/negotiation/` | Provider scoring and selection |
| Provider Router | `core/providers/` | Health-aware capability routing |
| Provider SDK | `provider_sdk/` | Third-party provider development kit |
| Artifacts | `core/workflow/artifact_store.py` | Output persistence, checksumming |
| Learning | `core/improvement/`, `core/generalization/` | Pattern extraction, confidence calibration |
| Activity Graph | `core/activity/` | Execution DAG, audit trail, resume |
| Workflow Engine | `core/workflow/` | Durable multi-step execution, recovery |
