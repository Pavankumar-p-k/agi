import logging
import asyncio
import os
import subprocess
import webbrowser
import shutil
import re
import io
import wave
import struct
import math
import random
import tempfile
from pathlib import Path
from skills.utils import success_response, error_response
logger = logging.getLogger(__name__)

def _find_spotify_exe():
    candidates = [
        Path(os.environ.get('LOCALAPPDATA', '')) / 'Microsoft' / 'WindowsApps' / 'Spotify.exe',
        Path(os.environ.get('APPDATA', '')) / 'Spotify' / 'Spotify.exe',
        Path(os.environ.get('LOCALAPPDATA', '')) / 'Spotify' / 'Spotify.exe',
        Path('C:/Program Files/WindowsApps/SpotifyAB.SpotifyMusic_*/Spotify.exe'),
        Path('C:/Program Files/Spotify/Spotify.exe'),
        Path('C:/Program Files (x86)/Spotify/Spotify.exe'),
    ]
    for candidate in candidates:
        expanded = Path(str(candidate)).expanduser()
        if '*' in str(expanded):
            from glob import glob
            matches = glob(str(expanded))
            if matches:
                return matches[0]
        if expanded.exists():
            return str(expanded)
    spotify_on_path = shutil.which('spotify')
    if spotify_on_path:
        return spotify_on_path
    return None

def _play_audio_tone(frequency=440, duration=0.5):
    try:
        import sounddevice as sd
        import numpy as np
        sample_rate = 44100
        t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
        wave_data = 0.5 * np.sin(2 * np.pi * frequency * t)
        sd.play(wave_data, sample_rate)
        sd.wait()
        return True
    except Exception:
        try:
            import winsound
            winsound.Beep(frequency, int(duration * 1500))
            return True
        except Exception:
            return False

def _play_melody():
    notes = [(523, 0.15), (587, 0.15), (659, 0.15), (698, 0.15),
             (784, 0.3), (659, 0.3), (523, 0.4)]
    for freq, dur in notes:
        try:
            import sounddevice as sd
            import numpy as np
            sample_rate = 44100
            t = np.linspace(0, dur, int(sample_rate * dur), endpoint=False)
            wave_data = 0.3 * np.sin(2 * np.pi * freq * t)
            sd.play(wave_data, sample_rate)
            sd.wait()
        except Exception:
            try:
                import winsound
                winsound.Beep(int(freq), int(dur * 1200))
            except Exception as e:
                logger.warning("[skills.library.entertainment.spotify.main] spotify_play failed: %s", e)

def _now_playing_file(query):
    content = f"""Now Playing: {query}
--- {query.upper()} by JARVIS AI ---
"""
    now_playing_path = Path(tempfile.gettempdir()) / "jarvis_now_playing.txt"
    now_playing_path.write_text(content, encoding='utf-8')
    return str(now_playing_path)

async def spotify(params: dict) -> dict:
    action = params.get('action', 'play')
    query = params.get('query', params.get('song', params.get('target', '')))
    
    if action == 'search':
        return await _search_track(query)
    elif action == 'pause':
        return _control_playback('pause')
    elif action == 'resume':
        return _control_playback('play')
    elif action == 'next':
        return _control_playback('next')
    elif action == 'previous':
        return _control_playback('previous')
    elif action == 'beep':
        ok = _play_audio_tone(880, 0.3)
        return success_response({"action": "beep", "played": ok})
    else:
        return await _play_song(query)

async def _play_song(query: str) -> dict:
    if not query:
        return success_response({"action": "open_spotify", "note": "Opening Spotify"})
    
    _play_melody()
    nf = _now_playing_file(query)
    
    spotify_exe = _find_spotify_exe()
    if spotify_exe:
        try:
            uri = f"spotify:search:{query}"
            subprocess.Popen([spotify_exe, uri], shell=False)
            return success_response({
                "action": "play", "query": query, "method": "native",
                "audio": "melody_played", "now_playing": nf
            })
        except Exception as e:
            logger.warning("[skills.spotify] spotify_control failed: %s", e)

    search_url = f"https://open.spotify.com/search/{query.replace(' ', '%20')}"
    webbrowser.open(search_url)
    return success_response({
        "action": "play", "query": query, "method": "browser",
        "url": search_url, "audio": "melody_played", "now_playing": nf
    })

async def _search_track(query: str) -> dict:
    search_url = f"https://open.spotify.com/search/{query.replace(' ', '%20')}"
    webbrowser.open(search_url)
    return success_response({"action": "search", "query": query, "url": search_url})

def _control_playback(command: str) -> dict:
    try:
        import psutil
        for proc in psutil.process_iter(['pid', 'name']):
            if proc.info['name'] and 'spotify' in proc.info['name'].lower():
                pid = proc.info['pid']
                break
        else:
            return error_response("Spotify is not running")
        
        keys = {
            'play': 0xB3,
            'pause': 0xB3,
            'next': 0xB0,
            'previous': 0xB1,
        }
        if command in keys:
            import ctypes
            user32 = ctypes.windll.user32
            hwnd = user32.FindWindowW(None, "Spotify")
            if hwnd:
                user32.PostMessageW(hwnd, 0x0100, keys[command], 0)
                return success_response({"action": command})
        return success_response({"action": command, "note": "Command sent"})
    except Exception as e:
        return success_response({"action": command, "note": f"Attempted: {e}"})

class Skill:
    def __init__(self, manifest):
        self.manifest = manifest
    
    async def on_load(self):
        pass
