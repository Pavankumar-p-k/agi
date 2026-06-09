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
"""core/checkpoint_manager.py
Phase 3 (C3): Fine-Grained Checkpoints.
Per-step, per-page, per-file-write checkpoints with rollback.
"""
import json
import logging
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

CHECKPOINT_DIR = Path.home() / ".jarvis" / "checkpoints"


@dataclass
class SnapshottedFile:
    rel_path: str
    content_hash: str
    backup_path: str


@dataclass
class Checkpoint:
    project: str
    step_id: str
    description: str = ""
    files: list = field(default_factory=list)
    state_snapshot: dict = field(default_factory=dict)
    created_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()

    @property
    def dir(self) -> Path:
        return CHECKPOINT_DIR / self.project / f"cp_{self.step_id}"

    def save(self):
        cp_dir = self.dir
        cp_dir.mkdir(parents=True, exist_ok=True)

        meta = {
            "project": self.project,
            "step_id": self.step_id,
            "description": self.description,
            "files": self.files,
            "state_snapshot": self.state_snapshot,
            "created_at": self.created_at,
        }
        (cp_dir / "checkpoint.json").write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")

    @classmethod
    def load(cls, project: str, step_id: str) -> Optional["Checkpoint"]:
        path = CHECKPOINT_DIR / project / f"cp_{step_id}" / "checkpoint.json"
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                return cls(**data)
            except Exception as e:
                logger.warning(f"Failed to load checkpoint {project}/{step_id}: {e}")
        return None

    @classmethod
    def list_for_project(cls, project: str) -> list[str]:
        dir_path = CHECKPOINT_DIR / project
        if not dir_path.exists():
            return []
        cps = sorted(
            (d.name for d in dir_path.iterdir() if d.is_dir() and d.name.startswith("cp_")),
            key=lambda n: n
        )
        return [cp.replace("cp_", "", 1) for cp in cps]


class CheckpointManager:
    def __init__(self, max_checkpoints: int = 20):
        self.max_checkpoints = max_checkpoints

    def snapshot_files(self, workspace: Path, project: str, step_id: str) -> list[dict]:
        cp_dir = CHECKPOINT_DIR / project / f"cp_{step_id}" / "files"
        cp_dir.mkdir(parents=True, exist_ok=True)
        files = []
        for fp in sorted(workspace.rglob("*")):
            if not fp.is_file():
                continue
            rel = fp.relative_to(workspace)
            backup = cp_dir / rel
            backup.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(fp, backup)
            except Exception as e:
                logger.warning(f"Failed to snapshot {rel}: {e}")
                continue
            files.append({
                "rel_path": str(rel),
                "backup_path": str(backup),
            })
        return files

    def save_checkpoint(self, project: str, step_id: str, description: str = "",
                        workspace: Path | None = None, state: dict | None = None):
        cp = Checkpoint(
            project=project,
            step_id=step_id,
            description=description,
            state_snapshot=state or {},
        )
        cp.save()
        if workspace and workspace.exists():
            cp.files = self.snapshot_files(workspace, project, step_id)
            cp.save()
        self._enforce_limit(project)
        logger.info(f"[CHECKPOINT] Saved {project}/{step_id} ({len(cp.files)} files)")
        return cp

    def rollback(self, project: str, step_id: str, workspace: Path) -> bool:
        cp = Checkpoint.load(project, step_id)
        if not cp:
            logger.warning(f"[CHECKPOINT] No checkpoint found for {project}/{step_id}")
            return False
        files_dir = CHECKPOINT_DIR / project / f"cp_{step_id}" / "files"
        if not files_dir.exists():
            logger.warning(f"[CHECKPOINT] No files backup for {project}/{step_id}")
            return False
        for fmeta in cp.files:
            backup = Path(fmeta["backup_path"])
            if backup.exists():
                target = workspace / fmeta["rel_path"]
                target.parent.mkdir(parents=True, exist_ok=True)
                try:
                    shutil.copy2(backup, target)
                except Exception as e:
                    logger.warning(f"[CHECKPOINT] Failed to restore {fmeta['rel_path']}: {e}")
        logger.info(f"[CHECKPOINT] Rolled back {project} to step {step_id} ({len(cp.files)} files)")
        return True

    def restore_state(self, project: str, step_id: str, state) -> bool:
        cp = Checkpoint.load(project, step_id)
        if not cp or not cp.state_snapshot:
            return False
        for k, v in cp.state_snapshot.items():
            if hasattr(state, k):
                setattr(state, k, v)
        state.save()
        logger.info(f"[CHECKPOINT] State restored to {project}/{step_id}")
        return True

    def list_checkpoints(self, project: str) -> list[str]:
        return Checkpoint.list_for_project(project)

    def _enforce_limit(self, project: str):
        cps = self.list_checkpoints(project)
        if len(cps) > self.max_checkpoints:
            excess = sorted(cps)[:len(cps) - self.max_checkpoints]
            for step_id in excess:
                path = CHECKPOINT_DIR / project / f"cp_{step_id}"
                if path.exists():
                    shutil.rmtree(path)
                    logger.info(f"[CHECKPOINT] Pruned old checkpoint {project}/{step_id}")


checkpoint_manager = CheckpointManager()
