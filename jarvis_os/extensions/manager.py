"""Extensions Manager - Phase 7 Mythos Omega."""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class Extension:
    def __init__(self, name: str, path: str, enabled: bool = True):
        self.name = name
        self.path = path
        self.enabled = enabled
        self.commands: List[str] = []
        self.metadata: Dict[str, Any] = {}


class ExtensionsManager:
    """Manages JARVIS OS extensions."""

    def __init__(self, config_dir: str):
        self.config_dir = config_dir
        self.extensions: Dict[str, Extension] = {}
        self._load_extensions()

    def _load_extensions(self):
        """Load extensions from config directory."""
        ext_file = os.path.join(self.config_dir, "extensions.json")
        if os.path.exists(ext_file):
            try:
                with open(ext_file, "r") as f:
                    data = json.load(f)
                    for name, info in data.get("extensions", {}).items():
                        ext = Extension(
                            name=name,
                            path=info.get("path", ""),
                            enabled=info.get("enabled", True),
                        )
                        ext.commands = info.get("commands", [])
                        ext.metadata = info.get("metadata", {})
                        self.extensions[name] = ext
            except Exception as e:
                logger.error("Failed to load extensions: %s", e)

    def _save_extensions(self):
        """Save extensions to config file."""
        ext_file = os.path.join(self.config_dir, "extensions.json")
        data = {"extensions": {}}
        for name, ext in self.extensions.items():
            data["extensions"][name] = {
                "path": ext.path,
                "enabled": ext.enabled,
                "commands": ext.commands,
                "metadata": ext.metadata,
            }
        try:
            with open(ext_file, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error("Failed to save extensions: %s", e)

    def list_extensions(self) -> List[Dict[str, Any]]:
        """List all extensions."""
        return [
            {
                "name": ext.name,
                "path": ext.path,
                "enabled": ext.enabled,
                "commands": ext.commands,
                "metadata": ext.metadata,
            }
            for ext in self.extensions.values()
        ]

    def get_extension_info(self, name: str) -> Dict[str, Any]:
        """Get info about a specific extension."""
        if name not in self.extensions:
            return {"error": f"Extension '{name}' not found"}
        ext = self.extensions[name]
        return {
            "name": ext.name,
            "path": ext.path,
            "enabled": ext.enabled,
            "commands": ext.commands,
            "metadata": ext.metadata,
        }

    def enable_extension(self, name: str) -> Dict[str, Any]:
        """Enable an extension."""
        if name not in self.extensions:
            return {"ok": False, "error": f"Extension '{name}' not found"}
        self.extensions[name].enabled = True
        self._save_extensions()
        return {"ok": True, "message": f"Extension '{name}' enabled"}

    def disable_extension(self, name: str) -> Dict[str, Any]:
        """Disable an extension."""
        if name not in self.extensions:
            return {"ok": False, "error": f"Extension '{name}' not found"}
        self.extensions[name].enabled = False
        self._save_extensions()
        return {"ok": True, "message": f"Extension '{name}' disabled"}

    def install_extension(self, path_or_url: str) -> Dict[str, Any]:
        """Install an extension from path or URL."""
        # For now, just register it
        name = os.path.basename(path_or_url).replace(".py", "")
        self.extensions[name] = Extension(
            name=name,
            path=path_or_url,
            enabled=True,
        )
        self._save_extensions()
        return {"ok": True, "message": f"Extension '{name}' installed", "name": name}

    def uninstall_extension(self, name: str) -> Dict[str, Any]:
        """Uninstall an extension."""
        if name not in self.extensions:
            return {"ok": False, "error": f"Extension '{name}' not found"}
        del self.extensions[name]
        self._save_extensions()
        return {"ok": True, "message": f"Extension '{name}' uninstalled"}

    def list_extension_commands(self) -> List[str]:
        """List all commands from enabled extensions."""
        commands = []
        for ext in self.extensions.values():
            if ext.enabled:
                commands.extend(ext.commands)
        return commands
