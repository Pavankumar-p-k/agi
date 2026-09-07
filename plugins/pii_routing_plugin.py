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

from __future__ import annotations

import logging
from typing import Any

from core.plugins import PrivacyPlugin, PluginManifest

logger = logging.getLogger(__name__)


class Plugin(PrivacyPlugin):
    manifest: PluginManifest

    def __init__(self, manifest: PluginManifest):
        super().__init__(manifest)
        self._classifier = None
        self._last_override = None

    async def on_load(self, app_state: dict | None = None) -> None:
        await super().on_load(app_state)
        try:
            from core.privacy_classifier import privacy_classifier
            self._classifier = privacy_classifier
            logger.info("[PIIRoutingPlugin] PrivacyClassifier acquired")
        except Exception as e:
            logger.warning("[PIIRoutingPlugin] Could not acquire classifier: %s", e)

    async def on_unload(self) -> None:
        self._classifier = None
        self._last_override = None
        await super().on_unload()

    async def on_routing_decision(self, tier: str, text: str, metadata: dict) -> str | None:
        if not self._classifier or not text:
            return None
        try:
            result = self._classifier.classify(text)
            pii_tier = result.value
            if pii_tier == "LOCAL" and tier != "LOCAL":
                logger.warning("[PIIRoutingPlugin] Override: %s -> LOCAL (PII detected)", tier)
                self._last_override = {"from": tier, "to": "LOCAL"}
                return "LOCAL"
            if pii_tier != tier:
                logger.info("[PIIRoutingPlugin] Adjusting tier: %s -> %s", tier, pii_tier)
                self._last_override = {"from": tier, "to": pii_tier}
                return pii_tier
        except Exception as e:
            logger.warning("[PIIRoutingPlugin] Classification failed: %s", e)
        return None

    async def on_redact(self, text: str, context: dict | None = None) -> str | None:
        if not self._classifier or not text:
            return None
        try:
            tier = (context or {}).get("tier", "HYBRID")
            from core.privacy_classifier import PrivacyTier
            sanitized = self._classifier.sanitize(text, PrivacyTier(tier))
            if sanitized != text:
                logger.info("[PIIRoutingPlugin] Redacted %d chars of PII", len(text) - len(sanitized))
            return sanitized
        except Exception as e:
            logger.warning("[PIIRoutingPlugin] Redaction failed: %s", e)
            return None

    async def health_check(self) -> dict:
        base = await super().health_check()
        base["classifier_ready"] = self._classifier is not None
        base["last_override"] = self._last_override
        return base
