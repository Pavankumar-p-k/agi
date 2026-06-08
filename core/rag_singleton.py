import logging
import os
import time
from pathlib import Path

logger = logging.getLogger(__name__)

rag_instance = None
_last_attempt = 0.0
_RETRY_INTERVAL = 30


def get_rag_manager():
    global rag_instance, _last_attempt
    if rag_instance is not None:
        return rag_instance
    now = time.monotonic()
    if now - _last_attempt < _RETRY_INTERVAL:
        return None
    _last_attempt = now
    try:
        from core.rag_vector import VectorRAG
        base_dir = Path(__file__).parent.parent
        persist_dir = os.path.join(base_dir, "data", "rag")
        rag_instance = VectorRAG(persist_directory=persist_dir)
        if not rag_instance.healthy:
            rag_instance = None
        else:
            logger.info("Initialized VectorRAG")
    except Exception as e:
        logger.warning(f"RAG init failed: {e}")
        rag_instance = None
    return rag_instance
