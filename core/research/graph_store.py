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
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

from core.research.knowledge_graph import KnowledgeGraphManager, GraphNode, GraphEdge

logger = logging.getLogger("jarvis.research.graph_store")


class GraphStore:
    """Persistent storage for the research knowledge graph using JSON files."""

    def __init__(self, storage_dir: str = None):
        self.storage_dir = Path(storage_dir) if storage_dir else Path.home() / ".jarvis" / "research_graphs"
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.current_kg: KnowledgeGraphManager = KnowledgeGraphManager()
        self.active_session: str = ""

    def save_kg(self, kg: KnowledgeGraphManager, session_name: str = None) -> str:
        """Save the knowledge graph to a JSON file."""
        session = session_name or self.active_session or f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        save_path = self.storage_dir / f"{session}.json"

        data = kg.to_dict()
        with open(save_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, default=str)

        logger.info(f"Knowledge graph saved to {save_path}")
        return str(save_path)

    def load_kg(self, session_name: str) -> KnowledgeGraphManager:
        """Load a knowledge graph from a JSON file."""
        load_path = self.storage_dir / f"{session_name}.json"

        if not load_path.exists():
            logger.warning(f"Knowledge graph session '{session_name}' not found")
            return KnowledgeGraphManager()

        try:
            with open(load_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            kg = KnowledgeGraphManager()
            kg.from_dict(data)
            self.current_kg = kg
            self.active_session = session_name

            logger.info(f"Knowledge graph loaded from {load_path}")
            return kg
        except Exception as e:
            logger.error(f"Failed to load knowledge graph: {e}")
            return KnowledgeGraphManager()

    def list_sessions(self) -> List[Dict[str, Any]]:
        """List all saved knowledge graph sessions."""
        sessions = []
        if self.storage_dir.exists():
            for file in self.storage_dir.glob("*.json"):
                try:
                    with open(file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    sessions.append({
                        "session": file.stem,
                        "filename": file.name,
                        "node_count": len(data.get("nodes", [])),
                        "edge_count": len(data.get("edges", [])),
                        "created": file.stat().st_mtime,
                    })
                except Exception as e:
                    logger.warning(f"Could not read session {file.name}: {e}")
        return sessions

    def delete_session(self, session_name: str) -> bool:
        """Delete a knowledge graph session."""
        load_path = self.storage_dir / f"{session_name}.json"
        if load_path.exists():
            try:
                load_path.unlink()
                logger.info(f"Deleted knowledge graph session {session_name}")
                return True
            except Exception as e:
                logger.error(f"Failed to delete session: {e}")
        return False

    def get_current_kg(self) -> KnowledgeGraphManager:
        """Get the currently active knowledge graph."""
        if self.current_kg and self.current_kg.kg.nodes:
            return self.current_kg
        return KnowledgeGraphManager()

    def export_to_json(self, file_path: str = None) -> str:
        """Export current knowledge graph to a specified file."""
        path = Path(file_path) if file_path else self.storage_dir / "current_graph.json"
        if not self.current_kg.kg.nodes:
            logger.warning("No knowledge graph data to export")
            return ""

        self.save_kg(self.current_kg, path.stem if path.stem else "export")
        return str(path)


# Singleton
graph_store = GraphStore()