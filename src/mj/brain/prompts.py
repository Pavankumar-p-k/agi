"""What may leave the machine for the model to see — decided 2026-10-28.

An allowlist, not a blocklist: only the goal text, the capability catalogue
(names and declared input schemas, as `reasoner.catalogue` builds them) and
the operator's ``--dir`` are ever placed in a prompt. File contents, secret
names or values, environment variables and credential paths are never
collected for a prompt in the first place, and the identity strings that
appear *inside* the allowed pieces — the home-directory prefix, the account
username, the machine hostname — are rewritten to stable placeholders
(``<HOME>``, ``<USER>``, ``<HOST>``) before one byte is sent. The executor
re-binds ``<HOME>`` locally when it validates a plan, so the model can still
echo the operator's directory back.

Nothing is trusted about these definitions: ``hash_prompt`` returns the
SHA-256 of the exact canonical prompt blob, and the planner records that
hash in the audit log for every prompt actually sent — so what left the
machine is always reconstructable to a byte, but its content is never
stored (the goal text belongs to the operator, the catalogue to the
registry, and neither belongs in a log).
"""

from __future__ import annotations

import hashlib
import os
import re
import socket

from mj.core.store import canonical_json

HOME_PLACEHOLDER = "<HOME>"
USER_PLACEHOLDER = "<USER>"
HOST_PLACEHOLDER = "<HOST>"

#: Placeholders the model is allowed to echo back and the executor re-binds.
PLACEHOLDERS = (HOME_PLACEHOLDER, USER_PLACEHOLDER, HOST_PLACEHOLDER)


def _identities() -> list[tuple[str, str]]:
    """(placeholder, identity string) pairs, most specific first.

    The home directory is rewritten before the bare username because the
    home path *contains* the username; the hostname is last. Each pair is
    bound explicitly: a hostname that happens to equal the account name
    must still land on its own placeholder, never on whichever one zip
    happens to pair it with."""
    home = os.path.expanduser("~").strip()
    username = home.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1] if home else ""
    host = (socket.gethostname() or "").strip()
    pairs: list[tuple[str, str]] = []
    if home and len(home) > 1:
        pairs.append((HOME_PLACEHOLDER, home))
    if username and len(username) > 1:
        pairs.append((USER_PLACEHOLDER, username))
    if host and len(host) > 1:
        pairs.append((HOST_PLACEHOLDER, host))
    return pairs


def identities() -> list[str]:
    """The concrete strings this machine's prompts will never contain."""
    return [identity for _placeholder, identity in _identities()]


def redact(text: str) -> str:
    """Rewrite identity strings to placeholders, case-insensitively.

    Order matters: the home directory (the longest, most specific string)
    first, then the bare username, then the hostname — each bound to its
    own placeholder explicitly (see ``_identities``)."""
    out = text
    for placeholder, identity in _identities():
        out = re.sub(re.escape(identity), placeholder, out, flags=re.IGNORECASE)
    return out


def canonicalize_placeholders(value: str) -> str:
    """Normalize any letter-casing of a placeholder to the canonical form,
    so a model-echoed ``<home>`` binds exactly like ``<HOME>``."""
    for placeholder in PLACEHOLDERS:
        pattern = re.compile(re.escape(placeholder), re.IGNORECASE)
        value = pattern.sub(placeholder, value)
    return value


def bind_home(value: str) -> str:
    """Turn a model-echoed placeholder path back into a real local path."""
    home = os.path.expanduser("~").strip()
    if not home:
        return value
    return value.replace(HOME_PLACEHOLDER, home)


def prompt_blob(system: str, user: str) -> str:
    """The exact bytes whose hash is audited for every prompt sent."""
    return canonical_json({"system": system, "user": user})


def hash_prompt(system: str, user: str) -> str:
    return hashlib.sha256(prompt_blob(system, user).encode("utf-8")).hexdigest()
