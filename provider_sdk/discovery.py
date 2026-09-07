from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from provider_sdk.manifest import ProviderManifest, load_manifest

logger = logging.getLogger(__name__)

_DEFAULT_SEARCH_DIRS = [
    Path.home() / ".jarvis" / "providers",
    Path.cwd() / "providers",
]


class ProviderDiscovery:
    def __init__(self) -> None:
        self._cached: dict[str, ProviderManifest] = {}
        self._search_dirs: list[Path] = []

    def add_search_dir(self, directory: str | Path) -> None:
        path = Path(directory)
        if path.is_dir() and path not in self._search_dirs:
            self._search_dirs.append(path)

    def discover_manifests(self) -> list[ProviderManifest]:
        manifests: list[ProviderManifest] = []
        seen_ids: set[str] = set()

        search_paths = self._search_dirs + _DEFAULT_SEARCH_DIRS
        for search_dir in search_paths:
            if not search_dir.is_dir():
                continue
            for pattern in ("*.json", "*.yaml", "*.yml"):
                for manifest_path in sorted(search_dir.glob(pattern)):
                    try:
                        manifest = load_manifest(manifest_path)
                        if manifest.provider_id in seen_ids:
                            continue
                        seen_ids.add(manifest.provider_id)
                        manifests.append(manifest)
                        self._cached[manifest.provider_id] = manifest
                        logger.info(
                            "[ProviderDiscovery] Discovered %s v%s from %s",
                            manifest.provider_id, manifest.version, manifest_path,
                        )
                    except Exception as e:
                        logger.debug("[ProviderDiscovery] Skipping %s: %s", manifest_path, e)
        return manifests

    def get_cached(self, provider_id: str) -> ProviderManifest | None:
        return self._cached.get(provider_id)

    def list_cached(self) -> list[ProviderManifest]:
        return list(self._cached.values())

    def clear_cache(self) -> None:
        self._cached.clear()


discovery_service = ProviderDiscovery()


def discover_providers() -> list[ProviderManifest]:
    return discovery_service.discover_manifests()
