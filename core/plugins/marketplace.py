from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
import zipfile
from dataclasses import dataclass, field
from typing import Any, Optional

from .errors import PluginNetworkError, PluginDependencyError
from .manifest import PluginManifest
from .verification import ManifestVerifier

logger = logging.getLogger("jarvis.plugins.marketplace")

try:
    import httpx
except ImportError:
    httpx = None  # type: ignore


@dataclass
class MarketplaceIndex:
    plugins: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    etag: str = ""


class PluginMarketplace:
    """Remote plugin marketplace client with caching.

    Phase 3d: Plugin marketplace integration.
    Fetches plugin index from a remote URL, caches with ETag,
    and provides search/list/info/install pipeline.
    """

    def __init__(
        self,
        url: str = "https://plugins.jarvis.ai/v1",
        timeout: float = 10.0,
        cache_dir: Optional[str] = None,
    ):
        self._url = url.rstrip("/")
        self._timeout = timeout
        self._cache_dir = cache_dir or os.path.join(
            tempfile.gettempdir(), "jarvis_plugin_marketplace"
        )
        self._index: MarketplaceIndex = MarketplaceIndex()
        self._http_client: Optional[httpx.AsyncClient] = None

    async def _ensure_client(self):
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=self._timeout)

    async def close(self):
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    async def refresh_index(self) -> bool:
        """Fetch the latest plugin index from the marketplace.

        Uses ETag/If-None-Match for bandwidth efficiency.
        Returns True if index was updated.
        """
        if httpx is None:
            logger.warning("[MARKETPLACE] httpx not available — cannot fetch index")
            return False

        await self._ensure_client()

        headers = {}
        if self._index.etag:
            headers["If-None-Match"] = self._index.etag

        try:
            r = await self._http_client.get(f"{self._url}/index.json", headers=headers)
        except Exception as e:
            logger.warning("[MARKETPLACE] Cannot fetch index: %s", e)
            return False

        if r.status_code == 304:
            logger.debug("[MARKETPLACE] Index unchanged (304)")
            return False

        if r.status_code != 200:
            logger.warning("[MARKETPLACE] Index returned HTTP %d", r.status_code)
            return False

        try:
            data = r.json()
        except Exception as e:
            logger.error("[MARKETPLACE] Invalid index JSON: %s", e)
            return False

        self._index = MarketplaceIndex(
            plugins=data.get("plugins", {}),
            etag=r.headers.get("etag", ""),
        )
        logger.info("[MARKETPLACE] Index refreshed: %d plugins", len(self._index.plugins))
        return True

    def search(self, query: str) -> list[dict[str, Any]]:
        """Search for plugins by name, description, or author.

        Case-insensitive substring match.
        """
        q = query.lower()
        results: list[dict[str, Any]] = []
        for plugin_id, versions in self._index.plugins.items():
            latest = versions[-1] if versions else {}
            if (
                q in plugin_id.lower()
                or q in latest.get("name", "").lower()
                or q in latest.get("description", "").lower()
                or q in latest.get("author", "").lower()
            ):
                results.append({"id": plugin_id, **latest})
        return results

    def list_versions(self, plugin_id: str) -> list[dict[str, Any]]:
        """List all available versions of a plugin."""
        return self._index.plugins.get(plugin_id, [])

    def info(self, plugin_id: str, version: str = "") -> dict[str, Any]:
        """Get metadata for a specific plugin version."""
        versions = self._index.plugins.get(plugin_id, [])
        if not versions:
            return {}
        if version:
            for v in versions:
                if v.get("version") == version:
                    return v
            return {}
        return versions[-1]  # latest

    async def download(
        self, plugin_id: str, version: str, target_dir: str,
    ) -> Optional[str]:
        """Download and extract a plugin package.

        Returns the path to the extracted plugin directory, or None on failure.
        Steps: fetch metadata -> download archive -> verify checksum -> extract.
        """
        meta = self.info(plugin_id, version)
        if not meta:
            logger.error("[MARKETPLACE] Unknown plugin %s v%s", plugin_id, version)
            return None

        download_url = meta.get("download_url", "")
        expected_sha256 = meta.get("sha256", "")

        if not download_url:
            logger.error("[MARKETPLACE] No download_url for %s v%s", plugin_id, version)
            return None

        if httpx is None:
            logger.error("[MARKETPLACE] httpx not available — cannot download")
            return None

        await self._ensure_client()

        # Download
        try:
            r = await self._http_client.get(download_url)
            r.raise_for_status()
        except Exception as e:
            logger.error("[MARKETPLACE] Download failed for %s: %s", plugin_id, e)
            return None

        # Save to temp file
        archive_path = os.path.join(
            self._cache_dir, f"{plugin_id}-{version}.zip",
        )
        os.makedirs(self._cache_dir, exist_ok=True)
        with open(archive_path, "wb") as f:
            f.write(r.content)

        # Verify checksum
        if expected_sha256:
            verifier = ManifestVerifier(mode="strict")
            if not verifier.verify_file_checksum(archive_path, expected_sha256):
                os.remove(archive_path)
                logger.error("[MARKETPLACE] Checksum verification failed for %s", plugin_id)
                return None

        # Extract
        extract_dir = os.path.join(target_dir, plugin_id)
        os.makedirs(extract_dir, exist_ok=True)
        try:
            with zipfile.ZipFile(archive_path, "r") as zf:
                for member in zf.infolist():
                    resolved = os.path.realpath(os.path.join(extract_dir, member.filename))
                    if not resolved.startswith(os.path.realpath(extract_dir)):
                        raise ValueError(f"Blocked zip slip traversal: {member.filename}")
                zf.extractall(extract_dir)
        except (zipfile.BadZipFile, ValueError) as e:
            os.remove(archive_path)
            logger.error("[MARKETPLACE] Extraction failed for %s: %s", plugin_id, e)
            return None

        os.remove(archive_path)
        logger.info("[MARKETPLACE] Downloaded %s v%s to %s", plugin_id, version, extract_dir)
        return extract_dir


plugin_marketplace = PluginMarketplace()
