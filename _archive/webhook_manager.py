import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def validate_events(events: str) -> list[str]:
    valid = {"chat.completed", "session.created", "agent.started", "agent.completed"}
    parts = [e.strip() for e in events.replace(",", " ").split() if e.strip()]
    return [e for e in parts if e in valid]


def validate_webhook_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Invalid scheme: {parsed.scheme}")
    if not parsed.netloc:
        raise ValueError("Missing hostname")
    return url
