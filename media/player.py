import logging
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from core.config import MUSIC_DIR

logger = logging.getLogger(__name__)


@dataclass
class Track:
    title: str
    artist: str
    path: str
    duration: int = 0
    tags: List[str] = field(default_factory=list)


_PLAYER_CHAIN = ["vlc", "mpv", "ffplay", "mplayer", "cvlc"]


def _find_player() -> Optional[str]:
    for player in _PLAYER_CHAIN:
        try:
            subprocess.run([player, "--version"], capture_output=True, timeout=5)
            return player
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    return None


class MediaPlayer:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._playlist: List[Track] = []
        self._index: int = 0
        self._state: str = "stopped"
        self._volume: int = 80
        self._process: Optional[subprocess.Popen] = None
        self._player: Optional[str] = _find_player()
        self._load_playlist()
        if not self._player:
            logger.info("No media player found. Install vlc, mpv, or ffplay.")

    def _load_playlist(self) -> None:
        music_dir = Path(MUSIC_DIR)
        if not music_dir.exists():
            logger.debug("Music dir %s not found", MUSIC_DIR)
            return
        files = list(music_dir.rglob("*.mp3")) + list(music_dir.rglob("*.wav")) + list(music_dir.rglob("*.flac")) + list(music_dir.rglob("*.ogg"))
        for f in files:
            self._playlist.append(Track(title=f.stem, artist="Unknown", path=str(f)))
        logger.info("Loaded %d tracks from %s", len(self._playlist), MUSIC_DIR)

    def get_status(self) -> dict:
        with self._lock:
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
        with self._lock:
            return [t.__dict__ for t in self._playlist]

    def play(self, path: Optional[str] = None) -> None:
        with self._lock:
            target = path or (self._playlist[self._index].path if self._playlist else None)
            if not target:
                logger.info("Nothing to play.")
                return
            self._state = "playing"
            self._stop_current()
        self._launch_player(target)

    def _launch_player(self, path: str) -> None:
        player = self._player
        if not player:
            logger.info("No media player available. Install vlc or mpv.")
            return
        try:
            self._process = subprocess.Popen(
                [player, path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            logger.info("Playing %s with %s", Path(path).name, player)
        except FileNotFoundError:
            self._player = _find_player()
            logger.warning("Player not found, retrying with fallback")

    def _stop_current(self) -> None:
        if self._process and self._process.poll() is None:
            try:
                self._process.terminate()
                self._process.wait(timeout=5)
            except Exception:
                self._process.kill()
            self._process = None

    def play_by_index(self, idx: int) -> None:
        with self._lock:
            if 0 <= idx < len(self._playlist):
                self._index = idx
                target = self._playlist[idx].path
                self._state = "playing"
                self._stop_current()
        if target:
            self._launch_player(target)

    def play_by_name(self, query: str) -> bool:
        q = query.lower()
        with self._lock:
            for i, t in enumerate(self._playlist):
                if q in t.title.lower():
                    self._index = i
                    self._state = "playing"
                    self._stop_current()
                    self._launch_player(t.path)
                    return True
        return False

    def pause(self) -> None:
        with self._lock:
            self._state = "paused"
        if self._process and self._process.poll() is None:
            try:
                self._process.signal(subprocess.signal.SIGSTOP)
            except (AttributeError, ValueError):
                logger.warning("Pause not supported on this platform")

    def next_track(self) -> None:
        with self._lock:
            if not self._playlist:
                return
            self._index = (self._index + 1) % len(self._playlist)
            target = self._playlist[self._index].path
            self._state = "playing"
            self._stop_current()
        self._launch_player(target)

    def set_volume(self, volume: int) -> None:
        with self._lock:
            self._volume = max(0, min(100, volume))

    def stop(self) -> None:
        with self._lock:
            self._state = "stopped"
            self._stop_current()


_MOOD_TAGS = {
    "happy": ["happy", "upbeat", "joy", "party", "pop"],
    "sad": ["sad", "melancholy", "blues", "slow", "ballad"],
    "relaxed": ["chill", "ambient", "lofi", "calm", "jazz"],
    "energetic": ["rock", "metal", "electronic", "dance", "workout"],
    "focused": ["classical", "instrumental", "study", "focus", "piano"],
    "sleepy": ["sleep", "lullaby", "night", "soft", "rain"],
}


class MusicSuggester:
    def suggest(self, mood: str) -> list:
        mood_lower = mood.lower().strip()
        tags = _MOOD_TAGS.get(mood_lower, [])
        if not tags:
            for key, vals in _MOOD_TAGS.items():
                if mood_lower in vals:
                    tags = vals
                    break
        if not tags:
            return []
        all_tracks = media_player.get_playlist()
        scored = []
        for t in all_tracks:
            score = sum(1 for tag in tags if tag in t.get("title", "").lower() or tag in t.get("artist", "").lower())
            if score > 0:
                scored.append((score, t))
        scored.sort(key=lambda x: -x[0])
        return [t for _, t in scored]


media_player = MediaPlayer()
music_suggester = MusicSuggester()
