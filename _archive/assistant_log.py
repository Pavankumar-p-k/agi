import logging

logger = logging.getLogger(__name__)


def log_to_assistant(owner: str, message: str, category: str = "General"):
    logger.info(f"[{category}] {owner}: {message}")
