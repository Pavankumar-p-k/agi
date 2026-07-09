"""Immutable graph checkpointing for distributed DAG recovery.

Checkpoints are JSON-serialised snapshots stored to disk or an external store.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from core.distribution.graph.models import DistributedGraph, GraphNode

logger = logging.getLogger(__name__)

_DEFAULT_DIR = Path.home() / ".jarvis" / "graph_checkpoints"


class GraphCheckpointer:
    """Saves and loads immutable graph snapshots."""

    def __init__(self, directory: str | Path | None = None) -> None:
        self._dir = Path(directory) if directory else _DEFAULT_DIR
        self._dir.mkdir(parents=True, exist_ok=True)

    async def save(self, graph: DistributedGraph) -> str:
        """Persist a snapshot of *graph*. Returns the checkpoint path."""
        snapshot = graph.to_snapshot()
        path = self._dir / f"{graph.id}.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(snapshot, indent=2, default=str), encoding="utf-8")
        tmp.replace(path)
        logger.debug("[Checkpoint] Saved graph %s to %s", graph.id, path)
        return str(path)

    async def load(self, graph_id: str) -> dict[str, Any] | None:
        """Load a raw snapshot dict for *graph_id*.

        Returns ``None`` if no checkpoint exists.
        """
        path = self._dir / f"{graph_id}.json"
        if not path.exists():
            logger.warning("[Checkpoint] No checkpoint found for %s", graph_id)
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        logger.debug("[Checkpoint] Loaded graph %s from %s", graph_id, path)
        return data

    async def list_checkpoints(self) -> list[str]:
        """Return all tracked graph IDs."""
        return [p.stem for p in self._dir.glob("*.json")]

    async def delete(self, graph_id: str) -> bool:
        """Remove a checkpoint. Returns ``True`` if it existed."""
        path = self._dir / f"{graph_id}.json"
        if path.exists():
            path.unlink()
            logger.debug("[Checkpoint] Deleted checkpoint %s", graph_id)
            return True
        return False
