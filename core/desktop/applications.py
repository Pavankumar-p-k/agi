"""Local registry of installed native applications and observed windows."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable
import json
import os
import time


@dataclass
class ApplicationRecord:
    name: str
    version: str = ""
    install_location: str = ""
    source: str = "windows_registry"
    windows: list[str] = field(default_factory=list)
    approved: bool = False
    updated_at: float = field(default_factory=time.time)


class ApplicationRegistry:
    def __init__(
        self,
        path: str | Path,
        installed_provider: Callable[[], dict[str, Any]],
        windows_provider: Callable[[], list[dict[str, Any]]],
    ):
        self.path = Path(path)
        self.installed_provider = installed_provider
        self.windows_provider = windows_provider
        self.records: dict[str, ApplicationRecord] = {}
        self._load()

    def refresh(self) -> list[ApplicationRecord]:
        installed = self.installed_provider().get("programs", [])
        windows = self.windows_provider()
        titles = [str(item.get("title", "")).strip() for item in windows if item.get("title")]
        for item in installed:
            name = str(item.get("Name", "")).strip()
            if not name:
                continue
            key = name.casefold()
            current = self.records.get(key, ApplicationRecord(name=name))
            current.name = name
            current.version = str(item.get("Version") or "")
            current.install_location = str(item.get("InstallLocation") or "")
            current.windows = [title for title in titles if name.casefold() in title.casefold()]
            current.updated_at = time.time()
            self.records[key] = current
        self._save()
        return self.list()

    def list(self, query: str | None = None) -> list[ApplicationRecord]:
        records = list(self.records.values())
        if query:
            needle = query.casefold()
            records = [record for record in records if needle in record.name.casefold()]
        return sorted(records, key=lambda record: record.name.casefold())

    def approve(self, name: str) -> ApplicationRecord:
        record = self._find(name)
        record.approved = True
        record.updated_at = time.time()
        self._save()
        return record

    def _find(self, name: str) -> ApplicationRecord:
        record = self.records.get(name.casefold())
        if record is None:
            raise KeyError(f"application not found: {name}")
        return record

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps({key: asdict(value) for key, value in self.records.items()}, indent=2), encoding="utf-8")
        os.replace(temp, self.path)

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            self.records = {key: ApplicationRecord(**value) for key, value in payload.items()}
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            self.records = {}
