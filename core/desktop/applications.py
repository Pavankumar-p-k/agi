"""ApplicationRegistry — installed-application records with query/refresh.

Combines a persisted JSON registry with a live scan (UserActions.
installed_programs / window titles) so the planner only claims apps
that are actually present.
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
    installed: bool = True
    source: str = "scan"

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "executable": self.executable,
            "installed": self.installed,
            "source": self.source,
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

    def refresh(self) -> None:
        """Reload the persisted store, then merge the live scan."""
        with self._lock:
            self._records.clear()
            if self._store_path and self._store_path.exists():
                try:
                    data = json.loads(
                        self._store_path.read_text(encoding="utf-8"))
                    for item in data.get("applications", []):
                        record = AppRecord(
                            name=str(item.get("name", "")),
                            executable=str(item.get("executable", "")),
                            source="stored",
                        )
                        if record.name:
                            self._records[record.name.lower()] = record
                except Exception:  # noqa: BLE001
                    pass
            if self._installed_programs_fn is not None:
                try:
                    result = self._installed_programs_fn()
                    for prog in result.get("programs", []):
                        name = str(prog.get("name", "")).strip()
                        if not name:
                            continue
                        key = name.lower()
                        if key in self._records:
                            self._records[key].installed = True
                        else:
                            self._records[key] = AppRecord(
                                name=name, source="scan")
                except Exception:  # noqa: BLE001
                    pass

    def list(self, query: Optional[str] = None) -> list:
        records = list(self._records.values())
        if query:
            q = str(query).lower()
            records = [r for r in records if q in r.name.lower()]
        return sorted(records, key=lambda r: r.name.lower())

    def has(self, name: str) -> bool:
        return str(name).lower() in self._records


__all__ = ["ApplicationRegistry", "AppRecord"]
