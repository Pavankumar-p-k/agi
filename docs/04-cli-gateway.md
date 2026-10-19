# Update 4 — Gateway: the `mj` CLI (thin vertical slice complete)

Date: 2026-10-19 · Scope: the CLI gateway. End-to-end loop now runs on real tasks.

## Commands

```text
mj status                     version, L0 notice, registry health, audit-chain check
mj ask <question>             machine-awareness answer from labeled facts (always fresh-read)
mj plan <goal> [--dir PATH] [--commit]
                              show the typed plan; unknown goals exit 3 with one question
mj run <goal> [--dir PATH] [--commit] [--yes]
                              build → policy-gate → execute → verify → report
mj events [--task-id ID]      task/event log
mj registry [--healthy]       capability manifests with risk classes and health
mj facts [--refresh]          world-model facts with honest verified/stale labels
mj undo <task_id>             undo recorded side effects of a done task
mj audit                      verify the hash-chained audit log
```

Exit codes: `0` ok, `2` usage, `3` unknown goal (with a targeted question),
`4` approval denied, `5` run not done/blocked, `6` audit chain broken.

## Proven live (not just in unit tests)

- `mj status` — healthy registry, chain ok, `autonomy_level: L0`.
- `mj ask "how much disk space…"` — disk fact with `label: verified`, source `shutil.disk_usage`, observed-at timestamp.
- `mj run … --commit` — policy asked for R2 `files.organize` showing the **exact payload and its hash**; declined (`n` / EOF) → files untouched, task parked at awaiting_approval; `y` → executed, both steps verified (`files.list` and `files.organize`), directory organized into `documents/` and `images/`, task `done`.
- `mj undo <task_id>` — put every file back (covered by test).

## Safety notes

- The CLI implements nothing itself: all side effects flow through the same registry, policy gate, executor and verifiers.
- `--yes` auto-approves only the steps the policy marked `ask`, still recording who approved.
- A non-interactive approval prompt (EOF) is an explicit refusal, never a silent yes.

## Not claimed yet

No daemon (`mjd`), no gRPC, no chat connectoors, no LLM reasoner, no expansion engine, no multi-agent coordination. Next phases from the plan: reasoner/verifiers for richer tasks (Phase 4) and the policy/adversarial hardening suite (Phase 5).
