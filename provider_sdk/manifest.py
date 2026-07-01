from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

MANIFEST_YAML_SUPPORT = False
try:
    import yaml
    MANIFEST_YAML_SUPPORT = True
except ImportError:
    pass


@dataclass
class ProviderManifest:
    provider_id: str = ""
    name: str = ""
    version: str = "1.0.0"
    description: str = ""
    author: str = ""
    capabilities: list[str] = field(default_factory=list)
    features: list[str] = field(default_factory=list)
    languages: list[str] = field(default_factory=list)
    adapter: str = ""
    adapter_type: str = "python"
    priority: int = 100
    health_endpoint: str = ""
    settings_schema: dict[str, Any] = field(default_factory=dict)
    dependencies: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    homepage: str = ""
    license: str = ""
    min_sdk_version: str = "1.0.0"

    @classmethod
    def from_dict(cls, data: dict) -> ProviderManifest:
        return cls(
            provider_id=data.get("provider_id", data.get("id", "")),
            name=data.get("name", ""),
            version=data.get("version", "1.0.0"),
            description=data.get("description", ""),
            author=data.get("author", ""),
            capabilities=data.get("capabilities", []),
            features=data.get("features", []),
            languages=data.get("languages", []),
            adapter=data.get("adapter", ""),
            adapter_type=data.get("adapter_type", "python"),
            priority=data.get("priority", 100),
            health_endpoint=data.get("health_endpoint", ""),
            settings_schema=data.get("settings_schema", {}),
            dependencies=data.get("dependencies", []),
            tags=data.get("tags", []),
            homepage=data.get("homepage", ""),
            license=data.get("license", ""),
            min_sdk_version=data.get("min_sdk_version", "1.0.0"),
        )

    def to_dict(self) -> dict:
        return {
            "provider_id": self.provider_id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "capabilities": self.capabilities,
            "features": self.features,
            "languages": self.languages,
            "adapter": self.adapter,
            "adapter_type": self.adapter_type,
            "priority": self.priority,
            "health_endpoint": self.health_endpoint,
            "settings_schema": self.settings_schema,
            "dependencies": self.dependencies,
            "tags": self.tags,
            "homepage": self.homepage,
            "license": self.license,
            "min_sdk_version": self.min_sdk_version,
        }


REQUIRED_FIELDS = ["provider_id", "name", "capabilities", "adapter"]
RECOMMENDED_FIELDS = ["version", "description", "author", "adapter_type"]


class ManifestError(Exception):
    pass


def validate_manifest(manifest: ProviderManifest) -> list[str]:
    errors: list[str] = []
    if not manifest.provider_id:
        errors.append("provider_id is required")
    if not manifest.name:
        errors.append("name is required")
    if not manifest.capabilities:
        errors.append("At least one capability is required")
    if not manifest.adapter:
        errors.append("adapter path is required")
    if manifest.adapter_type not in ("python", "http", "ws", "mcp", "cli", "grpc"):
        errors.append(f"Unknown adapter_type: {manifest.adapter_type}")
    return errors


def load_manifest(path: str | Path) -> ProviderManifest:
    path = Path(path)
    if not path.exists():
        raise ManifestError(f"Manifest not found: {path}")
    raw = path.read_text(encoding="utf-8")
    if path.suffix in (".yaml", ".yml"):
        if not MANIFEST_YAML_SUPPORT:
            raise ManifestError("PyYAML is required to load .yaml manifests")
        data = yaml.safe_load(raw)
    elif path.suffix == ".json":
        data = json.loads(raw)
    else:
        raise ManifestError(f"Unsupported manifest format: {path.suffix}")
    if not isinstance(data, dict):
        raise ManifestError("Manifest must be a JSON/YAML object")
    manifest = ProviderManifest.from_dict(data)
    errors = validate_manifest(manifest)
    if errors:
        raise ManifestError(f"Manifest validation failed: {'; '.join(errors)}")
    return manifest
