from __future__ import annotations

import logging
import subprocess
import sys
from typing import Optional

from .errors import PluginDependencyError

logger = logging.getLogger("jarvis.plugins.dependencies")


class DependencyResolver:
    """Formal dependency resolution with conflict detection and rollback.

    Replaces the inline install_deps in PluginLoader with a proper
    resolver that detects version conflicts and supports transactional
    install/uninstall with rollback on failure.
    """

    def __init__(self):
        self._installed_in_session: list[str] = []
        self._failed_in_session: list[str] = []

    def resolve(self, requires: list[str]) -> list[str]:
        """Parse a list of requirement strings and return packages to install.

        Returns only packages that are NOT already importable.
        Detects version conflicts with already-installed packages.
        Raises PluginDependencyError on conflict or parse failure.
        """
        missing: list[str] = []
        for req in requires:
            pkg_name = _parse_package_name(req)
            if pkg_name and not _is_installed(pkg_name):
                if _conflicts_with_existing(req):
                    raise PluginDependencyError(
                        dependency=req,
                        message=f"Version conflict: '{req}' conflicts with already-installed package",
                    )
                missing.append(req)
        return missing

    def install(self, requires: list[str]) -> bool:
        """Install requirements transactionally with rollback.

        Returns True if all installs succeeded.
        On failure, rolls back all packages installed in this session.
        """
        missing = self.resolve(requires)
        if not missing:
            return True

        self._failed_in_session = []
        self._installed_in_session = []

        logger.info("Installing plugin dependencies: %s", missing)
        for req in missing:
            try:
                subprocess.check_call(
                    [sys.executable, "-m", "pip", "install", "--quiet", req],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    timeout=120,
                )
                self._installed_in_session.append(req)
                logger.debug("Installed: %s", req)
            except subprocess.TimeoutExpired:
                logger.error("Timeout installing %s", req)
                self._failed_in_session.append(req)
                self._rollback()
                return False
            except subprocess.CalledProcessError as exc:
                logger.error("pip install failed for %s: %s", req, exc.stderr)
                self._failed_in_session.append(req)
                self._rollback()
                return False

        return True

    def uninstall(self, packages: list[str]) -> None:
        """Uninstall packages (used for rollback)."""
        if not packages:
            return
        try:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "uninstall", "--yes", "--quiet", *packages],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                timeout=60,
            )
            logger.info("Rolled back: %s", packages)
        except Exception as exc:
            logger.warning("Rollback failed for %s: %s", packages, exc)

    def _rollback(self) -> None:
        """Roll back all packages installed this session."""
        if self._installed_in_session:
            logger.warning("Rolling back %d installed packages", len(self._installed_in_session))
            self.uninstall(self._installed_in_session)
        self._installed_in_session = []
        self._failed_in_session = []

    def clear_session(self) -> None:
        """Clear session tracking (call after successful install)."""
        self._installed_in_session = []
        self._failed_in_session = []


def _parse_package_name(req: str) -> str:
    """Extract the base package name from a requirement string.

    Handles: ``package``, ``package>=1.0``, ``package==1.0``,
    ``package[extra]>=1.0``, ``package<=1.0``.
    """
    name = req.split(">=")[0].split("<=")[0].split("==")[0].split("!=")[0].split("~=")[0].strip()
    name = name.split("[")[0].strip()
    return name


def _is_installed(package_name: str) -> bool:
    """Check if a package can be imported."""
    name = _parse_package_name(package_name)
    try:
        importlib.import_module(name.replace("-", "_"))
        return True
    except ImportError:
        return False


def _conflicts_with_existing(req: str) -> bool:
    """Check if a requirement conflicts with an already-installed package.

    Basic check: if the package is installed and a version specifier
    is given, check if the installed version matches.
    """
    import importlib.metadata
    pkg_name = _parse_package_name(req)
    try:
        installed_version = importlib.metadata.version(pkg_name)
    except importlib.metadata.PackageNotFoundError:
        return False

    # Check for version specifiers
    for sep in (">=", "<=", "==", "!=", "~=", ">" , "<"):
        if sep in req:
            parts = req.split(sep, 1)
            if len(parts) == 2:
                spec_version = parts[1].strip()
                # Simple conflict detection: exact version mismatch
                if sep == "==" and installed_version != spec_version:
                    return True
    return False


import importlib


dependency_resolver = DependencyResolver()
