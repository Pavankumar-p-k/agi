# Update 3 — Brain + executor: typed plans, policy gate, idempotent execution, verification

Date: 2026-10-19 · Scope: the thin vertical slice (plan Phase 1 exit criterion), still model-free and deterministic.

## What exists (all real, all tested)

| Component | Module | Notes |
|---|---|---|
| Typed plan DAG | `mj/brain/planner.py` | Goal → fixed intents → `Plan` of `Step`s. Every step references a **registered, healthy** capability; unknown goals are refused with one targeted question (no guessing, failure 16). Hallucinated capabilities are rejected by validation (failure 4). Kahn's algorithm rejects cycles and unknown dependencies. |
| Deterministic plan ids | `mj/brain/planner.py` | Same goal + params → same plan id → same idempotency keys, so a resumed run cannot double-execute a side effect (failures 7, 18). |
| Deterministic executor | `mj/executor/runner.py` | Walks the DAG topologically. **The only module allowed to touch the world.** No LLM anywhere in the path (invariants 1, 2). |
| Policy gate in the loop | `mj/executor/runner.py` | Every step's risk class judged *before any execution*. deny → task blocked with a report; ask → `ApprovalRequired` with the exact payload shown (not a summary) and a payload hash bound to the approval (failure 25). R1 dry-run allows silently; R2 organize asks even from the local terminal. |
| Approvals + resume | `mj/executor/runner.py` | Task parked at `awaiting_approval`; `grant_pending` / `deny_pending`; resumed via `resume_task_id`. Grants bind to the payload hash. |
| Idempotency | `step_results` table | Key = hash(plan_id, step_id, inputs). A re-run finds a recorded result and **reuses** it (`step.reused` event) instead of re-triggering effects — proven by a crash-recovery test. |
| Independent verifiers | `mj/executor/capabilities.py` | Each builtin has its own verify function that re-reads the filesystem/fact store (failures 3, 30). A lying verifier test proves unverified steps are flagged and the capability is demoted to *degraded*. |
| Undo plan | `undo_organize` | Real `files.organize` records every move with source size; undo restores files **and removes created folders**, checked in tests. |
| Collision safety | `_unique_dst` | Destination conflicts become `name (2).ext`; a verified test proves a precious file is never overwritten (failure 11 in spirit). |
| Builtins registered | `ensure_registered` | `os.facts` (R0), `files.list` (R0), `files.organize.plan` (R1), `files.organize` (R2, has_undo) — all with verifiers. |

## Invariants honored

- Done means verified (invariant 8): reports separate `verified_steps` from `unverified_steps`; task completes as `done` only with evidence recorded.
- Least privilege: R2 organizes ask; unknown trust channels would deny; denied plans leave the world untouched (blocked task, evidenced in test).

## Not claimed yet

No LLM planner (deterministic intents only), no daemon, no gateway, no expansion engine, no multi-agent coordination. `mjd` and the CLI are next.

## Proven by tests

`tests/unit/test_brain_executor.py` — 19 tests. Highlights: hallucinated capability refused; unhealthy capability refused; cycle/unknown-dep detection; full facts plan verified end-to-end with audit chain intact; crash-recovery reuse with zero duplicate execution; dry-run moves nothing (verified); commit organize verified, then undone to byte-identical directory state; collision never overwrites; denied plan blocked; failed step marks task failed honestly; verified-vs-unverified separation with capability degradation when the verifier disagrees.
