from __future__ import annotations

import logging
from pathlib import Path


_CONFIGURED = False
_LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"


def configure_logging(level: str = "INFO", log_file: str = "") -> None:
    global _CONFIGURED
    normalized = getattr(logging, str(level).upper(), logging.INFO)
    formatter = logging.Formatter(_LOG_FORMAT)
    root = logging.getLogger("jarvis_os")
    root.setLevel(normalized)
    root.propagate = False
    if root.handlers:
        for handler in root.handlers:
            handler.setLevel(normalized)
            handler.setFormatter(formatter)
        _CONFIGURED = True
        return
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(normalized)
    stream_handler.setFormatter(formatter)
    root.addHandler(stream_handler)
    if log_file:
        target = Path(log_file).expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(target, encoding="utf-8")
        file_handler.setLevel(normalized)
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    if not _CONFIGURED:
        configure_logging()
    logger = logging.getLogger(name)
    logger.setLevel(logging.getLogger("jarvis_os").level or logging.INFO)
    logger.propagate = True
    return logger
