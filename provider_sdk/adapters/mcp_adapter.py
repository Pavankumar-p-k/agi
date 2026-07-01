from __future__ import annotations

import logging
from typing import Any

from provider_sdk.manifest import ProviderManifest

logger = logging.getLogger(__name__)


class MCPProviderAdapter:
    def __init__(self, manifest: ProviderManifest) -> None:
        self.manifest = manifest
        self.provider_id = manifest.provider_id
        self.name = manifest.name
        self.version = manifest.version
        self.priority = manifest.priority
        self.installed = True
        self._enabled = True

    def capabilities(self) -> Any:
        from core.providers.base import ProviderCapabilities
        return ProviderCapabilities(
            capability_names=self.manifest.capabilities[:],
            features=self.manifest.features[:],
            languages=self.manifest.languages[:],
        )

    async def health(self) -> Any:
        from core.providers.base import ProviderHealth, ProviderHealthStatus
        return ProviderHealth(status=ProviderHealthStatus.UNKNOWN)

    @property
    def enabled(self) -> bool:
        return self._enabled and self.installed

    def enable(self) -> None:
        self._enabled = True

    def disable(self) -> None:
        self._enabled = False
