"""Capability Discovery Engine for JARVIS.

Maintains the live catalog of what JARVIS can currently do by inspecting:
1. Active specialist modules (Desktop AI, Coding AI, etc.)
2. Authoritative ToolRegistry tools
3. Installed local CLI binaries and runtime environments in PATH
4. Plugins and extensions
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
from typing import Any, Callable, Optional

from core.specialist import SpecialistModule
from tools.base_tool import (
    CapabilityDefinition,
    CapabilityHealth,
    CapabilityStatus,
    CapabilityType,
    ReliabilityMetrics,
    RiskTier,
    VerificationSpec,
)
from tools.registry import CapabilityRegistry, _ensure_registry

logger = logging.getLogger(__name__)

# Common developer and productivity tools with their capability descriptions
KNOWN_CLI_PROFILES: dict[str, dict[str, Any]] = {
    "git": {
        "name": "cli.git",
        "description": "Git distributed version control system for staging, committing, and branching",
        "owner_module": "Coding AI",
        "requirements": ["terminal", "filesystem"],
        "version_flag": "--version",
        "risk": RiskTier.MEDIUM,
    },
    "gh": {
        "name": "cli.gh",
        "description": "GitHub official CLI for pull requests, issues, releases, and repository workflows",
        "owner_module": "Coding AI",
        "requirements": ["terminal", "network"],
        "version_flag": "--version",
        "risk": RiskTier.MEDIUM,
    },
    "node": {
        "name": "cli.node",
        "description": "Node.js JavaScript runtime for server-side code execution",
        "owner_module": "Coding AI",
        "requirements": ["terminal"],
        "version_flag": "-v",
        "risk": RiskTier.MEDIUM,
    },
    "npm": {
        "name": "cli.npm",
        "description": "Node Package Manager for installing, building, and running JS/TS packages",
        "owner_module": "Coding AI",
        "requirements": ["terminal", "network", "filesystem"],
        "version_flag": "-v",
        "risk": RiskTier.MEDIUM,
    },
    "python": {
        "name": "cli.python",
        "description": "Python interpreter runtime for script execution and testing",
        "owner_module": "Coding AI",
        "requirements": ["terminal"],
        "version_flag": "--version",
        "risk": RiskTier.MEDIUM,
    },
    "pip": {
        "name": "cli.pip",
        "description": "Python package installer for managing dependencies",
        "owner_module": "Coding AI",
        "requirements": ["terminal", "network"],
        "version_flag": "--version",
        "risk": RiskTier.MEDIUM,
    },
    "docker": {
        "name": "cli.docker",
        "description": "Docker container runtime and compose engine",
        "owner_module": "Deployment AI",
        "requirements": ["terminal", "daemon"],
        "version_flag": "--version",
        "risk": RiskTier.HIGH,
    },
    "vercel": {
        "name": "cli.vercel",
        "description": "Vercel deployment CLI for web application deployments",
        "owner_module": "Deployment AI",
        "requirements": ["terminal", "network"],
        "version_flag": "--version",
        "risk": RiskTier.MEDIUM,
    },
    "ffmpeg": {
        "name": "cli.ffmpeg",
        "description": "FFmpeg audio/video processing and transcoding engine",
        "owner_module": "Media AI",
        "requirements": ["terminal", "filesystem"],
        "version_flag": "-version",
        "risk": RiskTier.LOW,
    },
    "code": {
        "name": "cli.vscode",
        "description": "Visual Studio Code editor CLI for opening workspaces and inspecting files",
        "owner_module": "Desktop AI",
        "requirements": ["display"],
        "version_flag": "--version",
        "risk": RiskTier.LOW,
    },
}


class CapabilityDiscoveryService:
    """Discovers and synchronizes all available JARVIS capabilities."""

    def __init__(self, registry: Optional[CapabilityRegistry] = None) -> None:
        self.registry = registry if registry is not None else _ensure_registry()

    def discover_specialist(self, specialist: SpecialistModule) -> list[CapabilityDefinition]:
        """Discover and register capabilities from a specialist module."""
        discovered: list[CapabilityDefinition] = []
        health_info = specialist.health_check()
        is_healthy = health_info.get("status") in (CapabilityHealth.HEALTHY.value, "healthy")
        specialist_health = CapabilityHealth.HEALTHY if is_healthy else CapabilityHealth.DEGRADED

        for cap in specialist.get_capabilities():
            # Align capability health with specialist status
            if cap.health == CapabilityHealth.UNKNOWN:
                cap.health = specialist_health
            self.registry.register_capability(cap)
            discovered.append(cap)
            logger.info("Discovered specialist capability: %s from %s", cap.name, specialist.name)

        return discovered

    def discover_cli_tools(
        self,
        cli_profiles: Optional[dict[str, dict[str, Any]]] = None,
    ) -> list[CapabilityDefinition]:
        """Probe PATH for installed command-line tools and register their capabilities."""
        profiles = cli_profiles or KNOWN_CLI_PROFILES
        discovered: list[CapabilityDefinition] = []

        for binary, profile in profiles.items():
            path_str = shutil.which(binary)
            name = profile["name"]
            owner = profile.get("owner_module", "System AI")
            desc = profile.get("description", f"CLI tool for {binary}")
            reqs = profile.get("requirements", ["terminal"])
            risk = profile.get("risk", RiskTier.MEDIUM)

            if path_str:
                version = "installed"
                try:
                    flag = profile.get("version_flag", "--version")
                    out = subprocess.check_output([path_str, flag], stderr=subprocess.STDOUT, timeout=2.0)
                    line = out.decode("utf-8", errors="ignore").splitlines()[0].strip()
                    version = line[:50]
                except Exception:
                    pass

                cap = CapabilityDefinition(
                    name=name,
                    type=CapabilityType.CLI,
                    owner_module=owner,
                    version=version,
                    source="local_cli",
                    description=desc,
                    inputs={"command_args": {"type": "array", "description": "Arguments to pass to binary"}},
                    outputs={"stdout": {"type": "string"}, "exit_code": {"type": "integer"}},
                    requirements=reqs,
                    dependencies=[binary],
                    risk=risk,
                    status=CapabilityStatus.AVAILABLE,
                    health=CapabilityHealth.HEALTHY,
                    verification=VerificationSpec(method="exit_code_zero"),
                    metadata={"binary_path": path_str, "binary_name": binary},
                )
            else:
                # Registered as missing / unhealthy for gap detection
                cap = CapabilityDefinition(
                    name=name,
                    type=CapabilityType.CLI,
                    owner_module=owner,
                    version="not_installed",
                    source="local_cli",
                    description=f"{desc} (NOT FOUND in PATH)",
                    requirements=reqs,
                    dependencies=[binary],
                    risk=risk,
                    status=CapabilityStatus.AVAILABLE,
                    health=CapabilityHealth.UNHEALTHY,
                    metadata={"missing": True, "binary_name": binary},
                )

            self.registry.register_capability(cap)
            discovered.append(cap)

        return discovered

    def discover_all(
        self,
        specialists: Optional[list[SpecialistModule]] = None,
    ) -> dict[str, Any]:
        """Run complete discovery pass across specialists and local environment."""
        specialist_caps: list[CapabilityDefinition] = []
        if specialists:
            for spec in specialists:
                specialist_caps.extend(self.discover_specialist(spec))

        cli_caps = self.discover_cli_tools()

        all_caps = self.registry.list_capabilities()
        healthy_count = len([c for c in all_caps if c.health == CapabilityHealth.HEALTHY])
        degraded_count = len([c for c in all_caps if c.health == CapabilityHealth.DEGRADED])
        unhealthy_count = len([c for c in all_caps if c.health == CapabilityHealth.UNHEALTHY])

        return {
            "total_capabilities": len(all_caps),
            "healthy": healthy_count,
            "degraded": degraded_count,
            "unhealthy": unhealthy_count,
            "specialist_capabilities_count": len(specialist_caps),
            "cli_capabilities_count": len(cli_caps),
        }
