# MJ Core

A headless, software-only assistant kernel. No UI: you talk to it through the
`mj` CLI and the plan → policy-gate → execute → verify loop. Built to the
technical plan in `docs/` (one update page per build phase).

**Build rules for this repo (unchanged from the fresh start):** every module is
real, working code; every claim of "working" is demonstrated by a test or a
live command run; tests never assert less to pass.

## Status (docs/ = the update log)

1. **Kernel** — SQLite state store (WAL), append-only event log + task state
   machine, hash-chained audit log, validated capability registry, allow/ask/
   deny policy gate (rules live in a read-only file, outside any model).
2. **Awareness** — real OS probes (disk, running processes, installed apps,
   tool versions) feeding a fact store with provenance, TTL and honest
   verified / reported / stale labels.
3. **Brain + executor** — typed plan DAGs bound to the registry; the
   deterministic executor is the only component that touches the world;
   payload-hash-bound approvals; idempotent, resumable runs; independent
   verifiers; a real undo for file organization.
4. **Gateway** — the `mj` CLI, proven live end to end.
5. **Hardening** (docs/06–09) — adversarial suite; sensitive-power +
   declared-effects registration rules with runtime enforcement and an import
   lint; per-step/per-task timeouts and plan caps; killable subprocess
   workers with write-once step results; hashed dependency lockfile and a
   Windows+Linux CI workflow that runs the suite and the mutation harness.

6. **Reasoner** (docs/11) — local-first, behind an OpenAI-compatible
   adapter (`MJ_MODEL_PROVIDER`, `MJ_MODEL_BASE_URL`, `MJ_MODEL_NAME`,
   optional `MJ_MODEL_API_KEY`). A model may only *propose* a plan for a goal
   the intent table does not know; the proposal passes the same registry,
   input-contract, policy-gate and verifier checks as a deterministic plan.
   Rejections are audited, and a decline ends in one question. With no model
   configured nothing is ever contacted.

Nothing beyond what is listed is claimed. No daemon, gRPC server or expansion
engine exists yet. The reasoner proposes plans and nothing else: it cannot
execute, hold a credential, read the broker or edit policy.

## Usage

```bash
pip install --require-hashes -r requirements.lock   # hashed lockfile (psutil + pytest)
python -m pytest tests/                # 147 tests

export MJ_HOME=~/.mj                   # where the one state store lives (optional)
PYTHONPATH=src python -m mj status     # also installed as `mj` console script
PYTHONPATH=src python -m mj ask "how much disk space do I have?"
PYTHONPATH=src python -m mj run "organize files" --dir C:\path\to\messy          # dry run (R1)
PYTHONPATH=src python -m mj run "organize files" --dir C:\path\to\messy --commit  # real move (R2 → asks)
mj audit                               # verify the hash chain

# Optional: reasoned planning for goals the intents do not cover (docs/11).
# Local-first; unset these and no model is ever contacted.
export MJ_MODEL_PROVIDER=ollama
export MJ_MODEL_BASE_URL=http://127.0.0.1:11434/v1
export MJ_MODEL_NAME=llama3.1:8b
PYTHONPATH=src python -m mj plan "sort out the download folder" --dir C:\path\to\messy
```

Exit codes: 0 ok · 2 usage · 3 unknown goal (prints one targeted question) ·
4 approval denied · 5 run blocked/failed · 6 audit chain broken.

## Structure

```
src/mj/core/       kernel: store, events, audit, registry, policy, tasks, effects (no LLM, ever)
src/mj/policies/   the rules file — read-only to the agent; changed only by human review
src/mj/world/      probes + fact store (provenance, TTL, labels)
src/mj/brain/      typed planner (deterministic intents + strictly validated reasoner;
                   registry-bound; refuses to guess) and the local-first model adapter
src/mj/executor/   the runner: policy gate, approvals, idempotency, verifiers, undo, killable
                   subprocess workers — killed with their whole process tree (killtree.py)
src/mj/gateway/    the mj CLI (all side effects flow through the executor)
tests/             147 tests: unit + adversarial + integration + lint (mutation harness: tools/mutation_check.py)
.github/workflows/ CI: fresh venv, hash-locked install, full suite, mutation harness (Windows + Linux)
docs/              one page per build update
```

The dependency arrow points one way: world, brain, executor and gateway may
import `mj.core`; `core` never imports from them.

Previous skeleton (`src/app`) was replaced by this package on 2026-10-19.
History is preserved in git (`snapshot/pre-rebuild-2026-10-16` and earlier).
