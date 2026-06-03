from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from packaging.version import Version

logger = logging.getLogger(__name__)


@dataclass
class Migration:
    from_version: str
    to_version: str
    description: str
    migrate: Callable[[dict], dict]
    risks: list[str] = field(default_factory=list)

    @property
    def version_pair(self) -> tuple[str, str]:
        return (self.from_version, self.to_version)

    def applies_to(self, current: str) -> bool:
        try:
            return Version(current) < Version(self.to_version) and Version(current) >= Version(self.from_version)
        except Exception:
            return current == self.from_version


@dataclass
class MigrationPlan:
    plugin_name: str
    from_version: str
    to_version: str
    steps: list[Migration]
    backup: dict | None = None

    @property
    def step_count(self) -> int:
        return len(self.steps)


class MigrationEngine:
    def __init__(self):
        self._migrations: dict[str, list[Migration]] = {}

    def register(self, plugin_name: str, migration: Migration) -> None:
        self._migrations.setdefault(plugin_name, []).append(migration)
        self._migrations[plugin_name].sort(key=lambda m: Version(m.to_version))
        logger.debug("[Migration] Registered %s: %s -> %s", plugin_name, migration.from_version, migration.to_version)

    def detect(self, plugin_name: str, current_version: str) -> list[Migration]:
        return [m for m in self._migrations.get(plugin_name, []) if m.applies_to(current_version)]

    def plan(self, plugin_name: str, current_version: str, current_config: dict) -> MigrationPlan:
        steps = self.detect(plugin_name, current_version)
        if not steps:
            return MigrationPlan(plugin_name=plugin_name, from_version=current_version, to_version=current_version, steps=[])
        return MigrationPlan(
            plugin_name=plugin_name,
            from_version=current_version,
            to_version=steps[-1].to_version,
            steps=steps,
            backup=dict(current_config),
        )

    async def apply(self, plan: MigrationPlan) -> tuple[bool, dict, list[str]]:
        config = dict(plan.backup) if plan.backup else {}
        errors = []
        for step in plan.steps:
            try:
                result = step.migrate(config)
                if result is not None:
                    config = result
                logger.info("[Migration] Applied %s: %s -> %s", plan.plugin_name, step.from_version, step.to_version)
            except Exception as e:
                errors.append(f"Step {step.from_version}->{step.to_version}: {e}")
                logger.exception("[Migration] Failed: %s", e)
                if plan.backup is not None:
                    config = dict(plan.backup)
                    logger.info("[Migration] Rolled back %s to version %s", plan.plugin_name, plan.from_version)
                return False, config, errors
        return True, config, errors

    def list_registered(self, plugin_name: str | None = None) -> dict[str, list[dict]]:
        if plugin_name:
            return {
                plugin_name: [
                    {"from": m.from_version, "to": m.to_version, "desc": m.description}
                    for m in self._migrations.get(plugin_name, [])
                ]
            }
        return {
            name: [{"from": m.from_version, "to": m.to_version, "desc": m.description} for m in migrations]
            for name, migrations in self._migrations.items()
        }
