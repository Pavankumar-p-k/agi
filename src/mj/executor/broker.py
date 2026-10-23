"""The credential broker — no raw token ever reaches planner or model.

Secrets are stored encrypted at rest under the MJ home directory, keyed by a
name, and only decrypted at the moment a step runs. Steps reference secrets by
*name* (manifest input, plan payload); the runner injects the value into the
worker's stdin payload immediately before execution and scrubs the value out
of anything the worker hands back. The name is what appears in the audit
trail, approvals, and reports — never the value. (This closes the "no
credential broker yet" open item, docs/07 §6.)

Gating policy (docs/09 §3): a step that declares the ``secrets`` effect is R3
by floor and may only run on the local terminal. The manifest's
``requires_scopes`` lists the secret *names* it may draw from; the runner
enforces that every injected name is in scope.

Encryption: AES-256-GCM from the `cryptography` package — a vetted AEAD, not
hand-assembled primitives. Each record carries a fresh random 12-byte nonce,
and the secret's *name* is authenticated as associated data, so a record
renamed to a different secret (or copied from another broker home) refuses to
decrypt instead of silently yielding the wrong credential.

Master key: 32 random bytes, resolved in this order:
  1. ``MJ_BROKER_KEY`` (hex, at least 32 bytes) — explicit operator/test
     override. The runner strips it from every worker's environment: values
     reach a worker through its stdin payload, never through inherited env.
  2. the OS credential store through `keyring` (Windows Credential Manager,
     macOS Keychain, Secret Service) — generated once, read without prompts,
     so background tasks keep working.
  3. a mode-0600 key file next to the encrypted records — the headless
     fallback (CI without a Secret Service). Real entropy, never derived from
     public identifiers like the user or host name.

Records written by the old hand-rolled format (v1) are refused with a clear
"re-set the secret" error rather than silently mis-decrypted.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from mj.core.store import Store

_KEY_ENV = "MJ_BROKER_KEY"
_KEYRING_SERVICE = "mj-broker"
_KEYRING_USER = "master-key"
_KEY_FILE = ".master.key"
_KEY_BYTES = 32
_NONCE_BYTES = 12
_VERSION = 2

# A secret shorter than this cannot be told apart from ordinary output, so
# the redaction sweep below could not scrub it reliably. Refuse it up front.
MIN_SECRET_LEN = 4


class BrokerError(RuntimeError):
    """Raised when the broker cannot decrypt or find a secret."""


# -- master key ---------------------------------------------------------------


def _key_from_env() -> bytes | None:
    raw_hex = os.environ.get(_KEY_ENV)
    if not raw_hex:
        return None
    try:
        raw = bytes.fromhex(raw_hex)
    except ValueError as exc:
        raise BrokerError(f"{_KEY_ENV} must be hex-encoded bytes") from exc
    if len(raw) < _KEY_BYTES:
        raise BrokerError(f"{_KEY_ENV} must be at least {_KEY_BYTES} bytes")
    return raw if len(raw) == _KEY_BYTES else hashlib.sha256(raw).digest()


def _keyring_read() -> str | None:
    """The stored key, or None when the OS store is absent/empty/unreachable."""
    try:
        import keyring
        from keyring.errors import KeyringError
    except ImportError:
        return None
    try:
        return keyring.get_password(_KEYRING_SERVICE, _KEYRING_USER)
    except KeyringError:
        return None


def _keyring_write(hex_key: str) -> bool:
    """Persist the key in the OS store. False when it is unavailable."""
    try:
        import keyring
        from keyring.errors import KeyringError
    except ImportError:
        return False
    try:
        keyring.set_password(_KEYRING_SERVICE, _KEYRING_USER, hex_key)
    except KeyringError:
        return False
    return True


def _key_file_path(store: Store) -> Path:
    return _repo_dir(store) / _KEY_FILE


def _read_key_file(path: Path) -> bytes:
    try:
        raw = bytes.fromhex(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError) as exc:
        raise BrokerError(f"master key file {path} is unreadable or malformed") from exc
    if len(raw) != _KEY_BYTES:
        raise BrokerError(f"master key file {path} does not hold {_KEY_BYTES} bytes")
    return raw


def _write_key_file(path: Path, raw: bytes) -> None:
    """Create the key file once, owner-only. (Windows ignores the mode bits;
    the file inherits the user profile's ACL, which is the best available
    there without a keyring — this is the documented fallback, not the norm.)"""
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return  # a concurrent first use won the race; its key is the key
    try:
        os.write(fd, raw.hex().encode("ascii"))
        os.fsync(fd)
    finally:
        os.close(fd)


def _load_key(store: Store) -> bytes:
    """Resolve the master key: env override, OS keyring, then key file."""
    env_key = _key_from_env()
    if env_key is not None:
        return env_key

    stored = _keyring_read()
    if stored:
        try:
            raw = bytes.fromhex(stored)
        except ValueError as exc:
            raise BrokerError("master key in the OS credential store is malformed") from exc
        if len(raw) != _KEY_BYTES:
            raise BrokerError(
                "master key in the OS credential store is the wrong length; "
                "delete it and re-set the affected secrets"
            )
        return raw

    path = _key_file_path(store)
    if path.is_file():
        return _read_key_file(path)

    raw = os.urandom(_KEY_BYTES)
    if _keyring_write(raw.hex()):
        return raw
    _write_key_file(path, raw)
    return _read_key_file(path)


# -- storage ------------------------------------------------------------------


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _unb64(label: str, value: Any) -> bytes:
    try:
        return base64.b64decode(value, validate=True)
    except (TypeError, ValueError) as exc:
        raise BrokerError(f"secret record field {label!r} is malformed") from exc


def _encrypt(store: Store, name: str, plaintext: bytes) -> dict[str, Any]:
    nonce = os.urandom(_NONCE_BYTES)
    ciphertext = AESGCM(_load_key(store)).encrypt(nonce, plaintext, name.encode("utf-8"))
    return {
        "v": _VERSION,
        "alg": "aes-256-gcm",
        "nonce": _b64(nonce),
        "ct": _b64(ciphertext),
    }


def _decrypt(store: Store, name: str, rec: dict[str, Any]) -> bytes:
    if rec.get("v") != _VERSION:
        raise BrokerError(
            f"secret {name!r} uses an older broker format (v{rec.get('v')!r}); "
            f"re-set it: mj secrets set {name}"
        )
    nonce = _unb64("nonce", rec.get("nonce"))
    ciphertext = _unb64("ct", rec.get("ct"))
    try:
        return AESGCM(_load_key(store)).decrypt(nonce, ciphertext, name.encode("utf-8"))
    except InvalidTag as exc:
        raise BrokerError(
            f"secret {name!r} failed authentication (tampered record, renamed "
            "file, or wrong master key)"
        ) from exc


def _repo_dir(store: Store) -> Path:
    p = store.path.parent / "broker"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _record_path(store: Store, name: str) -> Path:
    return _repo_dir(store) / f"{name}.json"


def _read_record(store: Store, name: str) -> dict[str, Any] | None:
    path = _record_path(store, name)
    if not path.is_file():
        return None
    try:
        rec = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise BrokerError(f"secret {name!r} record is unreadable") from exc
    if not isinstance(rec, dict):
        raise BrokerError(f"secret {name!r} record is malformed")
    return rec


def _write_record(store: Store, name: str, rec: dict[str, Any]) -> None:
    path = _record_path(store, name)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(rec, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


# -- public API ---------------------------------------------------------------


def set_secret(store: Store, name: str, value: str) -> None:
    """Encrypt and persist a secret by name."""
    if not name or not name.replace("-", "").replace("_", "").isalnum():
        raise BrokerError(f"secret name {name!r} is malformed")
    if len(value) < MIN_SECRET_LEN:
        raise BrokerError(
            f"secret {name!r} is shorter than {MIN_SECRET_LEN} characters; "
            "values this short cannot be redacted from worker output"
        )
    rec = _encrypt(store, name, value.encode("utf-8"))
    rec["created"] = time.time()
    _write_record(store, name, rec)


def get_secret(store: Store, name: str) -> str | None:
    """Decrypt and return a secret by name, or None if not found."""
    rec = _read_record(store, name)
    if rec is None:
        return None
    return _decrypt(store, name, rec).decode("utf-8")


def secret_meta(store: Store, name: str) -> dict[str, Any] | None:
    """Name and timestamps only — never the value (that is what `secrets get`
    shows, and all an agent may see)."""
    rec = _read_record(store, name)
    if rec is None:
        return None
    return {"key": name, "created": rec.get("created"), "last_used": rec.get("last_used")}


def delete_secret(store: Store, name: str) -> bool:
    path = _record_path(store, name)
    if path.is_file():
        path.unlink()
        return True
    return False


def list_secrets(store: Store) -> list[str]:
    """Names only — never values."""
    return sorted(p.stem for p in _repo_dir(store).glob("*.json"))


def known_secrets(store: Store) -> dict[str, str]:
    """Every stored secret, name -> value, for scrubbing worker output.

    Best effort: a record that cannot be decrypted (wrong master key,
    tampering) is skipped rather than failing the step.
    """
    values: dict[str, str] = {}
    for name in list_secrets(store):
        try:
            value = get_secret(store, name)
        except BrokerError:
            continue
        if value:
            values[name] = value
    return values


def redact(value: Any, secrets: dict[str, str]) -> Any:
    """Scrub every known secret value out of anything a worker handed back.

    Everything coming out of a worker — output, exception text, a stderr
    tail — passes through here before it is recorded, reported, or printed.
    Longest values are replaced first so a secret containing another secret
    is scrubbed whole.
    """
    if not secrets:
        return value
    return _redact_walk(value, secrets)


def _redact_walk(value: Any, secrets: dict[str, str]) -> Any:
    if isinstance(value, str):
        for name in sorted(secrets, key=lambda n: -len(secrets[n])):
            secret = secrets[name]
            if len(secret) >= MIN_SECRET_LEN and secret in value:
                value = value.replace(secret, f"[REDACTED:{name}]")
        return value
    if isinstance(value, dict):
        return {_redact_walk(k, secrets): _redact_walk(v, secrets) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact_walk(v, secrets) for v in value]
    return value


def notes_from_inputs(inputs: dict[str, Any]) -> list[str]:
    """Names (never values) of the credentials in these step inputs."""
    raw = inputs.get("secrets") or inputs.get("use_secret")
    if isinstance(raw, str):
        raw = [raw]
    return [str(s) for s in (raw or []) if isinstance(s, (str, Path))]


def inject_secrets(store: Store, inputs: dict[str, Any], allowed: list[str]) -> dict[str, Any]:
    """Return a copy of `inputs` with `secrets` resolved to real values.

    `allowed` (from manifest.requires_scopes) constrains which names may be
    injected; anything else raises so a compromised plan cannot exfiltrate.
    Values are returned in a brand-new dict — the caller (runner) passes this
    to the worker subprocess and then drops it.
    """
    names = notes_from_inputs(inputs)
    out = dict(inputs)
    resolved: dict[str, str] = {}
    allowed_set = set(allowed)
    for n in names:
        if n not in allowed_set:
            raise BrokerError(
                f"secret {n!r} is not in this capability's requires_scopes"
            )
        val = get_secret(store, n)
        if val is None:
            raise BrokerError(f"secret {n!r} not found in broker")
        resolved[n] = val
        rec = _read_record(store, n)
        if rec is not None:
            rec["last_used"] = time.time()
            _write_record(store, n, rec)
    if resolved:
        out["secrets"] = {**resolved}
    return out
