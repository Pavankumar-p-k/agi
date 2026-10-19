# MJ Core

A headless, software-only assistant kernel. No UI: you talk to it through the
`mj` CLI and the plan/execute/verify loop. Built to the technical plan in
`docs/` (one update page per build phase).

**Build rules for this repo (unchanged from the fresh start):** every module is
real, working code; every claim of "working" is demonstrated by a test or a
live command run; tests never assert less to pass.

## Status (see docs/ for the update log)

- **Update 1 — Kernel:** SQLite state store (WAL), append-only event log and
  task state machine, hash-chained audit log, capability registry with
  manifest validation, policy gate (allow/ask/deny outside the model).
  15 unit tests. Capability awareness (probes, facts, TTL labels) and the
  executor slice are next.

Nothing beyond what is listed is claimed. No daemon, gateway, reasoner or
expansion engine exists yet.

## Usage

```bash
pip install -r requirements.txt   # pytest + pinned runtime deps
python -m pytest tests/           # full test suite
```

## Structure

```
src/mj/core/       kernel: store, events, audit, registry, policy, tasks (no LLM calls)
src/mj/policies/   policy rules — read-only to the agent; changed only by human review
tests/unit/        one test file per layer
docs/              one page per build update
```

The dependency arrow points one way: later packages (brain, executor, gateway)
may import `mj.core`; `core` never imports from them.

Previous skeleton (`src/app`) was replaced by this package on 2026-10-19.
History is preserved in git (`snapshot/pre-rebuild-2026-10-16` and earlier).
