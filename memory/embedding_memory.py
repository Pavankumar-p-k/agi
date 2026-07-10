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
import logging
import sqlite3
import requests
import json
import os
from typing import List, Dict, Optional, Union

import numpy as np

from core.result import Ok, Err, Result
from core.errors import ProviderError, StorageError

logger = logging.getLogger(__name__)

class EmbeddingMemory:
    """
    Semantic memory using nomic-embed-text and SQLite.

    Notes:
    - Uses Ollama embedding endpoint by default. If Ollama is not available,
      embed() returns an Err(ProviderError) and callers should handle gracefully.
    """
    def __init__(self, db_path: str | None = None):
        if db_path is None:
            from core.storage import SYSTEM_DB
            db_path = SYSTEM_DB
        self.db_path = db_path
        self.ollama_url = os.getenv("OLLAMA_EMBEDDING_URL", "http://localhost:11434/api/embed")
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

    def embed(self, text: str) -> Result:
        try:
            resp = requests.post(self.ollama_url, json={
                "model": os.getenv("EMBEDDING_MODEL", "nomic-embed-text"),
                "input": text
            }, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            emb = data.get("embeddings", [])
            if emb:
                emb = emb[0]
            else:
                emb = data.get("embedding") or data.get("response") or data
            if isinstance(emb, dict) and "embedding" in emb:
                emb = emb["embedding"]
            if not isinstance(emb, (list, tuple)):
                raise ValueError("Embedding response not in expected format")
            return Ok(np.array(emb, dtype=np.float32))
        except Exception as e:
            logger.exception("[Memory] Embedding error")
            return Err(ProviderError(f"Embedding failed: {e}"))

    def store(self, text: str, metadata: Dict = None):
        try:
            embedding_result = self.embed(text)
        except Exception as e:
            logger.error("[Memory] Skipping store — embedding exception: %s", e)
            return
        if hasattr(embedding_result, 'is_err') and embedding_result.is_err():
            logger.error("[Memory] Skipping store — embedding failed: %s", embedding_result._error)
            return
        embedding = embedding_result.unwrap() if hasattr(embedding_result, 'unwrap') else embedding_result
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO semantic_memory (text, metadata, embedding) VALUES (?, ?, ?)",
            (text, json.dumps(metadata or {}), embedding.tobytes())
        )
        conn.commit()
        conn.close()

    def semantic_search(self, query: str, top_k: int = 5) -> Result:
        embedding_result = self.embed(query)
        if hasattr(embedding_result, 'is_err') and embedding_result.is_err():
            return Err(embedding_result._error)
        query_embedding = embedding_result.unwrap() if hasattr(embedding_result, 'unwrap') else embedding_result

        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("SELECT text, metadata, embedding FROM semantic_memory")

        results = []
        for text, metadata, emb_blob in cursor:
            try:
                emb = np.frombuffer(emb_blob, dtype=np.float32)
                similarity = np.dot(query_embedding, emb) / (np.linalg.norm(query_embedding) * np.linalg.norm(emb) + 1e-9)
                results.append({
                    "text": text,
                    "metadata": json.loads(metadata),
                    "score": float(similarity)
                })
            except Exception:
                logger.exception("[Memory] Skipping corrupted embedding row")
                continue

        conn.close()
        return Ok(sorted(results, key=lambda x: x["score"], reverse=True)[:top_k])

# Instance (lazy: instantiate on first import to avoid init-time network calls in tests)
embedding_memory = None

def get_embedding_memory():
    global embedding_memory
    if embedding_memory is None:
        embedding_memory = EmbeddingMemory()
    return embedding_memory
