"""Text similarity utilities — tokenization, Jaccard, embedding-based similarity.

Extracted from the deprecated core.memory module so that consumers can
import from here instead. New code MUST import from this module.
"""

from __future__ import annotations

import logging

import numpy as np

logger = logging.getLogger(__name__)

_embedding_client = None


def _get_embedder():
    global _embedding_client
    if _embedding_client is None:
        try:
            from core.embeddings import get_embedding_client
            _embedding_client = get_embedding_client()
        except Exception as _e:
            logger.debug("similarity _get_embedder failed: %s", _e)
            _embedding_client = False
    return _embedding_client if _embedding_client is not False else None


def tokenize(text: str) -> list[str]:
    """Simple tokenizer that splits on whitespace and removes punctuation."""
    return [word.strip('.,!?";') for word in text.split()]


def jaccard_similarity(text1: str, text2: str) -> float:
    """Calculate Jaccard similarity between two texts."""
    if not text1 or not text2:
        return 0.0

    tokens1 = set(tokenize(text1.lower()))
    tokens2 = set(tokenize(text2.lower()))

    if not tokens1 and not tokens2:
        return 1.0
    if not tokens1 or not tokens2:
        return 0.0

    intersection = tokens1.intersection(tokens2)
    union = tokens1.union(tokens2)

    return len(intersection) / len(union)


def get_text_similarity(text1: str, text2: str) -> float:
    """Calculate semantic similarity using embeddings, with Jaccard fallback."""
    embedder = _get_embedder()
    if embedder is not None:
        try:
            vecs = embedder.encode([text1, text2], normalize_embeddings=True)
            if vecs.size > 0:
                sim = float(np.dot(vecs[0], vecs[1]))
                return max(0.0, min(1.0, sim))
        except Exception as _e:
            logger.debug("get_text_similarity failed: %s", _e)
    return jaccard_similarity(text1, text2)
