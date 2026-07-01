from __future__ import annotations

import logging
from typing import Any

from provider_sdk.manifest import ProviderManifest

logger = logging.getLogger(__name__)


class HTTPProviderAdapter:
    def __init__(self, manifest: ProviderManifest) -> None:
        self.manifest = manifest
        self.provider_id = manifest.provider_id
        self.name = manifest.name
        self.version = manifest.version
        self.priority = manifest.priority
        self.installed = True
        self._enabled = True
        self._base_url = manifest.health_endpoint or f"http://localhost:{_infer_port(manifest.provider_id)}"

    def capabilities(self) -> Any:
        from core.providers.base import ProviderCapabilities
        return ProviderCapabilities(
            capability_names=self.manifest.capabilities[:],
            features=self.manifest.features[:],
            languages=self.manifest.languages[:],
        )

    async def health(self) -> Any:
        from core.providers.base import ProviderHealth, ProviderHealthStatus
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                r = await client.get(f"{self._base_url}/health", timeout=5)
                if r.status_code == 200:
                    return ProviderHealth(status=ProviderHealthStatus.HEALTHY)
        except Exception:
            pass
        return ProviderHealth(status=ProviderHealthStatus.DOWN)

    @property
    def enabled(self) -> bool:
        return self._enabled and self.installed

    def enable(self) -> None:
        self._enabled = True

    def disable(self) -> None:
        self._enabled = False


def _infer_port(provider_id: str) -> int:
    port_map = {
        "search": 8100,
        "codex": 8200,
        "claude": 8300,
        "workspace": 8400,
        "github": 8500,
        "email": 8600,
    }
    return port_map.get(provider_id, 9000)
