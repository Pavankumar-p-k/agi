# Copyright (c) 2024-2026 JARVIS Project
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""core/api_key_vault.py
API key management for JARVIS agents.
Reads keys from ~/.jarvis/api_keys.json, rotates on 429, tracks usage.
"""
import json
import logging
import os
from pathlib import Path

logger = logging.getLogger("api_key_vault")

VAULT_PATH = Path.home() / ".jarvis" / "api_keys.json"
USAGE_PATH = Path.home() / ".jarvis" / "key_usage.json"


class APIKeyVault:
    """Manages API keys with rotation and usage tracking."""

    def __init__(self, vault_path: str = ""):
        self.vault_path = Path(vault_path) if vault_path else VAULT_PATH
        self._keys: dict[str, list[str]] = {}
        self._index: dict[str, int] = {}
        self._usage: dict[str, dict[str, int]] = {}
        self._load()

    def _load(self):
        if self.vault_path.exists():
            try:
                self._keys = json.loads(self.vault_path.read_text(encoding="utf-8"))
                for service, keys in self._keys.items():
                    if isinstance(keys, str):
                        self._keys[service] = [keys]
                    elif not isinstance(keys, list):
                        self._keys[service] = []
                self._keys = {k: v for k, v in self._keys.items() if v}
            except Exception as e:
                logger.error(f"[VAULT] Failed to load keys: {e}")
                self._keys = {}
        else:
            logger.info(f"[VAULT] No key file at {self.vault_path} — agents will use env vars")

        for service in self._keys:
            self._index[service] = 0

        if USAGE_PATH.exists():
            try:
                self._usage = json.loads(USAGE_PATH.read_text(encoding="utf-8"))
            except Exception as e:
                logger.exception("[VAULT] Failed to load usage data: %s", e)
                self._usage = {}

    def _save_usage(self):
        USAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
        USAGE_PATH.write_text(json.dumps(self._usage, indent=2), encoding="utf-8")

    def get(self, service: str) -> str | None:
        """Return current key for service, or None if not available."""
        keys = self._keys.get(service, [])
        if not keys:
            return os.getenv(f"{service.upper()}_API_KEY") or os.getenv(service.upper()) or None
        idx = self._index.get(service, 0) % len(keys)
        key = keys[idx]
        self._track_usage(service, key)
        return key

    def rotate(self, service: str) -> str | None:
        """Rotate to next key for service. Returns new key."""
        keys = self._keys.get(service, [])
        if not keys:
            logger.warning(f"[VAULT] No keys for {service} to rotate")
            return None
        self._index[service] = (self._index.get(service, 0) + 1) % len(keys)
        new_key = self._get_current(service)
        logger.info(f"[VAULT] Rotated {service} to key index {self._index[service]}")
        self._track_usage(service, new_key, rotated=True)
        return new_key

    def on_rate_limited(self, service: str):
        """Auto-detect 429, rotate, return new key."""
        logger.warning(f"[VAULT] Rate limited on {service} — rotating")
        return self.rotate(service)

    def _get_current(self, service: str) -> str | None:
        keys = self._keys.get(service, [])
        if not keys:
            return None
        idx = self._index.get(service, 0) % len(keys)
        return keys[idx]

    def _track_usage(self, service: str, key: str, rotated: bool = False):
        if service not in self._usage:
            self._usage[service] = {}
        masked = key[:8] + "..." if key else "none"
        if masked not in self._usage[service]:
            self._usage[service][masked] = 0
        self._usage[service][masked] += 1
        if rotated:
            self._usage[service][f"{masked}_rotations"] = self._usage[service].get(f"{masked}_rotations", 0) + 1
        self._save_usage()

    def get_usage(self) -> dict:
        """Return usage stats per service."""
        return dict(self._usage)

    def list_services(self) -> list[str]:
        """Return list of configured services."""
        return sorted(self._keys.keys())

    def get_profiles(self) -> list[tuple[str, str, int]]:
        """Return (service, key, priority) tuples for all configured services."""
        profiles = []
        for service, keys in self._keys.items():
            if keys:
                # Default priority 10 for vault keys
                profiles.append((service, keys[self._index.get(service, 0) % len(keys)], 10))
        return profiles

    def has_keys(self, service: str) -> bool:
        """Check if service has any keys."""
        return bool(self._keys.get(service, [])) or bool(os.getenv(f"{service.upper()}_API_KEY"))

    def add_keys(self, service: str, keys: list[str]):
        """Add keys for a service (persisted)."""
        if service not in self._keys:
            self._keys[service] = []
        self._keys[service].extend(keys)
        self._keys[service] = list(set(self._keys[service]))
        self._save()

    def _save(self):
        self.vault_path.parent.mkdir(parents=True, exist_ok=True)
        self.vault_path.write_text(json.dumps(self._keys, indent=2), encoding="utf-8")


vault = APIKeyVault()
