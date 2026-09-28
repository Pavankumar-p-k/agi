"""ProviderRegistry — priority-ordered, capability-indexed provider store.

Contract (tests/architecture/test_capability_gates.py, clean_registry fixture):
instances expose _providers, _priorities, _capability_index and
_pending_settings; register()/unregister() maintain the capability index.
"""
from __future__ import annotations

import json
import os
import threading
from typing import Any, Optional

# Reentrant: register() re-enters unregister() while holding the lock.
_lock_factory = threading.RLock

from core.providers.base import ExecutionProvider


class ProviderRegistry:
    """Thread-safe registry of execution providers with a capability index."""

    def __init__(self, settings_dir: Optional[str] = None) -> None:
        self._providers: dict[str, ExecutionProvider] = {}
        self._priorities: dict[str, int] = {}
        self._capability_index: dict[str, list[str]] = {}
        self._pending_settings: dict[str, dict] = {}
        self._lock = _lock_factory()
        self._PROVIDER_SETTINGS_DIR = settings_dir or os.path.expanduser(
            "~/.jarvis/provider_settings")
        self._PROVIDER_SETTINGS_FILE = os.path.join(
            self._PROVIDER_SETTINGS_DIR, "registry.json")
        self._load_settings()

    # ── persistence ──────────────────────────────────────────────────
    def _load_settings(self) -> None:
        try:
            if os.path.exists(self._PROVIDER_SETTINGS_FILE):
                with open(self._PROVIDER_SETTINGS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    self._pending_settings = data
        except Exception:  # noqa: BLE001 — settings are best-effort
            self._pending_settings = {}

    def _save_settings(self) -> None:
        try:
            os.makedirs(self._PROVIDER_SETTINGS_DIR, exist_ok=True)
            with open(self._PROVIDER_SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(self._pending_settings, f, indent=2)
        except Exception:  # noqa: BLE001
            pass

    # ── registration ─────────────────────────────────────────────────
    def register(self, provider: ExecutionProvider, priority: int = 50) -> None:
        pid = provider.provider_id
        with self._lock:
            # Remove any previous registration of the same id
            self.unregister(pid)
            self._providers[pid] = provider
            self._priorities[pid] = int(priority)
            for cap in provider.capabilities().capability_names:
                self._capability_index.setdefault(cap, []).append(pid)
            if pid in self._pending_settings:
                try:
                    provider._enabled = bool(
                        self._pending_settings[pid].get("enabled", True))
                except Exception:  # noqa: BLE001
                    pass

    def unregister(self, provider_id: str) -> bool:
        with self._lock:
            provider = self._providers.pop(provider_id, None)
            self._priorities.pop(provider_id, None)
            if provider is None:
                return False
            caps = provider.capabilities().capability_names
            for cap in caps:
                pids = self._capability_index.get(cap, [])
                if provider_id in pids:
                    pids.remove(provider_id)
                if not pids:
                    self._capability_index.pop(cap, None)
            return True

    # ── lookup ───────────────────────────────────────────────────────
    def has_capability(self, capability: str) -> bool:
        with self._lock:
            return bool(self._capability_index.get(capability))

    def providers_for_capability(self, capability: str) -> list[ExecutionProvider]:
        """Providers supporting a capability, best priority first (stable)."""
        with self._lock:
            pids = list(self._capability_index.get(capability, []))
            pairs = [(self._priorities.get(p, 100), p, p) for p in pids]
            pairs.sort(key=lambda t: (-t[0], t[1]))
            return [self._providers[p] for _, _, p in pairs]

    def get(self, provider_id: str) -> Optional[ExecutionProvider]:
        with self._lock:
            return self._providers.get(provider_id)

    def all_providers(self) -> list[ExecutionProvider]:
        with self._lock:
            return list(self._providers.values())

    def capabilities(self) -> list[str]:
        with self._lock:
            return sorted(self._capability_index.keys())

    def priorities(self) -> dict[str, int]:
        with self._lock:
            return dict(self._priorities)

    def __len__(self) -> int:
        return len(self._providers)

    # ── settings ─────────────────────────────────────────────────────
    def set_enabled(self, provider_id: str, enabled: bool) -> bool:
        with self._lock:
            provider = self._providers.get(provider_id)
            if provider is None:
                return False
            provider._enabled = bool(enabled)
            self._pending_settings[provider_id] = {
                **self._pending_settings.get(provider_id, {}),
                "enabled": bool(enabled),
            }
        self._save_settings()
        return True

    def to_dict(self) -> dict:
        with self._lock:
            return {
                pid: p.to_dict() if hasattr(p, "to_dict") else {"provider_id": pid}
                for pid, p in self._providers.items()
            }


# Module-level default registry (tests monkeypatch/patch this object).
provider_registry = ProviderRegistry()
_default_registry: Optional[ProviderRegistry] = None


def get_provider_registry() -> ProviderRegistry:
    global _default_registry
    if _default_registry is None:
        _default_registry = provider_registry
    return _default_registry


__all__ = ["ProviderRegistry", "provider_registry", "get_provider_registry"]
