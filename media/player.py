# media/player.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from core.config import MUSIC_DIR


@dataclass
class Track:
    title: str
    artist: str
    path: str
    duration: int = 0


class MediaPlayer:
    def __init__(self) -> None:
        self._playlist: List[Track] = []
        self._index: int = 0
        self._state: str = "stopped"
        self._volume: int = 80
        self._load_playlist()

    def _load_playlist(self) -> None:
        music_dir = Path(MUSIC_DIR)
        if not music_dir.exists():
            return
        files = list(music_dir.rglob("*.mp3")) + list(music_dir.rglob("*.wav"))
        for f in files:
            self._playlist.append(Track(title=f.stem, artist="Unknown", path=str(f)))

    def get_status(self) -> dict:
        track = self._playlist[self._index] if self._playlist else None
        return {
            "state": self._state,
            "track": track.__dict__ if track else None,
            "position": 0,
            "volume": self._volume,
            "shuffle": False,
            "repeat": False,
        }

    def get_playlist(self) -> list:
        return [t.__dict__ for t in self._playlist]

    def play(self) -> None:
        if self._playlist:
            self._state = "playing"

    def play_by_index(self, idx: int) -> None:
        if 0 <= idx < len(self._playlist):
            self._index = idx
            self._state = "playing"

    def play_by_name(self, query: str) -> bool:
        q = query.lower()
        for i, t in enumerate(self._playlist):
            if q in t.title.lower():
                self.play_by_index(i)
                return True
        return False

    def pause(self) -> None:
        self._state = "paused"

    def next_track(self) -> None:
        if not self._playlist:
            return
        self._index = (self._index + 1) % len(self._playlist)
        self._state = "playing"

    def set_volume(self, volume: int) -> None:
        self._volume = max(0, min(100, volume))


class MusicSuggester:
    def suggest(self, mood: str) -> list:
        return []


media_player = MediaPlayer()
music_suggester = MusicSuggester()
