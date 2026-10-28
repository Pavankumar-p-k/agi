"""A floor about where any step may point a path.

Step inputs are checked twice: the reasoner refuses paths into credential
territory while *building* a plan, and the runner refuses them again no
matter which planner produced the plan — the same defense-in-depth as the
effects floor (docs/09 §3), so a plan that bypassed one check still cannot
run. Executed decision: **agent decided, 2026-10-28 session, on operator
instruction** — a worker asking for a credential file outside MJ's own
store is refused, and MJ's own store file is refused as a path input too
(credentials live encrypted inside it; a worker has no business reading
the raw database).

What counts:
  * a path segment or file stem naming credentials, secrets, tokens, key
    material, or a ``.env`` file — after ``os.path.splitext``, so
    ``credentials.json`` and ``id_rsa.pub`` are caught;
  * well-known credential directories (``.ssh``, ``.gnupg``, ``.aws``,
    ``.kube``, ``.docker``, ``.password-store``);
  * MJ's own database file itself.

Deliberately a *name* rule, not policy-file content: an operator can add
denials in ``MJ_POLICY``, but this floor does not depend on that diligence.

Only names are matched — contents are never opened here — so the check can
be precise about what it refuses and cheap to call.
"""

from __future__ import annotations

import os
from typing import Any

#: Input keys whose values are paths. A value under any other key is *not*
#: scanned: a prose field may legitimately mention a word like "token" and
#: must not be turned into a refusal.
PATH_INPUT_KEYS = frozenset(
    {
        "path",
        "dir",
        "directory",
        "file",
        "filename",
        "filepath",
        "file_path",
        "folder",
        "source",
        "target",
        "root",
    }
)

#: Path segments (or file stems, after splitext) that name credential
#: material. Case-insensitive; an exact match on the segment or its stem.
_CREDENTIAL_STEMS = frozenset(
    {
        "credential",
        "credentials",
        "password",
        "passwd",
        "keyring",
        "keystore",
        "id_rsa",
        "id_dsa",
        "id_ecdsa",
        "id_ed25519",
        "private_key",
        "privatekey",
        "netrc",
        "htpasswd",
        "authtoken",
        "auth_token",
        "secrets",
        "secret",
        "secretini",
        "token",
        "tokens",
        "tokenstore",
        "credential_store",
        "credentialstore",
    }
)

#: Whole directories that are credential storage regardless of what they
#: contain. Matched against the path segment itself, lowercased.
_CREDENTIAL_DIRS = frozenset(
    {
        ".ssh",
        ".gnupg",
        ".aws",
        ".kube",
        ".docker",
        ".password-store",
    }
)

#: Files that name credential storage regardless of directory.
#: ".env" and anything it prefixes (".env.local", ...) are caught below.
_ENV_PREFIX = ".env"

#: MJ's own database file. A path input that names it — or any other file
#: with that name — is refused: it is credential material by definition.
_OWN_STORE_FILES = frozenset({"mj.sqlite3"})

#: Marker describing a refusal message.
REFUSAL_PREFIX = "credential path floor:"


def _is_credential_name(raw_part: str) -> bool:
    """True for a path segment or stem that names credential material."""
    part = raw_part.strip().lower()
    if not part or part in (".", ".."):
        return False
    if part in _CREDENTIAL_DIRS or part in _OWN_STORE_FILES:
        return True
    if part.startswith(_ENV_PREFIX):
        return True
    stem = os.path.splitext(part)[0]
    return stem in _CREDENTIAL_STEMS


def _walk_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for child in value.values() for s in _walk_strings(child)]
    if isinstance(value, (list, tuple)):
        return [s for child in value for s in _walk_strings(child)]
    return []


def _bad_reasons(value: str, forbidden_roots: tuple[str, ...]) -> list[str]:
    """Reasons this *one* string is refused. ``forbidden_roots`` names files
    (MJ's own store) that no path input may ever equal or differ from only by
    letter case — the store's raw database is credential material itself."""
    caseless = os.path.normcase(value.strip())
    normalized = os.path.normpath(value.strip()).replace("\\", "/").lower()
    parts = [p for p in normalized.split("/") if p]
    out = [f"credential material named: {p!r}" for p in sorted({p for p in parts if _is_credential_name(p)})]
    for root in forbidden_roots:
        if caseless == os.path.normcase(root.strip()):
            out.append("names MJ's own store")
    return sorted(set(out))


def credential_path_violations(
    inputs: dict[str, Any], forbidden_roots: tuple[str, ...] = ()
) -> list[str]:
    """Refusal reasons for this step's inputs, or ``[]`` when clean.

    Only values of path-typed keys are examined (see PATH_INPUT_KEYS).
    """
    reasons: list[str] = []
    for key, value in inputs.items():
        keyname = str(key).strip().lower()
        if keyname not in PATH_INPUT_KEYS:
            continue
        for candidate in _walk_strings(value):
            hits = _bad_reasons(candidate, forbidden_roots)
            for hit in hits:
                reasons.append(f"input {key!r}: {hit} (path {candidate!r})")
    return sorted(set(reasons))
