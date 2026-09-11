from __future__ import annotations

from pathlib import Path
import yaml

from core.authz.engine import authz_engine
from core.authz.schema import Role


class PolicyLoader:
    def __init__(self, roles_path: str = "config/roles.yaml") -> None:
        self.roles_path = Path(roles_path)

    def load_all(self) -> None:
        if not self.roles_path.exists():
            return
        payload = yaml.safe_load(self.roles_path.read_text(encoding="utf-8")) or {}
        for name, scopes in payload.items():
            role = Role(str(name).lower()) if str(name).lower() in {r.value for r in Role} else Role.ANALYST
            authz_engine.register_role(role, set(scopes or []))
