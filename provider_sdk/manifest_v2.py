from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from provider_sdk.manifest import ProviderManifest as V1Manifest

MANIFEST_YAML_SUPPORT = False
try:
    import yaml
    MANIFEST_YAML_SUPPORT = True
except ImportError:
    pass

PIPELINE_VERSION = 2

REQUIRED_V2 = {
    "id", "publisher", "version",
    "sdk_version", "api_version", "minimum_jarvis",
    "transport", "entrypoint",
    "permissions", "platforms",
}

VALID_TRANSPORTS = frozenset({"python", "mcp", "http", "grpc", "cli"})
VALID_PLATFORMS = frozenset({"windows", "linux", "darwin"})


class ManifestError(Exception):
    pass


@dataclass(frozen=True)
class ProviderDescriptor:
    id: str
    publisher: str
    version: str
    sdk_version: int
    api_version: int
    transport: str
    entrypoint: str
    permissions: frozenset[str]
    declared_capabilities: tuple[dict[str, Any], ...]
    platforms: tuple[str, ...]
    fingerprint: str
    manifest_path: str
    metadata: dict[str, Any]
    instance: object | None = None


@dataclass(frozen=True)
class StageResult:
    success: bool
    next_state: str
    diagnostics: tuple[str, ...]
    metadata: dict[str, Any]


def detect_manifest_version(raw: dict) -> int:
    if "sdk_version" in raw:
        return int(raw["sdk_version"])
    return 1


def _compute_fingerprint(manifest_bytes: bytes, adapter_bytes: bytes) -> str:
    h = hashlib.sha256()
    h.update(manifest_bytes)
    h.update(adapter_bytes)
    h.update(str(PIPELINE_VERSION).encode())
    return h.hexdigest()


def load_raw_manifest(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    if not path.exists():
        raise ManifestError(f"Manifest not found: {path}")
    raw = path.read_bytes()
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
    return data


def validate_v2_schema(data: dict) -> list[str]:
    errors: list[str] = []
    for field in REQUIRED_V2:
        if field not in data:
            errors.append(f"Missing required field: {field}")
    if "id" in data:
        import re
        if not re.match(r"^[a-z][a-z0-9-]*$", data["id"]):
            errors.append(f"Invalid id '{data['id']}': lowercase alphanumeric + hyphens only")
    if "sdk_version" in data:
        try:
            sv = int(data["sdk_version"])
            if sv < 1:
                errors.append("sdk_version must be >= 1")
        except (ValueError, TypeError):
            errors.append("sdk_version must be an integer")
    if "api_version" in data:
        try:
            av = int(data["api_version"])
            if av < 1:
                errors.append("api_version must be >= 1")
        except (ValueError, TypeError):
            errors.append("api_version must be an integer")
    if "transport" in data and data["transport"] not in VALID_TRANSPORTS:
        errors.append(f"Invalid transport '{data['transport']}': must be one of {sorted(VALID_TRANSPORTS)}")
    if "platforms" in data:
        if not isinstance(data["platforms"], list):
            errors.append("platforms must be a list")
        else:
            for p in data["platforms"]:
                if p not in VALID_PLATFORMS:
                    errors.append(f"Invalid platform '{p}'")
    if "permissions" in data:
        if not isinstance(data["permissions"], list):
            errors.append("permissions must be a list")
        else:
            from provider_sdk.permissions import validate_permissions
            errors.extend(validate_permissions(data["permissions"]))
    return errors


def v1_to_v2(data: dict, manifest_path: str) -> dict:
    return {
        "id": data.get("provider_id", data.get("name", Path(manifest_path).stem)),
        "publisher": "jarvis-core",
        "version": data.get("version", "1.0.0"),
        "sdk_version": 1,
        "api_version": 1,
        "minimum_jarvis": "1.0.0",
        "transport": "python",
        "entrypoint": data.get("adapter", ""),
        "permissions": [],
        "platforms": ["windows", "linux", "darwin"],
        "capabilities": [{"id": c, "version": 1} for c in data.get("capabilities", [])],
        "name": data.get("name", ""),
        "description": data.get("description", ""),
        "author": data.get("author", ""),
        "homepage": "",
        "license": "",
        "tags": [],
        "features": data.get("features", []),
        "priority": data.get("priority", 100),
        "signature": {},
        "sandbox": {},
        "dependencies": data.get("dependencies", []),
    }


def build_descriptor(data: dict, manifest_path: str) -> ProviderDescriptor:
    manifest_path = str(Path(manifest_path).resolve())
    manifest_bytes = Path(manifest_path).read_bytes()
    entrypoint = data.get("entrypoint", "")
    adapter_path = entrypoint
    if not Path(adapter_path).is_absolute():
        base = Path(manifest_path).parent
        adapter_path = str(base / entrypoint)
    try:
        adapter_bytes = Path(adapter_path).read_bytes()
    except Exception:
        adapter_bytes = b""
    fingerprint = _compute_fingerprint(manifest_bytes, adapter_bytes)
    caps_raw = data.get("capabilities", [])
    caps: list[dict[str, Any]] = []
    for c in caps_raw:
        if isinstance(c, str):
            caps.append({"id": c, "version": 1})
        elif isinstance(c, dict):
            caps.append({"id": c.get("id", ""), "version": c.get("version", 1)})
    perms = data.get("permissions", [])
    if isinstance(perms, list):
        perms_set = frozenset(p for p in perms if isinstance(p, str))
    else:
        perms_set = frozenset()
    platforms = tuple(data.get("platforms", ["windows", "linux", "darwin"]))
    if isinstance(platforms, list):
        platforms = tuple(platforms)
    metadata = {k: v for k, v in data.items() if k not in {
        "id", "publisher", "version", "sdk_version", "api_version",
        "minimum_jarvis", "maximum_jarvis", "transport", "entrypoint",
        "permissions", "capabilities", "platforms",
    }}
    return ProviderDescriptor(
        id=data["id"],
        publisher=data.get("publisher", "jarvis-core"),
        version=data["version"],
        sdk_version=int(data["sdk_version"]),
        api_version=int(data.get("api_version", 1)),
        transport=data.get("transport", "python"),
        entrypoint=entrypoint,
        permissions=perms_set,
        declared_capabilities=tuple(caps),
        platforms=platforms,
        fingerprint=fingerprint,
        manifest_path=manifest_path,
        metadata=metadata,
        instance=None,
    )


def parse_and_validate(path: str | Path) -> ProviderDescriptor:
    path = Path(path)
    raw = load_raw_manifest(str(path))
    version = detect_manifest_version(raw)
    if version == 1:
        from provider_sdk.manifest import load_manifest
        v1 = load_manifest(str(path))
        data = v1_to_v2(v1.to_dict(), str(path))
    else:
        errors = validate_v2_schema(raw)
        if errors:
            raise ManifestError(f"Manifest v2 validation failed: {'; '.join(errors)}")
        data = raw
    return build_descriptor(data, str(path))
