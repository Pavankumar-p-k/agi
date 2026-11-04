"""Reasoner: plans for goals the intent table does not know, proposed by a model.

Invariants this file exists to protect:

  * the model proposes, the deterministic executor disposes — nothing here
    executes, and nothing here can edit policy, the registry or the audit log;
  * a step may only reference a capability that is registered *and* healthy, so
    a hallucinated capability is a rejected plan, never a swallowed error
    (plan failure modes 4 and 16);
  * every step input is validated against a declared contract, so the model
    cannot smuggle extra keys (a secret, a second path, a shell command) into a
    payload the user is asked to approve;
  * a rejection is never silent: the planner audits the reason, and the user
    gets the same one targeted question the deterministic planner gives.

The reasoner is only reached for goals the intent table does not match, and
only when MJ_MODEL_PROVIDER is set (see `mj.brain.model`). With no model
configured this module is never called and nothing is contacted.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import socket
from dataclasses import dataclass
from typing import Any

from mj.brain import model, planner, prompts
from mj.brain.prompts import (
    HOST_PLACEHOLDER,
    HOME_PLACEHOLDER,
    USER_PLACEHOLDER,
)
from mj.core import audit, registry, settings
from mj.core.paths import credential_path_violations
from mj.core.registry import Manifest
from mj.core.store import Store, canonical_json
from mj.executor import broker

#: Stored-credential name holding the model's API key. Set it with
#: ``mj secrets set model_api_key`` through the local terminal; the adapter
#: sends it as a bearer token and nothing ever prints it back.
MODEL_KEY_SECRET_NAME = "model_api_key"


def resolve_api_key(store: Store) -> tuple[str | None, str]:
    """Where the model's bearer token comes from; ``(token, origin)``.

    Order: the explicit environment variable wins (operators may still run
    the key purely in-process), otherwise the encrypted broker is opened for
    the ``model_api_key`` stored credential — the credential path an operator
    fund chose over pasting keys into shell export lines. The token value is
    for the bearer header only; callers must not record it.
    """
    token = (os.environ.get("MJ_MODEL_API_KEY") or "").strip()
    if token:
        return token, "environment"
    try:
        secret = broker.get_secret(store, MODEL_KEY_SECRET_NAME)
    except broker.BrokerError:
        return None, ""
    return (secret, "broker") if secret else (None, "")


#: Probe scope names, mirrored from mj.world.probes.PROBES; a test asserts they
#: stay in step so the catalogue can never offer a scope the probes reject.
PROBE_CHOICES: tuple[str, ...] = ("apps", "disk", "processes", "tools")

#: Hard upper bound for the JSON schema handed to the model. The operator cap
#: (MJ_MAX_STEPS) still applies on top; this only keeps a runaway generation
#: cheap to reject.
SCHEMA_MAX_STEPS = 25

STEP_ID_PATTERN = r"^[a-z0-9][a-z0-9_-]{0,15}$"
_ALLOWED_STEP_KEYS = frozenset({"step_id", "name", "capability_id", "inputs", "depends_on"})
_MAX_PATH_LEN = 4096


class ReasonerError(Exception):
    """Base class: the reasoner declined, or could not be used at all."""


class ReasonerUnavailable(ReasonerError):
    """No model configured, transport failure, or an unusable configuration."""


class PlanRejected(ReasonerError):
    """The model answered, but the answer is not an executable plan."""


@dataclass(frozen=True)
class InputSpec:
    """One input a capability accepts, as the model is allowed to fill it."""

    kind: str  # "path" | "probe-names" | "secret-names"
    required: bool = True
    choices: tuple[str, ...] = ()
    description: str = ""

    def for_prompt(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "type": self.kind,
            "required": self.required,
            "description": self.description,
        }
        if self.choices:
            out["allowed"] = list(self.choices)
        return out


#: The input contract per capability. This is a *planner* concern (what a model
#: may propose), not a manifest concern, so it lives in the brain. A test
#: asserts every builtin has an entry: a new capability without one is simply
#: not offered to the model rather than being filled with unchecked inputs.
INPUT_SCHEMAS: dict[str, dict[str, InputSpec]] = {
    "os.facts": {
        "probes": InputSpec(
            "probe-names",
            required=False,
            choices=PROBE_CHOICES,
            description="which machine facts to refresh; omit for all of them",
        )
    },
    "files.list": {
        "path": InputSpec("path", description="directory to list (read-only)")
    },
    "files.organize.plan": {
        "path": InputSpec("path", description="directory whose contents to list as a dry-run proposal")
    },
    "files.organize": {
        "path": InputSpec("path", description="directory whose files are moved into category subfolders (undo recorded)")
    },
    "data.spreadsheet.summary": {
        "path": InputSpec("path", description="CSV file to summarize"),
        "secrets": InputSpec(
            "secret-names",
            required=True,
            description="names of stored credentials to resolve at execution time; never values",
        ),
    },
}


def plan_schema(max_steps: int) -> dict[str, Any]:
    """JSON schema for the plan object handed to the model (and its validator)."""
    limit = max(1, min(int(max_steps), SCHEMA_MAX_STEPS))
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "MJPlan",
        "type": "object",
        "additionalProperties": False,
        "required": ["steps"],
        "properties": {
            "steps": {
                "type": "array",
                "minItems": 0,
                "maxItems": limit,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["step_id", "capability_id"],
                    "properties": {
                        "step_id": {"type": "string", "pattern": STEP_ID_PATTERN},
                        "name": {"type": "string", "maxLength": 120},
                        "capability_id": {"type": "string"},
                        "inputs": {"type": "object"},
                        "depends_on": {
                            "type": "array",
                            "items": {"type": "string", "pattern": STEP_ID_PATTERN},
                        },
                    },
                },
            }
        },
    }


def is_configured() -> bool:
    """True when the model contract is complete enough to attempt a call."""
    try:
        return model.config_from_env() is not None
    except model.ModelError:
        # A half-typed configuration is still "configured" for the caller's
        # purposes: propose_plan will surface the error instead of hiding it.
        return True


def catalogue(store: Store) -> list[dict[str, Any]]:
    """The capabilities the model may use: healthy, with a known input contract."""
    offered: list[dict[str, Any]] = []
    for row in registry.list_all(store, healthy_only=True):
        capability_id = row["id"]
        contract = INPUT_SCHEMAS.get(capability_id)
        if contract is None:
            continue
        got = registry.get(store, capability_id)
        if got is None:  # status changed between the two reads
            continue
        manifest, status = got
        if status != "healthy":
            continue
        entry: dict[str, Any] = {
            "capability_id": manifest.id,
            "description": manifest.description,
            "risk_class": manifest.risk_class,
            "inputs": {name: spec.for_prompt() for name, spec in sorted(contract.items())},
        }
        if manifest.requires_scopes:
            entry["store_credential_names"] = list(manifest.requires_scopes)
        offered.append(entry)
    return offered


def _system_prompt(offered: list[dict[str, Any]], max_steps: int) -> str:
    return (
        "You plan steps for a local automation agent. You do not run anything: a\n"
        "deterministic executor policy-gates, executes and verifies whatever you\n"
        "propose, and the user approves anything risky.\n"
        "Output ONLY one JSON object, no prose and no markdown fences:\n"
        '{"steps":[{"step_id":"s1","name":"short label","capability_id":"...",'
        '"inputs":{...},"depends_on":[]}]}\n'
        "Rules:\n"
        "- capability_id MUST be one of the catalogue below; never invent one.\n"
        "- inputs MUST use exactly the keys in that capability's input schema.\n"
        f"- use at most {max_steps} step(s); prefer the fewest steps that work.\n"
        "- depends_on may only name step_ids that appear earlier in the list.\n"
        "- never write a credential value anywhere; only stored credential *names*\n"
        "  are allowed, and only where the schema says so.\n"
        f"- the prompt may contain the placeholders {HOME_PLACEHOLDER}, "
        f"{USER_PLACEHOLDER}, {HOST_PLACEHOLDER} standing for paths and identity "
        "that must not leave this machine; when a path input must use them, echo "
        "that exact placeholder spelling back — the executor re-binds it locally.\n"
        "- never guess, reconstruct or output a real home directory, username or "
        "hostname; never name credential files (.env, .ssh, secrets directories).\n"
        '- if the catalogue cannot achieve the goal, output {"steps":[]}.\n'
        "Catalogue (JSON):\n"
        + json.dumps(offered, indent=1, sort_keys=True)
    )


def _user_prompt(goal: str, params: dict[str, Any]) -> str:
    lines = [f"Goal: {prompts.redact(goal)}"]
    if params.get("dir"):
        lines.append(
            "Operator-supplied directory (a path input must use it, or one of the "
            f"placeholders with it spliced on): {prompts.redact(str(params['dir']))}"
        )
    if params.get("commit"):
        lines.append("The operator asked for real changes (not a dry run) where the goal needs them.")
    return "\n".join(lines)


def _reject(message: str) -> PlanRejected:
    return PlanRejected(message)


def _check_path(capability_id: str, name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _reject(f"{capability_id}: input {name!r} must be a non-empty string path")
    if len(value) > _MAX_PATH_LEN:
        raise _reject(f"{capability_id}: input {name!r} is longer than {_MAX_PATH_LEN} characters")
    if "\x00" in value or "\n" in value or "\r" in value:
        raise _reject(f"{capability_id}: input {name!r} contains control characters")
    return value.strip()


def _check_string_list(capability_id: str, name: str, value: Any, allowed: tuple[str, ...]) -> list[str]:
    if not isinstance(value, list) or not value:
        raise _reject(f"{capability_id}: input {name!r} must be a non-empty list of names")
    out: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise _reject(f"{capability_id}: input {name!r} must contain only strings")
        if item not in allowed:
            raise _reject(
                f"{capability_id}: {name!r} value {item!r} is not one of {sorted(allowed)}"
            )
        out.append(item)
    return out


def validate_inputs(
    capability_id: str,
    inputs: Any,
    manifest: Manifest,
) -> dict[str, Any]:
    """Validate one step's inputs against its declared contract; normalise them."""
    contract = INPUT_SCHEMAS.get(capability_id)
    if contract is None:
        raise _reject(f"capability {capability_id!r} has no declared input contract")
    if not isinstance(inputs, dict):
        raise _reject(f"{capability_id}: inputs must be a JSON object")

    unknown = sorted(set(inputs) - set(contract))
    if unknown:
        raise _reject(
            f"{capability_id}: input key(s) {unknown} are not accepted by this capability "
            f"(allowed: {sorted(contract)})"
        )
    missing = sorted(name for name, spec in contract.items() if spec.required and name not in inputs)
    if missing:
        raise _reject(f"{capability_id}: missing required input(s) {missing}")

    clean: dict[str, Any] = {}
    for name, spec in contract.items():
        if name not in inputs:
            continue
        value = inputs[name]
        if spec.kind == "path":
            clean[name] = _check_path(capability_id, name, value)
        elif spec.kind == "probe-names":
            clean[name] = sorted(_check_string_list(capability_id, name, value, spec.choices))
        elif spec.kind == "secret-names":
            names = tuple(sorted(manifest.requires_scopes))
            if not names:
                raise _reject(
                    f"{capability_id}: accepts no stored credentials, so {name!r} cannot be set"
                )
            clean[name] = _check_string_list(capability_id, name, value, names)
        else:  # pragma: no cover - a new kind must be implemented before it is offered
            raise _reject(f"{capability_id}: input {name!r} has an unknown kind {spec.kind!r}")
    return clean


def _same_path(left: str, right: str) -> bool:
    try:
        return os.path.normcase(os.path.abspath(left)) == os.path.normcase(os.path.abspath(right))
    except (TypeError, ValueError):
        return False


def _to_steps(
    data: dict[str, Any],
    offered: list[dict[str, Any]],
    store: Store,
    params: dict[str, Any],
    max_steps: int,
) -> list[planner.Step]:
    if set(data) != {"steps"}:
        raise _reject(f"plan object must have exactly one key 'steps' (got {sorted(data)})")
    raw_steps = data["steps"]
    if not isinstance(raw_steps, list):
        raise _reject("'steps' must be a list")
    if not raw_steps:
        raise _reject("the model declined: the catalogue cannot achieve this goal")
    if len(raw_steps) > max_steps:
        raise _reject(f"plan has {len(raw_steps)} steps, over the cap of {max_steps}")

    by_id = {entry["capability_id"]: entry for entry in offered}
    step_ids: list[str] = []
    steps: list[planner.Step] = []
    for index, raw in enumerate(raw_steps):
        if not isinstance(raw, dict):
            raise _reject(f"step #{index + 1} is not an object")
        unknown = sorted(set(raw) - _ALLOWED_STEP_KEYS)
        if unknown:
            raise _reject(f"step #{index + 1} has unknown key(s) {unknown}")
        step_id = raw.get("step_id")
        if not isinstance(step_id, str) or not _valid_step_id(step_id):
            raise _reject(f"step #{index + 1} has an invalid step_id {step_id!r}")
        if step_id in step_ids:
            raise _reject(f"duplicate step_id {step_id!r}")
        capability_id = raw.get("capability_id")
        if capability_id not in by_id:
            raise _reject(
                f"step {step_id!r} references capability {capability_id!r}, which is not "
                f"offered (allowed: {sorted(by_id)})"
            )
        got = registry.get(store, capability_id)
        if got is None or got[1] != "healthy":
            raise _reject(f"step {step_id!r}: capability {capability_id!r} is not healthy")
        manifest = got[0]

        depends_on = raw.get("depends_on", [])
        if not isinstance(depends_on, list) or not all(isinstance(d, str) for d in depends_on):
            raise _reject(f"step {step_id!r}: depends_on must be a list of step ids")
        for dep in depends_on:
            if dep not in step_ids:
                raise _reject(
                    f"step {step_id!r} depends on {dep!r}, which is not an earlier step "
                    "(forward references and cycles are refused)"
                )

        inputs = validate_inputs(capability_id, raw.get("inputs", {}), manifest)
        # Credential-path floor (decided 2026-10-28): a plan may not point a
        # path input at credential material — secrets files, key material,
        # .env, .ssh, MJ's own store. A model that tries gets a rejection,
        # never a step.
        for violation in credential_path_violations(inputs):
            raise _reject(f"step {step_id!r}: {violation}")
        operator_dir = params.get("dir")
        if operator_dir and "path" in inputs:
            # The model saw placeholder-redacted paths and must either echo
            # them (re-bound locally) or use a path equal to the operator's
            # directory. A path that matches neither is a rejection, so the
            # model can never substitute its own directory (and a placeholder
            # the executor re-binds cannot smuggle a different real one).
            rebound = prompts.bind_home(
                prompts.canonicalize_placeholders(inputs["path"])
            )
            if not _same_path(rebound, str(operator_dir)):
                raise _reject(
                    f"step {step_id!r} uses path {inputs['path']!r} but the operator supplied "
                    f"{prompts.redact(str(operator_dir))!r}; a reasoned plan may not replace "
                    "an explicit directory"
                )
            inputs["path"] = rebound

        name = raw.get("name")
        label = name.strip() if isinstance(name, str) and name.strip() else manifest.description
        steps.append(
            planner.Step(
                step_id=step_id,
                name=label[:120],
                capability_id=capability_id,
                inputs=inputs,
                depends_on=list(depends_on),
            )
        )
        step_ids.append(step_id)
    return steps


def _valid_step_id(step_id: str) -> bool:
    import re

    return bool(re.fullmatch(STEP_ID_PATTERN, step_id))


def _build_prompt_parts(
    store: Store,
    params: dict[str, Any],
    goal: str,
) -> tuple[list[dict[str, Any]], str, str, int]:
    """The four raw ingredients of every model prompt: (offered catalogue,
    system prompt, redacted user prompt, step cap). ``propose_plan`` sends
    this; ``show_prompt`` and the CLI's ``--show-prompt`` print it instead,
    so what is reviewed is byte-for-byte what leaves the machine."""
    offered = catalogue(store)
    if not offered:
        raise ReasonerUnavailable(
            "no healthy capability has a declared input contract, so there is "
            "nothing a plan could reference"
        )
    cap = settings.max_steps()
    max_steps = cap if cap > 0 else SCHEMA_MAX_STEPS
    return offered, _system_prompt(offered, max_steps), _user_prompt(goal, params), max_steps


def show_prompt(store: Store, goal: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """The exact prompt that *would* be sent for this goal — no contact, no
    audit entry, no plan. Decided 2026-10-28: an operator can read what a
    model call would disclose before ever configuring a key."""
    _offered, system, user, max_steps = _build_prompt_parts(store, dict(params or {}), goal)
    return {
        "system": system,
        "user": user,
        "prompt_hash": prompts.hash_prompt(system, user),
        "schema": plan_schema(max_steps),
    }


def propose_plan(
    store: Store,
    goal: str,
    trust_level: str = "local-terminal",
    params: dict[str, Any] | None = None,
) -> planner.Plan:
    """Ask the configured model for a plan; validate it or raise.

    Raises ReasonerUnavailable when no model can be used at all, and
    PlanRejected when the model answered with something that is not a safe,
    registry-bound plan. Both mean the caller should fall back to asking the
    user — never to executing a guess.
    """
    params = dict(params or {})
    try:
        cfg = model.config_from_env()
    except model.ModelError as exc:
        raise ReasonerUnavailable(str(exc)) from None
    if cfg is None:
        raise ReasonerUnavailable(
            "no model configured (MJ_MODEL_PROVIDER unset); reasoning is off"
        )

    offered, system, user, max_steps = _build_prompt_parts(store, params, goal)

    # Every prompt that leaves the process is first hashed into the audit
    # log — the send is reconstructable, its content is not stored. Hashing
    # happens on the *sent* strings, after redaction.
    audit.append(
        store,
        "reasoner",
        "prompt.sent",
        {
            "model": cfg.model,
            "provider": cfg.provider,
            "prompt_hash": prompts.hash_prompt(system, user),
        },
    )

    api_token, _origin = resolve_api_key(store)
    try:
        data = model.chat_json(
            cfg,
            system=system,
            user=user,
            schema=plan_schema(max_steps),
            api_key=api_token,
        )
    except model.ModelError as exc:
        raise ReasonerUnavailable(str(exc)) from None

    steps = _to_steps(data, offered, store, params, max_steps)
    plan = planner.Plan(
        goal=goal,
        trust_level=trust_level,
        steps=steps,
        source=f"reasoner:{cfg.provider}:{cfg.model}",
    )
    try:
        planner.validate_plan(plan, store)
    except planner.PlanValidationError as exc:
        raise PlanRejected(str(exc)) from None
    return plan
