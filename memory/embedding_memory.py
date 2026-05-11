import sqlite3
import numpy as np
import requests
import json
import os
from typing import List, Dict, Optional

class EmbeddingMemory:
    """
    Semantic memory using nomic-embed-text and SQLite.
    """
    def __init__(self, db_path: str = "data/jarvis_memory.db"):
        self.db_path = db_path
        self.ollama_url = "http://localhost:11434/api/embeddings"
        self._init_db()

    def _init_db(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS semantic_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT,
                metadata TEXT,
                embedding BLOB,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.close()

    def embed(self, text: str) -> np.ndarray:
        try:
            resp = requests.post(self.ollama_url, json={
                "model": "nomic-embed-text",
                "prompt": text
            }, timeout=10)
            resp.raise_for_status()
            return np.array(resp.json()["embedding"], dtype=np.float32)
        except Exception as e:
            print(f"[Memory] Embedding error: {e}")
            return np.zeros(768, dtype=np.float32)

    def store(self, text: str, metadata: Dict = None):
        embedding = self.embed(text)
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO semantic_memory (text, metadata, embedding) VALUES (?, ?, ?)",
            (text, json.dumps(metadata or {}), embedding.tobytes())
        )
        conn.commit()
        conn.close()

    def semantic_search(self, query: str, top_k: int = 5) -> List[Dict]:
        query_embedding = self.embed(query)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("SELECT text, metadata, embedding FROM semantic_memory")
        
        results = []
        for text, metadata, emb_blob in cursor:
            emb = np.frombuffer(emb_blob, dtype=np.float32)
            # Cosine similarity
            similarity = np.dot(query_embedding, emb) / (np.linalg.norm(query_embedding) * np.linalg.norm(emb) + 1e-9)
            results.append({
                "text": text,
                "metadata": json.loads(metadata),
                "score": float(similarity)
            })
        
        conn.close()
        return sorted(results, key=lambda x: x["score"], reverse=True)[:top_k]

# Instance
embedding_memory = EmbeddingMemory()
