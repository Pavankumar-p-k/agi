"""integrations/whatsapp/media.py
Media download, caching, and type detection utilities.
"""
from __future__ import annotations

import logging
import mimetypes
import os
import tempfile
from pathlib import Path
from typing import Any

from .models import WhatsAppMedia, WhatsAppMessage

logger = logging.getLogger(__name__)

MEDIA_EXTENSIONS: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "audio/ogg": ".ogg",
    "audio/mpeg": ".mp3",
    "audio/mp4": ".m4a",
    "audio/amr": ".amr",
    "video/mp4": ".mp4",
    "video/3gp": ".3gp",
    "application/pdf": ".pdf",
    "application/msword": ".doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "text/plain": ".txt",
    "application/zip": ".zip",
}


class MediaManager:
    def __init__(self, cache_dir: str | None = None):
        self._cache_dir = Path(cache_dir or os.path.join(tempfile.gettempdir(), "jarvis_whatsapp_media"))
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    def get_extension(self, mime_type: str) -> str:
        ext = MEDIA_EXTENSIONS.get(mime_type)
        if ext:
            return ext
        guessed = mimetypes.guess_extension(mime_type)
        return guessed or ".bin"

    def is_image(self, mime_type: str) -> bool:
        return mime_type.startswith("image/")

    def is_audio(self, mime_type: str) -> bool:
        return mime_type.startswith("audio/")

    def is_document(self, mime_type: str) -> bool:
        return mime_type.startswith("application/")

    def is_video(self, mime_type: str) -> bool:
        return mime_type.startswith("video/")

    def get_cache_path(self, media_id: str, mime_type: str) -> Path:
        ext = self.get_extension(mime_type)
        return self._cache_dir / f"{media_id}{ext}"

    async def download_and_cache(
        self,
        provider: Any,
        media: WhatsAppMedia,
    ) -> Path | None:
        cache_path = self.get_cache_path(media.id, media.mime_type)
        if cache_path.exists():
            logger.debug("[MediaManager] Cache hit: %s", cache_path)
            media.local_path = str(cache_path)
            return cache_path
        data = await provider.download_media(media.id, media.mime_type)
        if data is None:
            logger.warning("[MediaManager] Download failed: %s", media.id)
            return None
        cache_path.write_bytes(data)
        media.local_path = str(cache_path)
        logger.info("[MediaManager] Cached: %s (%d bytes)", cache_path, len(data))
        return cache_path

    def cleanup_old(self, max_age_hours: int = 24):
        import time
        now = time.time()
        removed = 0
        for f in self._cache_dir.iterdir():
            if f.is_file() and (now - f.stat().st_mtime) > max_age_hours * 3600:
                f.unlink(missing_ok=True)
                removed += 1
        if removed:
            logger.info("[MediaManager] Cleaned %d old files from cache", removed)
