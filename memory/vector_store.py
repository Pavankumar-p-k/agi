"""Unified ChromaDB vector store — single instance, single import.

All vector consumers should use this module instead of creating
their own ChromaDB connections. Replaces core/memory_vector.py.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_COLLECTION = "odysseus_memories"
_COLLECTION = None
_CLIENT = None


def get_chroma_collection(
    collection_name: str = DEFAULT_COLLECTION,
    metadata: dict[str, Any] | None = None,
):
    """Get or create a named ChromaDB collection from the shared singleton client."""
    global _COLLECTION, _CLIENT

    if _COLLECTION is not None and _COLLECTION.name == collection_name:
        return _COLLECTION

    try:
        from core.chroma_client import get_chroma_client

        client = get_chroma_client()
        meta = metadata or {"hnsw:space": "cosine"}
        _COLLECTION = client.get_or_create_collection(
            name=collection_name,
            metadata=meta,
        )
        _CLIENT = client
        return _COLLECTION
    except Exception as e:
        logger.debug("ChromaDB collection %r unavailable: %s", collection_name, e)
        return None


def get_embedder():
    """Get the shared embedding client."""
    try:
        from core.embeddings import get_embedding_client
        return get_embedding_client()
    except Exception as e:
        logger.debug("Embedding client unavailable: %s", e)
        return None


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed texts using the shared embedding client."""
    embedder = get_embedder()
    if embedder is None:
        return []
    vecs = embedder.encode(texts, normalize_embeddings=True)
    return vecs.tolist()


def search_collection(
    collection_name: str,
    query: str,
    k: int = 8,
    where: dict[str, Any] | None = None,
) -> list[dict]:
    """Search a named collection and return results with id, score, document, metadata."""
    collection = get_chroma_collection(collection_name)
    if collection is None or collection.count() == 0:
        return []

    embeddings = embed_texts([query])
    if not embeddings:
        return []

    actual_k = min(k, collection.count())
    try:
        results = collection.query(
            query_embeddings=embeddings,
            n_results=actual_k,
            where=where,
        )
    except Exception as e:
        logger.debug("ChromaDB query failed: %s", e)
        return []

    out = []
    for idx, mid in enumerate(results["ids"][0]):
        distance = results["distances"][0][idx] if results.get("distances") else 0.0
        out.append({
            "id": mid,
            "score": round(1.0 - distance, 4),
            "document": (results["documents"][0][idx] if results.get("documents") else ""),
            "metadata": (results["metadatas"][0][idx] if results.get("metadatas") else {}),
        })
    return out


def add_to_collection(
    collection_name: str,
    ids: list[str],
    texts: list[str],
    metadatas: list[dict[str, Any]] | None = None,
):
    """Add entries to a named collection."""
    collection = get_chroma_collection(collection_name)
    if collection is None:
        return
    embeddings = embed_texts(texts)
    if not embeddings:
        return
    try:
        collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas or [{}] * len(ids),
        )
    except Exception as e:
        logger.debug("ChromaDB add failed: %s", e)


def delete_from_collection(collection_name: str, ids: list[str]):
    """Delete entries from a named collection."""
    collection = get_chroma_collection(collection_name)
    if collection is None:
        return
    try:
        collection.delete(ids=ids)
    except Exception as e:
        logger.debug("ChromaDB delete failed: %s", e)


def rebuild_collection(
    collection_name: str,
    ids: list[str],
    texts: list[str],
    metadatas: list[dict[str, Any]] | None = None,
):
    """Delete and recreate a collection, then batch-add entries."""
    collection = get_chroma_collection(collection_name)
    if collection is None:
        return
    try:
        import chromadb
        from core.chroma_client import get_chroma_client
        client = get_chroma_client()
        client.delete_collection(collection_name)
    except Exception:
        pass
    get_chroma_collection(collection_name, metadata={"hnsw:space": "cosine"})
    batch_size = 100
    for i in range(0, len(texts), batch_size):
        batch_ids = ids[i:i + batch_size]
        batch_texts = texts[i:i + batch_size]
        batch_meta = (metadatas[i:i + batch_size] if metadatas else [{}] * len(batch_ids))
        add_to_collection(collection_name, batch_ids, batch_texts, batch_meta)
