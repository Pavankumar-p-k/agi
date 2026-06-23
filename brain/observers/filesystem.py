from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from brain.events.event_bus import Event
from brain.events.event_types import FileCreated, FileModified, FileDeleted

from .observer_manager import Observer

logger = logging.getLogger(__name__)


class FileSystemObserver(Observer):
    """Watches directories for file creation, modification, and deletion.

    Uses polling (os.stat) to detect changes. In production, swap in
    watchdog (inotify/FSEvents/kqueue) for instant notification.
    """

    def __init__(self, watch_dirs: list[str] | None = None,
                 poll_interval: float = 10.0, **kwargs):
        super().__init__(name="filesystem", poll_interval=poll_interval, **kwargs)
        self._watch_dirs = watch_dirs or []
        self._snapshots: dict[str, dict[str, float]] = {}

    def add_watch(self, directory: str):
        abs_path = os.path.abspath(directory)
        if abs_path not in self._watch_dirs:
            self._watch_dirs.append(abs_path)
            logger.info("[FileSystemObserver] watching: %s", abs_path)

    def remove_watch(self, directory: str):
        abs_path = os.path.abspath(directory)
        if abs_path in self._watch_dirs:
            self._watch_dirs.remove(abs_path)
        self._snapshots.pop(abs_path, None)

    async def observe(self) -> list[Event]:
        events: list[Event] = []

        for watch_dir in self._watch_dirs:
            if not os.path.isdir(watch_dir):
                continue

            current: dict[str, float] = {}
            try:
                for root, dirs, files in os.walk(watch_dir):
                    for fname in files:
                        fpath = os.path.join(root, fname)
                        try:
                            stat = os.stat(fpath)
                            current[fpath] = stat.st_mtime
                        except OSError:
                            continue
            except OSError as e:
                logger.debug("[FileSystemObserver] walk error %s: %s", watch_dir, e)
                continue

            previous = self._snapshots.get(watch_dir, {})

            # Detect new files
            for fpath in current:
                if fpath not in previous:
                    try:
                        size = os.path.getsize(fpath)
                    except OSError:
                        size = 0
                    events.append(Event(
                        type="file.created",
                        source="observer.filesystem",
                        payload=FileCreated(path=fpath, size_bytes=size).__dict__,
                    ))

            # Detect modified files
            for fpath, mtime in current.items():
                if fpath in previous and previous[fpath] != mtime:
                    try:
                        size = os.path.getsize(fpath)
                    except OSError:
                        size = 0
                    events.append(Event(
                        type="file.modified",
                        source="observer.filesystem",
                        payload=FileModified(path=fpath, size_bytes=size).__dict__,
                    ))

            # Detect deleted files
            for fpath in previous:
                if fpath not in current:
                    events.append(Event(
                        type="file.deleted",
                        source="observer.filesystem",
                        payload=FileDeleted(path=fpath).__dict__,
                    ))

            self._snapshots[watch_dir] = current

        if events:
            logger.debug("[FileSystemObserver] %d events", len(events))
        return events
