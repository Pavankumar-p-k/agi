from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_QUARANTINE_DIR = Path.home() / ".jarvis" / "quarantine"


@dataclass
class QuarantineRecord:
    provider_id: str
    publisher: str
    version: str
    fingerprint: str
    last_healthy_fingerprint: str
    failing_stage: str
    exception: str
    traceback: str
    timestamp: float
    retry_count: int
    pipeline_version: int
    manifest_version: int

    def to_dict(self) -> dict:
        return {
            "provider_id": self.provider_id,
            "publisher": self.publisher,
            "version": self.version,
            "fingerprint": self.fingerprint,
            "last_healthy_fingerprint": self.last_healthy_fingerprint,
            "failing_stage": self.failing_stage,
            "exception": self.exception,
            "traceback": self.traceback,
            "timestamp": self.timestamp,
            "retry_count": self.retry_count,
            "pipeline_version": self.pipeline_version,
            "manifest_version": self.manifest_version,
        }

    @classmethod
    def from_dict(cls, d: dict) -> QuarantineRecord:
        return cls(**d)


class QuarantineStore:
    def __init__(self) -> None:
        self._records: dict[str, QuarantineRecord] = {}
        self._load()

    def quarantine(self, record: QuarantineRecord) -> None:
        key = f"{record.publisher}/{record.provider_id}"
        existing = self._records.get(key)
        if existing:
            record.retry_count = existing.retry_count + 1
        else:
            record.retry_count = 0
        self._records[key] = record
        self._save()

    def get(self, provider_id: str, publisher: str = "") -> QuarantineRecord | None:
        for key, rec in self._records.items():
            if rec.provider_id == provider_id:
                if not publisher or rec.publisher == publisher:
                    return rec
        return None

    def remove(self, provider_id: str, publisher: str = "") -> bool:
        to_remove: list[str] = []
        for key, rec in self._records.items():
            if rec.provider_id == provider_id:
                if not publisher or rec.publisher == publisher:
                    to_remove.append(key)
        for key in to_remove:
            del self._records[key]
        if to_remove:
            self._save()
        return len(to_remove) > 0

    def list_quarantined(self) -> list[QuarantineRecord]:
        return list(self._records.values())

    def _load(self) -> None:
        try:
            path = _QUARANTINE_DIR / "quarantine.json"
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                for item in data:
                    rec = QuarantineRecord.from_dict(item)
                    key = f"{rec.publisher}/{rec.provider_id}"
                    self._records[key] = rec
        except Exception:
            pass

    def _save(self) -> None:
        try:
            _QUARANTINE_DIR.mkdir(parents=True, exist_ok=True)
            path = _QUARANTINE_DIR / "quarantine.json"
            path.write_text(
                json.dumps([r.to_dict() for r in self._records.values()], indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    def clear(self) -> None:
        self._records.clear()
        self._save()


quarantine_store = QuarantineStore()
