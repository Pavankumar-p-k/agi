"""YAML role→scope loader.

The file format is a mapping of role name to a list of scope strings::

    analyst:
      - memory:read
      - tools:execute:low

Loaded grants are applied to the module-level policy engine.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Iterable, Optional

from core.authz.engine import PolicyEngine, authz_engine
from core.authz.schema import Role

logger = logging.getLogger(__name__)

DEFAULT_ROLES_PATH = "config/roles.yaml"


class PolicyLoader:
    """Loads role→scope grants from YAML into a policy engine."""

    def __init__(self, roles_path: Any = None, engine: Optional[PolicyEngine] = None) -> None:
        self.roles_path = Path(roles_path or DEFAULT_ROLES_PATH)
        self.engine = engine

    # ── internals ───────────────────────────────────────────────────
    @staticmethod
    def _parse_role(name: str) -> Any:
        try:
            return Role(str(name).strip().lower())
        except ValueError:
            return str(name).strip().lower()

    def _target_engine(self) -> PolicyEngine:
        # ``authz_engine`` is resolved lazily so tests can patch the
        # module-level attribute.
        return self.engine or authz_engine

    # ── public API ──────────────────────────────────────────────────
    def load_all(self) -> dict:
        """Apply every role grant in the roles file. Returns {role: scopes}."""
        import yaml  # local import — PyYAML is only needed when loading

        if not self.roles_path.exists():
            logger.debug("roles file not found: %s", self.roles_path)
            return {}

        with open(self.roles_path, "r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        if not isinstance(data, dict):
            logger.warning("roles file %s is not a mapping — ignoring", self.roles_path)
            return {}

        engine = self._target_engine()
        applied: dict = {}
        for name, scopes in data.items():
            if scopes is None:
                scopes = []
            if not isinstance(scopes, Iterable) or isinstance(scopes, (str, bytes)):
                logger.warning("role %s has non-list scopes — skipping", name)
                continue
            role = self._parse_role(name)
            engine.register_role(role, list(scopes))
            applied[str(name)] = list(scopes)
        return applied


__all__ = ["PolicyLoader", "DEFAULT_ROLES_PATH"]
