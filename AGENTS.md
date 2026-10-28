# AGENTS.md

Rules for any agent (human-directed or model-driven) working in this
repository. MJ's plan for what an automated agent may and may not do lives
in `docs/`; this file states the rules that bind the agents *building* MJ.

## Credential files (decided 2026-10-28)

Agents working on MJ must not read credential *files* — anything outside
MJ's own secret store whose name or containing directory designates
credential material: `.env`, `id_rsa`, `credentials.json`, `.ssh`,
`.gnupg`, `.aws`, `.kube`, `.docker`, `.password-store`, secrets
directories, other tools' secret stores (for example `~/.config/opencode/`).

* Needed credentials for MJ go through MJ's own broker
  (`mj secrets set ...`), not through files copied out of other tools.
* A key that was ever in a shell environment must be treated as exposed to
  everything that ran in that shell; rotate it instead of reusing it.
* The same refusal is enforced in code at both boundaries: plan building
  (`src/mj/core/paths.py`, used by the reasoner) and step execution
  (`src/mj/executor/runner.py`, for any planner's output). A worker asking
  for such a path is refused, tested in `tests/unit/test_reasoner.py`
  (the credential-path floor section).

## Sending things to the model (decided 2026-10-28)

What leaves the machine for the model to see is an allowlist maintained in
`src/mj/brain/prompts.py`: goal text, the capability catalogue and the
operator's directory, with home/username/hostname rewritten to `<HOME>`,
`<USER>`, `<HOST>` placeholders. Never add file contents, environment
variables, secret names/values or credential paths to a prompt. The
executor re-binds the placeholders locally; the audit log stores a hash of
every prompt sent, never its text.

## Model configuration (decided 2026-10-28)

`MJ_MODEL_API_KEY`, when needed, resolves from MJ's own broker store
(`mj secrets get model_api_key`) when the environment variable is unset.
Do not export a model key into the environment to "make it work".

## seen / decided

`docs/05-progress-and-decisions.md` is the running log; `docs/06-adversarial.md`
lists the adversarial suite. CI runs the full test suite and the mutation
harness on Windows and Linux — every defense must kill its mutation.
