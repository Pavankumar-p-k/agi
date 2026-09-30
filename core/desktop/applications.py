"""ApplicationRegistry — installed-application records with query/refresh.

Combines a persisted JSON registry with a live scan (installed programs
+ open window titles) so the planner only claims apps that are actually
present. Human approvals persist across reloads.
"""
from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional


@dataclass
class AppRecord:
    name: str
    executable: str = ""
    version: str = ""
    install_location: str = ""
    windows: list = field(default_factory=list)
    installed: bool = True
    source: str = "scan"
    approved: bool = False

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "executable": self.executable,
            "version": self.version,
            "install_location": self.install_location,
            "windows": list(self.windows),
            "installed": self.installed,
            "source": self.source,
            "approved": self.approved,
        }


class ApplicationRegistry:
    """Registry of installed applications (persisted + live scan)."""

    def __init__(self, store_path: Optional[Path] = None,
                 installed_programs_fn: Optional[Callable] = None,
                 list_windows_fn: Optional[Callable] = None) -> None:
        self._store_path = Path(store_path) if store_path else None
        self._installed_programs_fn = installed_programs_fn
        self._list_windows_fn = list_windows_fn
        self._records: dict[str, AppRecord] = {}
        self._lock = threading.Lock()
        self.refresh()

    # ── persistence ──────────────────────────────────────────────────
    def _load(self) -> None:
        if not self._store_path or not self._store_path.exists():
            return
        try:
            data = json.loads(self._store_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — store is best-effort
            return
        for item in data.get("applications", []):
            name = str(item.get("name", "")).strip()
            if not name:
                continue
            self._records[name.lower()] = AppRecord(
                name=name,
                executable=str(item.get("executable", "")),
                version=str(item.get("version", "")),
                install_location=str(item.get("install_location", "")),
                windows=list(item.get("windows", [])),
                installed=bool(item.get("installed", True)),
                source="stored",
                approved=bool(item.get("approved", False)),
            )

    def _save(self) -> None:
        if not self._store_path:
            return
        try:
            self._store_path.parent.mkdir(parents=True, exist_ok=True)
            data = {"applications": [r.to_dict()
                                     for r in self._records.values()]}
            self._store_path.write_text(json.dumps(data, indent=1),
                                        encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass

    # ── refresh ──────────────────────────────────────────────────────
    def refresh(self) -> list:
        """Reload the persisted store, then merge the live scan."""
        with self._lock:
            self._records.clear()
            self._load()

            if self._installed_programs_fn is not None:
                try:
                    result = self._installed_programs_fn() or {}
                    for prog in result.get("programs", []):
                        name = str(prog.get("Name") or prog.get("name", "")).strip()
                        if not name:
                            continue
                        key = name.lower()
                        record = self._records.get(key) or AppRecord(name=name)
                        record.version = str(prog.get("Version")
                                             or prog.get("version", "")
                                             or record.version)
                        record.install_location = str(
                            prog.get("InstallLocation")
                            or prog.get("install_location", "")
                            or record.install_location)
                        record.installed = True
                        self._records[key] = record
                except Exception:  # noqa: BLE001
                    pass

            if self._list_windows_fn is not None:
                try:
                    for window in self._list_windows_fn() or []:
                        title = str(window.get("title", "") if
                                    isinstance(window, dict) else window)
                        for record in self._records.values():
                            if record.name and record.name.lower() in title.lower():
                                if title not in record.windows:
                                    record.windows.append(title)
                except Exception:  # noqa: BLE001
                    pass

            self._save()
            return list(self._records.values())

    # ── queries ──────────────────────────────────────────────────────
    def list(self, query: Optional[str] = None) -> list:
        records = list(self._records.values())
        if query:
            q = str(query).lower()
            records = [r for r in records if q in r.name.lower()]
        return sorted(records, key=lambda r: r.name.lower())

    def has(self, name: str) -> bool:
        return str(name).lower() in self._records

    def approve(self, name: str) -> AppRecord:
        """Mark an application as human-approved (persisted)."""
        record = self._records.get(str(name).lower())
        if record is None:
            record = AppRecord(name=str(name))
            self._records[str(name).lower()] = record
        record.approved = True
        self._save()
        return record


__all__ = ["ApplicationRegistry", "AppRecord"]
