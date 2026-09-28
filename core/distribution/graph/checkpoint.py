"""GraphCheckpointer — durable JSON snapshots of distributed graphs."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

DEFAULT_CHECKPOINT_DIR = "data/checkpoints"


class GraphCheckpointer:
    """Writes/reads ``<graph_id>.json`` snapshots under a directory."""

    def __init__(self, directory: Any = None) -> None:
        self.directory = Path(directory or DEFAULT_CHECKPOINT_DIR)

    def _path(self, graph_id: str) -> Path:
        return self.directory / f"{graph_id}.json"

    def _ensure_dir(self) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)

    async def save(self, graph: Any) -> str:
        """Persist *graph*'s snapshot. Returns the written path."""
        self._ensure_dir()
        snapshot = graph.to_snapshot() if hasattr(graph, "to_snapshot") else dict(graph)
        path = self._path(snapshot.get("graph_id", getattr(graph, "id", "graph")))
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(snapshot, handle, indent=2, default=str)
        return str(path)

    async def load(self, graph_id: str) -> Optional[dict]:
        path = self._path(graph_id)
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("failed to load checkpoint %s: %s", path, exc)
            return None

    async def list_checkpoints(self) -> list:
        if not self.directory.exists():
            return []
        return sorted(p.stem for p in self.directory.glob("*.json"))

    async def delete(self, graph_id: str) -> bool:
        path = self._path(graph_id)
        if not path.exists():
            return False
        try:
            os.remove(path)
            return True
        except OSError as exc:  # pragma: no cover - filesystem race
            logger.warning("failed to delete checkpoint %s: %s", path, exc)
            return False


__all__ = ["GraphCheckpointer", "DEFAULT_CHECKPOINT_DIR"]
