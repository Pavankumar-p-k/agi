from __future__ import annotations

import importlib
import logging
import sys
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Diagnostic:
    severity: str
    message: str
    plugin_name: str
    component: str
    details: dict = field(default_factory=dict)
    fixable: bool = False
    fix_hint: str = ""


class PluginDoctor:
    def __init__(self, registry=None, state_store=None, secrets=None):
        self._registry = registry
        self._state_store = state_store
        self._secrets = secrets

    def set_registry(self, registry) -> None:
        self._registry = registry

    def set_state_store(self, store) -> None:
        self._state_store = store

    def set_secrets(self, secrets) -> None:
        self._secrets = secrets

    def check_plugin(self, plugin: Any) -> list[Diagnostic]:
        issues: list[Diagnostic] = []
        name = plugin.manifest.name

        if not plugin._enabled:
            issues.append(Diagnostic("info", "Plugin is disabled", name, "lifecycle", fixable=True, fix_hint="POST /api/plugins/{name}/enable"))

        if plugin._last_error:
            issues.append(Diagnostic("error", f"Last error: {plugin._last_error}", name, "lifecycle"))

        if plugin._load_attempts > 3:
            issues.append(Diagnostic("warning", f"Excessive load attempts: {plugin._load_attempts}", name, "lifecycle"))

        try:
            mod = sys.modules.get(plugin.manifest.name)
            if mod is None:
                mod = sys.modules.get(f"plugins.{plugin.manifest.name}")
            if mod is None:
                issues.append(Diagnostic("warning", "Module not in sys.modules", name, "module"))
        except Exception:
            pass

        try:
            if self._state_store:
                state = self._state_store.get_all(name)
                if state:
                    issues.append(Diagnostic("info", f"State entries: {len(state)}", name, "state"))
        except Exception as e:
            issues.append(Diagnostic("warning", f"State store error: {e}", name, "state"))

        return issues

    def check_all(self) -> list[Diagnostic]:
        all_issues: list[Diagnostic] = []
        if not self._registry:
            return all_issues

        total = self._registry.count
        enabled = len(self._registry.list_enabled())
        disabled = len(self._registry.list_disabled())

        all_issues.append(Diagnostic("info", f"Total: {total}, Enabled: {enabled}, Disabled: {disabled}", "system", "registry"))

        for name, plugin in self._registry.plugins.items():
            all_issues.extend(self.check_plugin(plugin))

        return all_issues

    def check_imports(self, plugin_name: str) -> list[Diagnostic]:
        issues: list[Diagnostic] = []
        mod = sys.modules.get(plugin_name) or sys.modules.get(f"plugins.{plugin_name}")
        if mod is None:
            issues.append(Diagnostic("error", f"Module {plugin_name} not loaded", plugin_name, "imports"))
            return issues

        try:
            from core.plugins.sandbox import validate_manifest_imports
            f = getattr(mod, "__file__", None)
            if f:
                disallowed = validate_manifest_imports(f)
                for d in disallowed:
                    issues.append(Diagnostic("warning", f"Disallowed import: {d}", plugin_name, "imports", fixable=True, fix_hint=f"Remove import {d}"))
        except Exception as e:
            issues.append(Diagnostic("error", f"Import check failed: {e}", plugin_name, "imports"))

        return issues

    def format_report(self, issues: list[Diagnostic]) -> str:
        lines = ["Plugin Doctor Report", "=" * 60]
        by_severity = {"error": [], "warning": [], "info": []}
        for d in issues:
            by_severity.setdefault(d.severity, []).append(d)

        for sev in ("error", "warning", "info"):
            items = by_severity.get(sev, [])
            if not items:
                continue
            lines.append(f"\n{sev.upper()} ({len(items)}):")
            lines.append("-" * 40)
            for d in items:
                line = f"  [{d.plugin_name}:{d.component}] {d.message}"
                if d.fixable:
                    line += f"  (fix: {d.fix_hint})"
                lines.append(line)

        lines.append(f"\n{'=' * 60}")
        lines.append(f"Total: {len(issues)} ({len(by_severity.get('error', []))} errors, {len(by_severity.get('warning', []))} warnings)")
        return "\n".join(lines)
