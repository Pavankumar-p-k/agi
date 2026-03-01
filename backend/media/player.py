from __future__ import annotations

from core.config import MUSIC_DIR


class MediaPlayer:
    def __init__(self) -> None:
        self.playing = False
        self.volume = 70
        self.playlist = []
        self.track_index = 0

    def _current_track(self):
        if not self.playlist:
            return None
        if self.track_index < 0 or self.track_index >= len(self.playlist):
            self.track_index = 0
        return self.playlist[self.track_index]

    def get_status(self) -> dict:
        return {
            'playing': self.playing,
            'volume': self.volume,
            'track': self._current_track(),
            'music_dir': MUSIC_DIR,
        }

    def play(self) -> None:
        self.playing = True

    def pause(self) -> None:
        self.playing = False

    def next_track(self) -> None:
        if self.playlist:
            self.track_index = (self.track_index + 1) % len(self.playlist)

    def set_volume(self, volume: int) -> None:
        self.volume = max(0, min(100, volume))

    def get_playlist(self) -> list:
        return list(self.playlist)

    def play_by_name(self, query: str) -> bool:
        for idx, item in enumerate(self.playlist):
            if query.lower() in str(item).lower():
                self.track_index = idx
                self.playing = True
                return True
        return False

    def play_by_index(self, track_index: int) -> None:
        if not self.playlist:
            return
        self.track_index = max(0, min(len(self.playlist) - 1, track_index))
        self.playing = True


class MusicSuggester:
    def suggest_by_mood(self, mood: str) -> dict:
        return {'mood': mood, 'suggestions': ['lofi focus mix', 'instrumental chill', 'ambient coding set']}

    def suggest_similar(self, track: str) -> dict:
        return {'based_on': track, 'suggestions': [f'{track} (live)', f'{track} (acoustic)', f'{track} remix']}


media_player = MediaPlayer()
music_suggester = MusicSuggester()
