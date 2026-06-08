import logging

logger = logging.getLogger(__name__)


async def run_document_tidy(owner: str = "") -> str:
    logger.info(f"Document tidy requested for owner={owner}")
    return "Document tidy complete"
