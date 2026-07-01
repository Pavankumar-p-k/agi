from __future__ import annotations

import importlib
import importlib.util
import logging
import sys
from pathlib import Path
from typing import Any

from provider_sdk.manifest import ProviderManifest

logger = logging.getLogger(__name__)


class ProviderLoader:
    def load_adapter(self, manifest: ProviderManifest, base_dir: Path | None = None) -> Any | None:
        if manifest.adapter_type == "python":
            return self._load_python_adapter(manifest, base_dir)
        elif manifest.adapter_type == "http":
            return self._load_http_adapter(manifest)
        elif manifest.adapter_type == "mcp":
            return self._load_mcp_adapter(manifest)
        elif manifest.adapter_type == "cli":
            return self._load_cli_adapter(manifest)
        else:
            logger.warning("[ProviderLoader] Unsupported adapter_type: %s", manifest.adapter_type)
            return None

    def _load_python_adapter(self, manifest: ProviderManifest, base_dir: Path | None = None) -> Any | None:
        adapter_path = manifest.adapter
        if base_dir and not Path(adapter_path).is_absolute():
            adapter_path = str(base_dir / adapter_path)

        if not Path(adapter_path).exists():
            logger.warning("[ProviderLoader] Adapter file not found: %s", adapter_path)
            return None

        try:
            spec = importlib.util.spec_from_file_location(
                f"provider_{manifest.provider_id}", adapter_path,
            )
            if not spec or not spec.loader:
                logger.warning("[ProviderLoader] Cannot load spec for %s", adapter_path)
                return None
            mod = importlib.util.module_from_spec(spec)
            sys.modules[f"provider_{manifest.provider_id}"] = mod
            spec.loader.exec_module(mod)
            provider_class = getattr(mod, "Provider", None)
            if not provider_class:
                logger.warning("[ProviderLoader] No Provider class in %s", adapter_path)
                return None
            instance = provider_class()
            return instance
        except Exception as e:
            logger.exception("[ProviderLoader] Failed to load %s: %s", adapter_path, e)
            return None

    def _load_http_adapter(self, manifest: ProviderManifest) -> Any | None:
        try:
            from provider_sdk.adapters.http_adapter import HTTPProviderAdapter
            return HTTPProviderAdapter(manifest)
        except ImportError:
            logger.warning("[ProviderLoader] HTTP adapter support not installed")
            return None

    def _load_mcp_adapter(self, manifest: ProviderManifest) -> Any | None:
        try:
            from provider_sdk.adapters.mcp_adapter import MCPProviderAdapter
            return MCPProviderAdapter(manifest)
        except ImportError:
            logger.warning("[ProviderLoader] MCP adapter support not installed")
            return None

    def _load_cli_adapter(self, manifest: ProviderManifest) -> Any | None:
        try:
            from provider_sdk.adapters.cli_adapter import CLIProviderAdapter
            return CLIProviderAdapter(manifest)
        except ImportError:
            logger.warning("[ProviderLoader] CLI adapter support not installed")
            return None
