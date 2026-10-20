# Update 5 — Verified progress + draft answers to the five open decisions

Date: 2026-10-19 · This page separates **verified** from **reported**, per plan invariant 5.

## What is done and independently verified

Verification was performed again, from outside the agent's own report:
`python -m pytest tests` (exit 0), `git log` hash check, and `mj status` /
`mj audit` in a **fresh venv** with a non-editable install and a fresh MJ_HOME.
The venv procedure is now a permanent test: `tests/integration/test_clean_install.py`.

| Claim | Status | What confirms it |
|---|---|---|
| Kernel: WAL store, event log + task state machine, hash-chained audit, registry, policy gate | **Verified** | 15 unit tests incl. tamper-detection and concurrent-transition rejection |
| Awareness: disk / processes / apps / tools probes with provenance, TTL, labels | **Verified** | Cross-checked in tests against independent OS-level reads (`shutil.disk_usage`, pid of the test process) |
| Thin vertical slice: typed plan → policy gate → executor → verifier, idempotent + resumable | **Verified** | 19 tests incl. crash-recovery reuse, denial, undo, collision-safety, verifier-disagreement demotion |
| Approval flow shows exact payload + hash; refusal is a no-op; undo restores | **Verified live** | CLI session: `n`/EOF left the directory untouched; `y` executed with all steps verified; documented in `docs/04` |
| Clean install → `mj` works with no PYTHONPATH tricks | **Verified** (Update 5) | `tests/integration/test_clean_install.py` builds a fresh venv, installs non-editably, runs `mj status`/`mj audit` |
| Suite | **Verified** | 59 tests, exit 0 |

Still missing (priority order, matching the review): **1.** adversarial suite
(injection via tool output, fake success replies, gate-bypass attempts) — to be
done *before* any LLM joins the loop; **2.** credential broker (no raw token
ever reaches the planner); **3.** reasoner emitting typed plans only; **4.**
expansion engine; **5.** daemon/API (explicitly deferred).

## Draft recommended answers to the five open decisions

These are **drafts for you to edit** — nothing here is a commitment.
(Refined, argued answers for #3 model provider and #4 risk stance landed in
`docs/09` §5 on 2026-10-20; both remain open for your edit.)

1. **Operating system(s) first.** Windows (win32) — it is the machine we run
   on; every OS-specific probe already records its source so per-OS adapters
   stay swappable. macOS/Linux paths exist for the probes but are untested
   until a target machine exists.
2. **First three real tasks.** (a) awareness Q&A (done), (b) file organization
   with refusal/undo (done), (c) `git push` of a project branch with an
   independent verifier (remote ref lookup and hash comparison). Task (c)
   needs the credential broker, which is why it is deferred behind it.
3. **Model provider(s).** Provider-agnostic router when the reasoner phase
   starts: a strong hosted model for planning *with structured outputs*, a
   cheap/none fallback means planning degrades to "ask the user", which the
   policy gate already supports. No provider is wired today — nothing in the
   current build calls any model API.
4. **Risk stance (draft v0).** R0 allowed from any channel; R1 allowed from
   the local terminal only; R2 always asks, payload-hash-bound; R3 never
   silent (asks from local terminal or a confirmed channel); R4 denied until a
   written standing rule is added to the policy file by human edit. Standing
   approvals always bind to a payload hash and expire when the payload
   changes — this is the current actual behavior; we are not loosening it in
   the first autonomy step.
5. **Existing agents and tools to reuse.** Inventory of this machine: git CLI
   (well-proven), Python interpreter, a real browser (Playwright candidate —
   not integrated). No MCP servers or external agents are registered yet, so
   "reuse" today means: everything the registry now knows. A Phase 0
   tested-inventory record will be added when external components appear.
