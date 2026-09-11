from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import os
import shutil


class CheckpointManager:
    def __init__(self, root: str | Path | None = None):
        self.root = Path(root or Path.home() / ".jarvis" / "checkpoints")

    def _path(self, project: str, step: str) -> Path:
        return self.root / str(project) / f"cp_{step}"

    def save_checkpoint(self, project: str, step: str, description: str = "", workspace: str | Path | None = None, state: dict[str, Any] | None = None) -> dict[str, Any]:
        target = self._path(project, step)
        target.mkdir(parents=True, exist_ok=True)
        payload = {"project": project, "step": step, "description": description, "state": state or {}, "workspace": str(workspace) if workspace else ""}
        temporary = target / "checkpoint.json.tmp"
        temporary.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        os.replace(temporary, target / "checkpoint.json")
        if workspace:
            self.snapshot_files(project, step, Path(workspace))
        return payload

    def list_checkpoints(self, project: str) -> list[str]:
        directory = self.root / str(project)
        if not directory.exists():
            return []
        return sorted(path.name.removeprefix("cp_") for path in directory.iterdir() if path.is_dir() and (path / "checkpoint.json").exists())

    def snapshot_files(self, project: str, step: str, workspace: Path) -> None:
        destination = self._path(project, step) / "workspace"
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(workspace, destination)

    def rollback(self, project: str, step: str, workspace: Path) -> bool:
        snapshot = self._path(project, step) / "workspace"
        if not snapshot.exists():
            return False
        if workspace.exists():
            shutil.rmtree(workspace)
        shutil.copytree(snapshot, workspace)
        return True

    def restore_state(self, project: str, step: str) -> dict[str, Any] | None:
        path = self._path(project, step) / "checkpoint.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8")).get("state", {})


checkpoint_manager = CheckpointManager()
