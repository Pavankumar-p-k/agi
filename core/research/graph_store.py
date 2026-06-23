"""GraphStore — SQLite-backed knowledge graph storage for nodes and edges."""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import uuid
from pathlib import Path
from typing import Any

from core.research.graph_models import GraphEdge, GraphNode, ALL_EDGE_TYPES, ALL_NODE_TYPES

logger = logging.getLogger(__name__)

_DEFAULT_DB = str(Path("data") / "workflow.db")


class GraphStore:
    """Persistent SQLite-backed knowledge graph.

    Two tables: kg_nodes, kg_edges.
    Coexists in the same database as FactStore and ActivityStore.
    """

    def __init__(self, db_path: str | None = None):
        self._db_path = db_path or _DEFAULT_DB
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self) -> None:
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS kg_nodes (
                    node_id TEXT PRIMARY KEY,
                    node_type TEXT NOT NULL CHECK(node_type IN ('fact','entity','concept')),
                    label TEXT NOT NULL,
                    data_json TEXT DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS kg_edges (
                    edge_id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL REFERENCES kg_nodes(node_id),
                    target_id TEXT NOT NULL REFERENCES kg_nodes(node_id),
                    edge_type TEXT NOT NULL,
                    weight REAL NOT NULL DEFAULT 1.0,
                    metadata_json TEXT DEFAULT '{}'
                );

                CREATE INDEX IF NOT EXISTS idx_kg_edges_source
                    ON kg_edges(source_id);
                CREATE INDEX IF NOT EXISTS idx_kg_edges_target
                    ON kg_edges(target_id);
                CREATE INDEX IF NOT EXISTS idx_kg_edges_type
                    ON kg_edges(edge_type);
                CREATE INDEX IF NOT EXISTS idx_kg_nodes_label
                    ON kg_nodes(label);
                CREATE INDEX IF NOT EXISTS idx_kg_nodes_type
                    ON kg_nodes(node_type);
            """)

    # ── Node CRUD ─────────────────────────────────────────────────────

    def add_node(self, node_id: str, node_type: str, label: str,
                 data: dict[str, Any] | None = None) -> GraphNode:
        assert node_type in ALL_NODE_TYPES, f"Invalid node type: {node_type}"
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """INSERT OR IGNORE INTO kg_nodes (node_id, node_type, label, data_json)
                   VALUES (?, ?, ?, ?)""",
                (node_id, node_type, label, json.dumps(data or {})),
            )
        return GraphNode(node_id=node_id, node_type=node_type, label=label, data=data or {})

    def get_node(self, node_id: str) -> GraphNode | None:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM kg_nodes WHERE node_id=?", (node_id,)
            ).fetchone()
            if row is None:
                return None
            return _row_to_node(row)

    def find_nodes_by_label(self, label: str,
                            node_type: str | None = None) -> list[GraphNode]:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            if node_type:
                rows = conn.execute(
                    "SELECT * FROM kg_nodes WHERE label=? AND node_type=?",
                    (label, node_type),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM kg_nodes WHERE label LIKE ?",
                    (f"%{label}%",),
                ).fetchall()
            return [_row_to_node(r) for r in rows]

    def list_nodes(self, node_type: str | None = None) -> list[GraphNode]:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            if node_type:
                rows = conn.execute(
                    "SELECT * FROM kg_nodes WHERE node_type=? ORDER BY label",
                    (node_type,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM kg_nodes ORDER BY node_type, label"
                ).fetchall()
            return [_row_to_node(r) for r in rows]

    def delete_node(self, node_id: str) -> None:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute("DELETE FROM kg_edges WHERE source_id=? OR target_id=?",
                         (node_id, node_id))
            conn.execute("DELETE FROM kg_nodes WHERE node_id=?", (node_id,))

    def count_nodes(self) -> dict[str, int]:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT node_type, COUNT(*) as cnt FROM kg_nodes GROUP BY node_type"
            ).fetchall()
            counts: dict[str, int] = {}
            for r in rows:
                counts[r["node_type"]] = r["cnt"]
            return counts

    # ── Edge CRUD ─────────────────────────────────────────────────────

    def add_edge(self, source_id: str, target_id: str, edge_type: str,
                 weight: float = 1.0,
                 metadata: dict[str, Any] | None = None) -> str:
        assert edge_type in ALL_EDGE_TYPES, f"Invalid edge type: {edge_type}"
        edge_id = f"e_{uuid.uuid4().hex[:12]}"
        # Avoid duplicate edges
        with self._lock, sqlite3.connect(self._db_path) as conn:
            existing = conn.execute(
                "SELECT edge_id FROM kg_edges WHERE source_id=? AND target_id=? AND edge_type=?",
                (source_id, target_id, edge_type),
            ).fetchone()
            if existing:
                return existing[0]

            conn.execute(
                """INSERT INTO kg_edges (edge_id, source_id, target_id, edge_type, weight, metadata_json)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (edge_id, source_id, target_id, edge_type, weight,
                 json.dumps(metadata or {})),
            )
        return edge_id

    def get_edge(self, edge_id: str) -> GraphEdge | None:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM kg_edges WHERE edge_id=?", (edge_id,)
            ).fetchone()
            if row is None:
                return None
            return _row_to_edge(row)

    def get_edges_for_node(self, node_id: str) -> list[GraphEdge]:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM kg_edges WHERE source_id=? OR target_id=?",
                (node_id, node_id),
            ).fetchall()
            return [_row_to_edge(r) for r in rows]

    def get_edges_and_neighbors(self, node_id: str
                                 ) -> tuple[list[GraphEdge], list[str]]:
        """Get all edges from a node plus neighbor node IDs."""
        edges = self.get_edges_for_node(node_id)
        neighbors: list[str] = []
        for e in edges:
            if e.source_id == node_id and e.target_id not in neighbors:
                neighbors.append(e.target_id)
            elif e.target_id == node_id and e.source_id not in neighbors:
                neighbors.append(e.source_id)
        return edges, neighbors

    def find_edges_by_type(self, entity_name: str,
                           edge_type: str) -> list[GraphEdge]:
        """Find edges of a specific type connected to an entity label."""
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT e.* FROM kg_edges e
                   JOIN kg_nodes n ON (e.source_id = n.node_id OR e.target_id = n.node_id)
                   WHERE n.label LIKE ? AND e.edge_type=?
                   ORDER BY e.weight DESC""",
                (f"%{entity_name}%", edge_type),
            ).fetchall()
            return [_row_to_edge(r) for r in rows]

    def get_fact_ids_for_entity(self, entity_name: str) -> list[str]:
        """Get all fact node IDs that reference this entity."""
        with self._lock, sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                """SELECT e.source_id FROM kg_edges e
                   JOIN kg_nodes n ON e.target_id = n.node_id
                   WHERE n.label=? AND e.edge_type='REFERENCES'""",
                (entity_name,),
            ).fetchall()
            return [r[0] for r in rows]

    def get_fact_for_node(self, node_id: str):
        """Get the Fact data from a fact node."""
        node = self.get_node(node_id)
        if node is None or node.node_type != "fact":
            return None
        from core.research.models import Fact
        from datetime import datetime
        d = node.data
        return Fact(
            fact_id=d.get("fact_id", node_id),
            source_url=d.get("source_url", ""),
            claim=d.get("claim", node.label),
            confidence=d.get("confidence", 0.5),
            category=d.get("category", "general"),
            tags=d.get("tags", []),
            timestamp=datetime.fromisoformat(d["timestamp"]) if d.get("timestamp") else None,
        )

    def get_linked_nodes(self, node_id: str,
                         edge_type: str | None = None) -> list[GraphNode]:
        """Get nodes linked to this node, optionally filtered by edge type."""
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            if edge_type:
                rows = conn.execute(
                    """SELECT n.* FROM kg_nodes n
                       JOIN kg_edges e ON n.node_id = e.target_id
                       WHERE e.source_id=? AND e.edge_type=?
                       UNION
                       SELECT n.* FROM kg_nodes n
                       JOIN kg_edges e ON n.node_id = e.source_id
                       WHERE e.target_id=? AND e.edge_type=?""",
                    (node_id, edge_type, node_id, edge_type),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT DISTINCT n.* FROM kg_nodes n
                       JOIN kg_edges e ON n.node_id = e.target_id
                       WHERE e.source_id=?
                       UNION
                       SELECT DISTINCT n.* FROM kg_nodes n
                       JOIN kg_edges e ON n.node_id = e.source_id
                       WHERE e.target_id=?""",
                    (node_id, node_id),
                ).fetchall()
            return [_row_to_node(r) for r in rows]

    def delete_edge(self, edge_id: str) -> None:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute("DELETE FROM kg_edges WHERE edge_id=?", (edge_id,))

    def count_edges(self) -> dict[str, int]:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT edge_type, COUNT(*) as cnt FROM kg_edges GROUP BY edge_type"
            ).fetchall()
            counts: dict[str, int] = {}
            for r in rows:
                counts[r["edge_type"]] = r["cnt"]
            return counts

    def clear(self) -> None:
        """Clear all graph data (for testing)."""
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute("DELETE FROM kg_edges")
            conn.execute("DELETE FROM kg_nodes")


def _row_to_node(row: sqlite3.Row) -> GraphNode:
    data = json.loads(row["data_json"]) if row["data_json"] else {}
    return GraphNode(
        node_id=row["node_id"],
        node_type=row["node_type"],
        label=row["label"],
        data=data,
    )


def _row_to_edge(row: sqlite3.Row) -> GraphEdge:
    metadata = json.loads(row["metadata_json"]) if row["metadata_json"] else {}
    return GraphEdge(
        edge_id=row["edge_id"],
        source_id=row["source_id"],
        target_id=row["target_id"],
        edge_type=row["edge_type"],
        weight=row["weight"],
        metadata=metadata,
    )
