# Update 1 — Kernel (store, events, audit, registry, policy, tasks)

Date: 2026-10-19 · Scope: kernel only, per plan rule "do not create the whole folder tree up front".

## What exists (all real, all tested)

| Component | Module | Notes |
|---|---|---|
| State store of record | `mj/core/store.py` | One SQLite file (WAL). MJ_HOME env or `~/.mj`. No second store; wrapped components will read through adapters. |
| Event log + task state machine | `mj/core/events.py` | Append-only. Legal transitions enforced row-by-row; a mistimed/concurrent transition is refused, not double-applied. |
| Hash-chained audit log | `mj/core/audit.py` | Genesis 64 zeros; each entry hashes the previous. Tampering with one payload breaks chain verification. |
| Capability registry | `mj/core/registry.py` | Validated manifests (risk classes R0–R4, sealed status graph: candidate→testing→healthy→degraded→retired). |
| Policy gate | `mj/core/policy.py` | allow/ask/deny decided by rules outside the model (`mj/policies/policy.json`, read-only to the agent). R3/R4 escalate allow→ask. Unknown trust levels deny by default. |
| Tasks | `mj/core/tasks.py` | `received → planned → policy_checked → [awaiting_approval →] executing → verifying → done/failed/blocked`; every transition is an event. |

## Invariants honored so far

- One brain, one source of truth (invariant 9): single registry, single store, single event log.
- Policy outside the model (invariant 2): rules are a data file; decisions are audited.
- Awareness before autonomy (invariant 10): autonomy level fixed at L0, recorded in `mj/__init__.py`.

## Not claimed yet

No daemon, no `mjd`, no gRPC gateway, no reasoner, no expansion engine, no sandbox, no workers. Those come later phases; nothing here pretends otherwise.

## Proven by tests

`tests/unit/test_kernel.py` — 15 tests: reopen-persistence, WAL mode, transition legality, concurrent-transition rejection, audit tamper detection, manifest validation, status graph, policy decision table, R3/R4 escalation, unknown-trust denial, decision auditing.
