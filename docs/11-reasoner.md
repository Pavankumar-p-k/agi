# Update 11 — the reasoner: a model that may propose, never decide

Date: 2026-10-26 · Implements the item docs/10 §5 left open once the two
decisions of 2026-10-22 were recorded (docs/09 §5): **model provider —
local-first, behind an OpenAI-compatible adapter**; **risk stance — held**
(no L1, no standing grants). Nothing in this update changes the risk stance.

## 1. What was built

Three pieces, no new dependencies: the adapter speaks HTTP with `urllib`, so
the hash-locked dependency set is untouched.

**`src/mj/brain/model.py`** — the adapter. Four environment variables, read
here and nowhere else:

| Variable | Meaning |
|---|---|
| `MJ_MODEL_PROVIDER` | provider label; its *presence* is the enable switch |
| `MJ_MODEL_BASE_URL` | OpenAI-compatible base (`http://127.0.0.1:11434/v1`) |
| `MJ_MODEL_NAME` | model name |
| `MJ_MODEL_API_KEY` | optional bearer token; local servers ignore it |
| `MJ_MODEL_TIMEOUT_S` | request deadline, default 30 s |
| `MJ_MODEL_RESPONSE_FORMAT` | `json_schema` (default) · `json_object` · `off` |

It sends exactly one chat completion with a strict JSON schema attached, and
returns the parsed content. There is no retry loop: a model failure falls back
to the deterministic planner or to one question, which is cheaper and more
honest than retrying a flaky endpoint inside planning. A partial configuration
(provider set, URL or name empty) raises instead of silently pretending no
model exists — a half-typed env contract is a mistake the operator should see.

**`src/mj/brain/reasoner.py`** — the boundary. It builds a catalogue from the
registry (healthy capabilities only, each with a declared input contract),
prompts the model, then validates everything:

- the plan object must have exactly one key, `steps`;
- each step may use only `step_id`, `name`, `capability_id`, `inputs`,
  `depends_on` — no extra keys, no policy, no capabilities;
- `capability_id` must be in the catalogue *and* re-read from the registry as
  healthy at validation time (not just when the catalogue was built);
- inputs must match the capability's contract exactly: known keys only,
  required keys present, `path` a plain string, probe names from the real probe
  set, credential **names** only and only within the capability's
  `requires_scopes`;
- `depends_on` may only name earlier steps (forward references and cycles are
  refused before topo-sort);
- the operator's `--dir` cannot be replaced by a different path;
- then the ordinary `validate_plan` runs: registered, healthy, DAG, step cap.

**`src/mj/brain/planner.py`** — one wiring decision: **deterministic first**.
A known goal never depends on a model being up, and its plan id stays stable.
Only a goal the intent table does not match may reach the reasoner, and only
when a model is configured. Plans now carry `source`
(`deterministic` / `reasoner:<provider>:<model>`) — deliberately *outside*
`plan_id`, so the same goal and steps stay idempotent whichever planner
produced them.

## 2. What the model cannot do

Every line is enforced by code and by a test in `tests/unit/test_reasoner.py`:

| Claim | How |
|---|---|
| Cannot execute anything | nothing in `model.py`/`reasoner.py` calls a capability; execution stays in `executor/runner.py`'s subprocess workers |
| Cannot invent a capability | catalogue + per-step registry re-read + `validate_plan` |
| Cannot add inputs | per-capability contracts; unknown keys are a rejection |
| Cannot exfiltrate a credential | `secrets` accepts stored *names* only, validated against `requires_scopes`; the broker resolves values at execution time |
| Cannot replace the operator's directory | a `path` input differing from `--dir` is rejected |
| Cannot bypass policy or approvals | a reasoned plan goes through `run_plan` unchanged; a deny-everything policy blocks it (test) |
| Cannot read or write the store, audit log or policy file | it receives the `Store` only to read the registry and validate a plan |
| Cannot see the key beyond the bearer header | the key is never in a plan, report, audit payload or `mj status` (test); and workers no longer inherit `MJ_MODEL_API_KEY` either (runner strips it like `MJ_BROKER_KEY`) |
| Cannot make a rejection silent | `plan.reasoner.declined` is appended to the hash-chained audit log with the reason; the CLI also prints it next to the question |

## 3. A refusal looks the same as before, and says why

`mj plan` / `mj run` still exit `3` for an unknown goal and still print one
targeted question. When a model was asked and declined, the same output gains a
`reasoner` field, e.g.:

```json
{
  "error": "unknown goal",
  "goal": "file my taxes",
  "question": "I can answer questions about disk space, ... What exactly do you want?",
  "reasoner": "ReasonerUnavailable: MJ_MODEL_PROVIDER='ollama' is set but MJ_MODEL_BASE_URL is empty; ..."
}
```

and `mj audit --entries 10` shows the same reason from the audit chain, so
"unknown goal" is never printed for a goal a model merely failed on. A model
being down can never look like an unsupported request.

## 4. Verification record (this update)

| Check | Result |
|---|---|
| Host suite, all tests | **147 passed, exit 0** (`PYTHONPATH=src python -m pytest tests/ -q`) |
| New reasoner tests | 23; 16 of them drive a real local fake OpenAI-compatible server (not a mocked `urlopen`) |
| Mutation harness | **8/8 defenses killed, exit 0** (run on a frozen tree, §6) |
| Live CLI against a fake local endpoint | `mj status` → `model.configured: true`; `mj plan` → `source: reasoner:ollama:llama3.1:8b`; `mj run --yes` → `done`, 2/2 steps verified, dry run moved nothing |
| No-model path | no HTTP request is attempted (test asserts the client is never called) |
| Wire contract | one `POST /v1/chat/completions`, bearer header when a key is set, `response_format.json_schema.name == "mj_plan"`, `strict: true` |

The fake server returns what a model returns — untrusted JSON — so these tests
prove the *boundary*, not model quality.

## 5. What is deliberately not claimed

- **No live model was used.** Every test and the CLI demo point at a local fake
  server. Ollama and LM Studio are named as the intended local-first targets;
  neither was installed or measured here, and plan quality of any model is
  unproven.
- **No hosted provider was tested.** The adapter is OpenAI-compatible by
  shape, not certified against any vendor's structured-output quirks; that is
  why `MJ_MODEL_RESPONSE_FORMAT` exists.
- **Schema enforcement is ours.** Provider-side strict mode is requested but
  never trusted: the plan is re-validated locally.
- **One shot, no repair loop.** A rejected plan is not re-prompted with the
  error; the user gets the question instead.
- **Intent miss only.** The reasoner cannot override or re-plan a goal the
  intent table already matches, and it has no tool discovery or multi-turn
  memory.
- **Hand-written input contracts.** A capability without one in
  `reasoner.INPUT_SCHEMAS` is invisible to the model; a test fails if a builtin
  lacks a contract, so this cannot rot silently.

## 6. Mutation harness

Run after all source edits were frozen, because the harness mutates files in
place: `PYTHONPATH=src python tools/mutation_check.py`.

Result on this update's tree: **all 8 defenses are load-bearing; every mutation
was killed; exit 0** (approval-payload binding, verifier independence, secret
redaction, credential scope, step-result write-once, path-traversal escape,
power → effect cross-check, registry sensitive-power rule).

A caution learned here: the harness restores each file from a byte-exact backup,
so **never edit source while it runs**. An earlier run overlapped with an edit
to `runner.py`, the harness restored the pre-edit copy, and both results became
meaningless (it reported a false "restore integrity" error). The numbers above
come from a run with no concurrent edits, and the tree was checked for leftover
`MUTATION-CHECK-DISABLED` markers afterwards (none).
