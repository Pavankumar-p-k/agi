# Update 9 — CI on machines we don't control, killable workers, declared effects

Date: 2026-10-20 · Implements the second review's four items: CI + hashed
lockfile, the zombie-worker isolation fix, effect declarations with runtime
enforcement and an import lint — plus refined draft answers to the two
decisions still blocking the reasoner.

## 0. Why this update exists

Update 8's results were *reported*: the same agent wrote the code, ran the
checks and described them. The reviewer's point stands — the independent
check is a clean run on a machine the agent does not control. Three more
findings were structural, not cosmetic:

1. A timed-out worker was "abandoned". Python threads cannot be killed, so
   an abandoned worker keeps running and can cause side effects after MJ has
   marked the step failed.
2. The registration rule matched *words* ("web", "browser", "shell"). A
   capability named `helper` that shells out passes any name check.
3. Tests had passed on ambient packages — the missing `psutil` proved it.
   Dependencies needed pinning before the broker and sandbox add more.

Order (unchanged): CI → zombie fix → credential broker → the reasoner.

## 1. CI + hashed lockfile

**`.github/workflows/ci.yml`** — on push to main and on every PR, for
**windows-latest and linux-latest** (path, process and shell behavior differ
enough between them to hide bugs; the harness itself hit a Windows file-lock
bug in Update 8):

1. fresh venv (never the runner's ambient site-packages),
2. `pip install --require-hashes -r requirements.lock`,
3. `pip install --no-deps .` + `mj status` smoke — the *installed* package,
   where packaging bugs surface (this is what caught the missing dependency),
4. full suite,
5. `tools/mutation_check.py` — every defense must kill its mutation.

`requirements.in` holds the two direct dependencies (psutil, pytest) with
refresh instructions; `requirements.lock` is `pip-compile --generate-hashes`
output (all hashes, all transitive deps). The workflow YAML parses under
`yaml.safe_load` with structure assertions (validated, not eyeballed).

**To make CI actually block merges**, one action only you can take: on GitHub
enable branch protection for `main` → "Require status checks to pass" →
select both jobs. The agent cannot set repo settings; without this the runs
are advisory.

Two design notes:

- `pyproject.toml` gives pytest `pythonpath = ["src"]`, so the suite and the
  mutation harness always test the checked-out source (mutations are
  visible to the tests). The packaging smoke tests the *installed* copy —
  each step validates what it claims to.
- CI still runs only when pushed; it does not exist in this repo's history
  until this update lands.

## 2. Zombie workers → processes MJ can kill

Each step now runs in its own **subprocess** (`mj.executor.worker`), not a
thread (`runner._run_step`):

- **The deadline is enforced by process death.** `subprocess.run` terminates
  the worker on timeout before the runner ever raises — an unkillable thread
  is no longer in the picture. Test: the injected worker records its own pid,
  sleeps past the deadline, and the test asserts that exact process is dead
  (psutil, Windows and Linux).
- **A late result is discarded.** The worker writes its result to a file the
  parent reads *only* if the process exited cleanly, in time. On expiry the
  file is removed unread.
- **The final state is final.** `step_results` is write-once
  (`ON CONFLICT(idempotency_key) DO NOTHING`): a late or duplicate write
  loses against the recorded truth and the discard is audited as
  `step.result.discarded`. Previously the inserts were `OR REPLACE` — a
  racing write could silently overwrite the record.
- **Tests inject through the real path.** All ten worker-behavior injections
  now use `MJ_WORKER_OVERRIDE_DEV` (a JSON file naming capability + code);
  the override executes *inside the worker subprocess*, exactly where a real
  capability would run, so the tests exercise the shipping execution path
  including its death by timeout. Verifiers were always parent-side and
  remain so.
- The worker opens its own store connection (WAL), so it can never race the
  kernel's connection.

**Known limitations (stated, not hidden):**

- *Pre-expiry side effects* a killed worker already performed are still
  unrecorded by design — a timeout is an unknown outcome, never a success;
  undo covers recorded moves only. No automatic rollback exists yet.
- *Grandchildren*: killing the worker does not kill processes the worker
  itself spawned (a future shell capability would need process-group kill or
  the sandbox step). Today's builtins spawn only short-lived read-only
  probes, so the exposure is theoretical — for now.

## 3. Declared effects: declaration, runtime floor, import lint

Manifests gain `effects` — `filesystem.read | filesystem.write | network |
process | secrets` — enforced at three independent points
(`mj.core.effects`, `mj.core.registry`, `runner`):

1. **Registration**: closed vocabulary; a sensitive power (web/browser/shell)
   without its required effect (`network`/`process`) is rejected — powers and
   effects must agree; sensitive effects carry a risk floor
   (`network`/`process` ≥ R1, `secrets` ≥ R3), so a capability named
   `helper` cannot register a shell-out as a silent R0.
2. **Runtime**: the runner denies `network`/`process`/`secrets` steps from
   every trust level but `local-terminal` — even for a legacy or compromised
   DB row that skipped validation entirely (defense in depth; tested by
   inserting such a row directly, where policy alone would *allow* it).
3. **Lint**: AST scan of each builtin's provenance modules against the
   declared effects, as a test. `mj.world.probes` imports `subprocess`, so
   `os.facts` now honestly declares `process` — and its risk class moved
   **R0 → R1** (the floor). Local UX is unchanged (R1 allows from the
   terminal); facts from non-local channels are now denied, matching the
   documented R1 rule rather than the old R0-from-anywhere one.

Declared-but-unused effects are fine (conservative declarations cost
nothing); used-but-undeclared is the violation the lint fails on.

## 4. The harness caught its own gap

The new power→effect mutation first *survived*: the disabling condition was
`if "MUTATION-CHECK-DISABLED" else None` — a non-empty string is truthy, so
the mutation was a no-op and the defense never actually switched off. The
harness reported `SURVIVED` (correctly), the condition was inverted to
`if not ...`, and the mutation was then killed. The checker is itself
checked: a defense whose kill-test cannot fail is exactly what it exists to
find — including in its own table.

## 5. Draft answers to the two open decisions (for you to edit)

> **DECIDED 2026-10-22 by the operator** (this section's two drafts are now
> accepted, with one amendment):
>
> 1. **Model provider — accepted as local-first.** Local default behind an
>    OpenAI-compatible adapter (Ollama + JSON-schema `Plan` outputs), hosted
>    providers pluggable for when plan quality demands it. Env contract as
>    drafted: `MJ_MODEL_PROVIDER`, `MJ_MODEL_BASE_URL`, `MJ_MODEL_NAME`,
>    `MJ_MODEL_API_KEY` — read by the model adapter only; the executor never
>    sees a key.
> 2. **Risk stance — HOLD, do not loosen.** The operator declined the L1
>    step. The current stance (R0 any channel, R1 local-terminal, R2 asks
>    payload-hash-bound, R3 never silent, R4 human-edited standing rule,
>    plus the effects floor from §3) stands **unchanged**. The three triggers
>    below and the proposed L1 standing grants are **withdrawn** — not
>    deferred, not conditional; revisit only by a fresh, explicit decision.
>
> Both decisions unblock the reasoner (item next after the credential broker).
The text below is retained as the historical draft that was accepted/amended.

Both are **drafts**. Nothing here is a commitment.

**Model provider — recommendation: local-first behind an
OpenAI-compatible adapter, hosted providers pluggable.**

Reasoning: MJ's design caps what a model can do — it proposes typed plans;
the gate, executor, verifiers, audit and (soon) the broker decide everything
else (invariants 1, 2, 8). So the provider choice trades *plan quality*
against *data exposure*, not against safety. Local-first (Ollama +
constrained JSON output for `Plan`) means zero prompts leave the machine
while the reasoner is new — before it has real tools to invoke and before a
hosted provider's retention policy is even in the trust path. When a hosted
model is needed for quality, require structured outputs and zero-retention /
no-training terms. Proposed env contract: `MJ_MODEL_PROVIDER`,
`MJ_MODEL_BASE_URL`, `MJ_MODEL_NAME`, `MJ_MODEL_API_KEY` (read by the model
adapter only; the executor never sees it).

*Decision needed from you:* local-first default vs hosted-first, and which
hosted provider when quality demands it.

**Risk stance — recommendation: hold the current stance; take exactly one
step (L1) after three triggers.**

The current stance (Update 5 draft #4, unchanged in practice): R0 any
channel, R1 local-terminal, R2 always asks payload-hash-bound, R3 never
silent, R4 needs a human-edited standing rule — now plus the effects floor
(§3). Triggers for loosening:

1. credential broker merged, its adversarial tests green (the first piece
   that materially raises blast radius);
2. ≥25 consecutive real tasks with zero gate overrides and zero
   steps-unverified-because-unverifiable (evidence that asking stays rare
   enough not to train override habits);
3. CI green on both OSes including the mutation harness for a week — the
   "machines we don't control" bar.

Then the one step: **L1 = standing grants for R1-only, local-terminal plans**
(still payload-hash-bound, still expiring on payload change). Nothing R2+
becomes pre-approvable without a separate later decision. Note Update 9's
os.facts R0→R1 moved a capability *toward* scrutiny because the declaration
changed — the stance should move on facts like that, not on convenience.

*Decision needed from you:* accept, edit the triggers, or pick different
ones.

## 6. Verification record (commands and exit codes, this update)

| Check | Result |
|---|---|
| Host suite | **98 passed, exit 0** |
| Fresh venv (from scratch), `pip install --require-hashes -r requirements.lock` | exit 0 |
| Fresh venv, `pip install --no-deps .` | exit 0 |
| `mj status` from outside the repo (installed package) | exit 0 |
| Fresh venv suite | **98 passed, exit 0** |
| Fresh venv `tools/mutation_check.py` | **all 6 defenses killed, exit 0** |
| `ci.yml` parse + structure assertions (`yaml.safe_load`) | exit 0 |

Test growth: 88 → 98 (+7 effects/lint/runtime-floor, +2 zombie/discard, +1
power↔effect registration).

## 7. Order and what's next

Done here: CI, lockfile, zombie fix, effects — items 1–3 of the review plus
its packaging observation. **Next: credential broker**, then the reasoner,
which starts the moment §5's two decisions are yours.

Open limitations to carry: pre-expiry side effects of a killed worker are
reported, not rolled back; grandchildren of a killed worker survive (shell
capabilities will need process-group kill or sandboxing); branch protection
needs your one-time GitHub setting before CI blocks anything; no LLM is
wired anywhere yet.
