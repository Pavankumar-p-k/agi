"""Shared embedding serialization — standardize on struct.pack format.

All stores MUST use these functions for embedding BLOB serialization
to ensure cross-store compatibility.

Format: struct.pack(f"{n}f", *embedding) — 4 bytes per float32, native endian.
"""

from __future__ import annotations

import struct
from typing import Any

import numpy as np


def serialize_embedding(embedding: np.ndarray | list[float] | tuple[float, ...]) -> bytes:
    """Serialize an embedding vector to bytes using struct.pack."""
    if isinstance(embedding, np.ndarray):
        embedding = embedding.astype(np.float32).tolist()
    return struct.pack(f"{len(embedding)}f", *embedding)


def deserialize_embedding(blob: bytes) -> np.ndarray:
    """Deserialize bytes back to a float32 numpy array."""
    return np.frombuffer(blob, dtype=np.float32)


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two vectors."""
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)
