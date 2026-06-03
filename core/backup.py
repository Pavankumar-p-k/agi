from __future__ import annotations

import json
import logging
import os
import shutil
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

BACKUP_DIR = Path.home() / ".jarvis" / "backups"
SESSIONS_DIR = Path.home() / ".jarvis" / "sessions"
CONFIG_DIR = Path.home() / ".jarvis"


class BackupManager:
    """Backup and restore JARVIS state — matching OpenClaw's backup system."""

    def __init__(self):
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    async def create_backup(self, include_sessions: bool = True,
                            include_config: bool = True,
                            include_workspace: bool = False) -> dict:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_name = f"jarvis_backup_{timestamp}.tar.gz"
        archive_path = BACKUP_DIR / archive_name
        manifest = {
            "created": datetime.now().isoformat(),
            "version": "1.0.0",
            "includes": {
                "sessions": include_sessions,
                "config": include_config,
                "workspace": include_workspace,
            },
            "files": [],
        }

        try:
            with tarfile.open(archive_path, "w:gz") as tar:
                if include_config:
                    config_files = list(CONFIG_DIR.glob("*.json")) + list(CONFIG_DIR.glob("*.db"))
                    for f in config_files:
                        if f.name == "backups":
                            continue
                        tar.add(f, arcname=f"config/{f.name}")
                        manifest["files"].append(f"config/{f.name}")

                if include_sessions and SESSIONS_DIR.exists():
                    tar.add(SESSIONS_DIR, arcname="sessions")
                    manifest["files"].append(f"sessions/ ({len(list(SESSIONS_DIR.glob('*.json')))} files)")

                if include_workspace:
                    ws = Path.cwd()
                    tar.add(ws, arcname="workspace",
                            filter=lambda x: None if ".jarvis" in x.name or "__pycache__" in x.name else x)
                    manifest["files"].append("workspace/")

            manifest_path = BACKUP_DIR / f"{archive_name}.manifest.json"
            manifest_path.write_text(json.dumps(manifest, indent=2))

            size = archive_path.stat().st_size
            logger.info("[Backup] Created: %s (%.1f MB)", archive_name, size / 1024 / 1024)
            return {
                "success": True,
                "path": str(archive_path),
                "size_mb": round(size / 1024 / 1024, 2),
                "files": manifest["files"],
                "manifest": str(manifest_path),
            }
        except Exception as e:
            logger.exception("[Backup] Failed: %s", e)
            return {"success": False, "error": str(e)}

    async def restore_backup(self, archive_path: str | Path,
                             restore_sessions: bool = True,
                             restore_config: bool = True) -> dict:
        archive_path = Path(archive_path)
        if not archive_path.exists():
            return {"success": False, "error": f"Not found: {archive_path}"}

        restored = []
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                with tarfile.open(archive_path, "r:gz") as tar:
                    # Safe extract to prevent path traversal attacks
                    def _is_within_directory(directory: str, target: str) -> bool:
                        abs_directory = os.path.abspath(directory)
                        abs_target = os.path.abspath(target)
                        return os.path.commonpath([abs_directory]) == os.path.commonpath([abs_directory, abs_target])

                    for member in tar.getmembers():
                        member_path = os.path.join(tmpdir, member.name)
                        if not _is_within_directory(tmpdir, member_path):
                            raise Exception("Attempted Path Traversal in Tar File")

                    # Extract members individually to avoid tarfile.extractall warnings
                    for member in tar.getmembers():
                        tar.extract(member, tmpdir)

                tmp = Path(tmpdir)

                if restore_config:
                    config_dir = tmp / "config"
                    if config_dir.exists():
                        for f in config_dir.iterdir():
                            dest = CONFIG_DIR / f.name
                            shutil.copy2(f, dest)
                            restored.append(f"config/{f.name}")

                if restore_sessions:
                    sessions_dir = tmp / "sessions"
                    if sessions_dir.exists():
                        shutil.copytree(sessions_dir, SESSIONS_DIR, dirs_exist_ok=True)
                        restored.append("sessions/")

            logger.info("[Backup] Restored %d items from %s", len(restored), archive_path.name)
            return {"success": True, "restored": restored}
        except Exception as e:
            logger.exception("[Backup] Restore failed: %s", e)
            return {"success": False, "error": str(e)}

    def list_backups(self) -> list[dict]:
        backups = []
        for f in sorted(BACKUP_DIR.glob("*.tar.gz"), reverse=True):
            size = f.stat().st_size
            manifest_path = BACKUP_DIR / f"{f.name}.manifest.json"
            manifest = {}
            if manifest_path.exists():
                try:
                    manifest = json.loads(manifest_path.read_text())
                except Exception:
                    pass
            backups.append({
                "name": f.name,
                "size_mb": round(size / 1024 / 1024, 2),
                "created": manifest.get("created", "unknown"),
                "files": manifest.get("files", []),
            })
        return backups

    async def verify_backup(self, archive_path: str | Path) -> dict:
        archive_path = Path(archive_path)
        if not archive_path.exists():
            return {"valid": False, "error": "File not found"}
        try:
            with tarfile.open(archive_path, "r:gz") as tar:
                members = tar.getmembers()
                return {"valid": True, "file_count": len(members), "size_mb": round(archive_path.stat().st_size / 1024 / 1024, 2)}
        except Exception as e:
            return {"valid": False, "error": str(e)}


backup_manager = BackupManager()
