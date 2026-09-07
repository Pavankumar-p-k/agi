from __future__ import annotations

import json
from pathlib import Path


class GraphCheckpointer:
    def __init__(self, directory=None):
        self.directory = Path(directory or ".checkpoints")
        self.directory.mkdir(parents=True, exist_ok=True)

    async def save(self, graph):
        path = self.directory / f"{graph.id}.json"
        path.write_text(json.dumps(graph.to_snapshot()), encoding="utf-8")
        return str(path)

    async def load(self, graph_id):
        path = self.directory / f"{graph_id}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    async def list_checkpoints(self):
        return sorted(p.stem for p in self.directory.glob("*.json"))

    async def delete(self, graph_id):
        path = self.directory / f"{graph_id}.json"
        if not path.exists():
            return False
        path.unlink()
        return True
