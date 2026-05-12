"""
assistant/engine.py — Offline AI assistant (Vosk STT + Ollama LLM + pyttsx3 TTS)
"""
import asyncio
import json
import queue
import threading
import httpx
import requests
import pyttsx3
try:
    import pyaudio
    HAS_PYAUDIO = True
except ImportError:
    HAS_PYAUDIO = False
    pyaudio = None

try:
    from vosk import Model, KaldiRecognizer
    HAS_VOSK = True
except ImportError:
    HAS_VOSK = False
    Model = None
    KaldiRecognizer = None

from pathlib import Path
from core.config import VOSK_MODEL_PATH
from core.model_router import get_ollama_url, model_for_role, route_role_for_text
from typing import AsyncGenerator


# ══════════════════════════════════════════════
#  TEXT-TO-SPEECH ENGINE
# ══════════════════════════════════════════════
class TTSEngine:
    def __init__(self):
        self.engine = None
        try:
            self.engine = pyttsx3.init()
            self.engine.setProperty("rate", 185)
            self.engine.setProperty("volume", 0.9)
            voices = self.engine.getProperty("voices")
            for v in voices:
                if "david" in v.name.lower() or "zira" in v.name.lower():
                    self.engine.setProperty("voice", v.id)
                    break
        except Exception as exc:
            self.engine = None
            print(f"[TTS] Disabled: {exc}")

    def speak(self, text: str):
        """Speak text synchronously."""
        if self.engine is None:
            return
        self.engine.say(text)
        self.engine.runAndWait()

    def speak_async(self, text: str):
        """Speak without blocking."""
        t = threading.Thread(target=self.speak, args=(text,), daemon=True)
        t.start()


# ══════════════════════════════════════════════
#  SPEECH-TO-TEXT ENGINE (Vosk — fully offline)
# ══════════════════════════════════════════════
class STTEngine:
    def __init__(self):
        self.model = None
        self.is_listening = False
        self._result_queue = queue.Queue()

    def load_model(self):
        if not Path(VOSK_MODEL_PATH).exists():
            raise FileNotFoundError(
                f"Vosk model not found at {VOSK_MODEL_PATH}.\n"
                "Download from: https://alphacephei.com/vosk/models\n"
                "Recommended: vosk-model-small-en-us-0.15"
            )
        self.model = Model(VOSK_MODEL_PATH)
        print("[STT] Vosk model loaded")

    def listen_once(self, timeout: int = 5) -> str | None:
        """Listen for one utterance and return text."""
        if not self.model or not HAS_PYAUDIO:
            return None

        rec = KaldiRecognizer(self.model, 16000)
        p = pyaudio.PyAudio()
        stream = p.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=16000,
            input=True,
            frames_per_buffer=8192
        )
        stream.start_stream()

        result_text = None
        silent_chunks = 0
        max_silent_chunks = timeout * 4   # ~4 chunks/sec

        try:
            while silent_chunks < max_silent_chunks:
                data = stream.read(4096, exception_on_overflow=False)
                if rec.AcceptWaveform(data):
                    result = json.loads(rec.Result())
                    text = result.get("text", "").strip()
                    if text:
                        result_text = text
                        break
                else:
                    partial = json.loads(rec.PartialResult())
                    if not partial.get("partial", "").strip():
                        silent_chunks += 1
                    else:
                        silent_chunks = 0  # reset on activity
        finally:
            stream.stop_stream()
            stream.close()
            p.terminate()

        return result_text

    def start_continuous(self, callback):
        """Start continuous listening in a background thread, calling callback(text) on each result."""
        if not self.model:
            self.load_model()
        self.is_listening = True

        def _run():
            rec = KaldiRecognizer(self.model, 16000)
            p = pyaudio.PyAudio()
            stream = p.open(format=pyaudio.paInt16, channels=1, rate=16000, input=True, frames_per_buffer=8192)
            stream.start_stream()
            try:
                while self.is_listening:
                    data = stream.read(4096, exception_on_overflow=False)
                    if rec.AcceptWaveform(data):
                        result = json.loads(rec.Result())
                        text = result.get("text", "").strip()
                        if text:
                            callback(text)
            finally:
                stream.stop_stream()
                stream.close()
                p.terminate()

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        return t

    def stop(self):
        self.is_listening = False


# ══════════════════════════════════════════════
#  OLLAMA LLM ENGINE
# ══════════════════════════════════════════════
SYSTEM_PROMPT = """You are JARVIS, a highly intelligent personal AI assistant.
You are helpful, concise, and proactive. You remember context from the conversation.
You can control apps, set reminders, take notes, recognize faces, and analyze the user's daily activities.
Always respond in 1-3 sentences unless the user asks for detail.
When performing actions, confirm what you've done briefly."""

class LLMEngine:
    def __init__(self):
        self.default_model = model_for_role("chat")
        self.base_url = get_ollama_url(self.default_model)
        self.model = self.default_model
        self.conversation_history = []

    def is_available(self) -> bool:
        try:
            r = requests.get(f"{self.base_url}/api/tags", timeout=2)
            return r.status_code == 200
        except Exception:
            return False

    def _select_model(self, user_message: str) -> str:
        role = route_role_for_text(user_message)
        return model_for_role(role)

    async def chat(self, user_message: str, context: str = "") -> str:
        """Send a message and get a response from the local LLM (async)."""
        model = self._select_model(user_message)
        base_url = get_ollama_url(model)
        self.conversation_history.append({
            "role": "user",
            "content": f"{context}\n{user_message}".strip() if context else user_message
        })

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                *self.conversation_history[-20:]   # last 20 messages for context
            ],
            "stream": False
        }

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"{base_url}/api/chat",
                    json=payload
                )
                response.raise_for_status()
                reply = response.json()["message"]["content"]
            self.conversation_history.append({"role": "assistant", "content": reply})
            return reply
        except httpx.ConnectError:
            return "Ollama is offline. Run: ollama serve"
        except Exception as e:
            return f"Model error: {e}"

    def chat_sync(self, user_message: str, context: str = "") -> str:
        """Synchronous wrapper for chat(). Used by non-async callers."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                return asyncio.run_coroutine_threadsafe(self.chat(user_message, context), loop).result()
        except RuntimeError:
            pass
        return asyncio.run(self.chat(user_message, context))

    def chat_stream(self, user_message: str):
        """Generator that yields response tokens as they arrive."""
        model = self._select_model(user_message)
        base_url = get_ollama_url(model)
        self.conversation_history.append({"role": "user", "content": user_message})
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                *self.conversation_history[-20:]
            ],
            "stream": True
        }
        try:
            with requests.post(f"{base_url}/api/chat", json=payload, stream=True, timeout=60) as r:
                for line in r.iter_lines():
                    if line:
                        chunk = json.loads(line)
                        token = chunk.get("message", {}).get("content", "")
                        if token:
                            yield token
                        if chunk.get("done"):
                            break
        except Exception as e:
            yield f"LLM unavailable: {e}"

    def _fallback_response(self, message: str) -> str:
        return "Ollama is offline. Run: ollama serve"

    def clear_history(self):
        self.conversation_history = []


# ══════════════════════════════════════════════
#  INTENT DETECTOR (quick command parsing)
# ══════════════════════════════════════════════
INTENTS = {
    "set_reminder":    ["remind", "reminder", "alarm", "alert me", "set alarm"],
    "create_note":     ["note", "write down", "remember this", "take note"],
    "file_manager":    ["file", "folder", "open folder", "find file"],
    "open_app":        ["open", "launch", "start"],
    "send_whatsapp":   ["whatsapp", "send whatsapp", "message on whatsapp"],
    "send_instagram":  ["instagram", "insta", "dm on insta"],
    "face_recognize":  ["who is", "recognize", "identify face"],
    "play_music":      ["play music", "play song", "music", "shuffle"],
    "daily_summary":   ["summary", "what did i do", "my day", "activity"],
    "screen_share":    ["screen share", "share screen", "mirror"],
    "stop":            ["stop", "cancel", "quit", "exit", "shutdown"],
}

def detect_intent(text: str) -> str | None:
    text_lower = text.lower()
    for intent, keywords in INTENTS.items():
        if any(kw in text_lower for kw in keywords):
            return intent
    return "general_chat"


# ══════════════════════════════════════════════
#  OPEN / LAUNCH COMMAND EXECUTOR
# ══════════════════════════════════════════════
import webbrowser
import subprocess

KNOWN_APPS = {
    "youtube": "https://youtube.com",
    "google": "https://google.com",
    "amazon": "https://amazon.com",
    "whatsapp": "https://web.whatsapp.com",
    "gmail": "https://gmail.com",
    "github": "https://github.com",
}

KNOWN_DESKTOP_APPS = {
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "vscode": "code",
    "explorer": "explorer.exe",
}

def execute_open_command(target: str) -> dict:
    target_lower = target.lower().strip()

    for keyword, url in KNOWN_APPS.items():
        if keyword in target_lower:
            webbrowser.open(url)
            return {
                "action": "opened_browser",
                "target": keyword,
                "url": url,
                "success": True,
                "message": f"Opened {keyword} in browser"
            }

    for keyword, exe in KNOWN_DESKTOP_APPS.items():
        if keyword in target_lower:
            try:
                subprocess.Popen([exe])
                return {
                    "action": "opened_app",
                    "target": keyword,
                    "exe": exe,
                    "success": True,
                    "message": f"Launched {keyword}"
                }
            except Exception as e:
                return {
                    "action": "opened_app",
                    "target": keyword,
                    "success": False,
                    "error": str(e)
                }

    return {
        "action": "unknown",
        "target": target,
        "success": False,
        "message": f"Don't know how to open: {target}"
    }


# ══════════════════════════════════════════════
#  MAIN ASSISTANT (combines everything)
# ══════════════════════════════════════════════
class JarvisAssistant:
    def __init__(self):
        self.tts = TTSEngine()
        self.stt = STTEngine()
        self.llm = LLMEngine()
        self.is_running = False
        self.wake_words = ["jarvis", "hey jarvis", "ok jarvis"]

    def greet(self):
        from datetime import datetime
        hour = datetime.now().hour
        greeting = "Good morning" if hour < 12 else "Good afternoon" if hour < 17 else "Good evening"
        msg = f"{greeting}. All systems are operational. I'm ready to assist you."
        self.tts.speak_async(msg)
        return msg

    async def process_text(self, text: str, user_id: int = None) -> dict:
        """Process a text command and return structured response."""
        import re
        intent = detect_intent(text)
        
        # Execute action if detected
        action_response = None
        if intent == "set_reminder":
            match = re.search(r'(?:remind\s+(?:me|us)\s+(?:to\s+)?|reminder(?:\s+to\s+)?|set\s+(?:a\s+)?(?:reminder|alarm)\s+(?:for\s+)?|alert\s+me\s+(?:to\s+)?)(.+)', text.lower())
            if match:
                what = match.group(1).strip()
                action_response = await self._execute_reminder_action(what)
                intent = "reminder_created"
        
        elif intent == "create_note":
            parts = re.split(r'note|remember', text.lower(), maxsplit=1)
            if len(parts) > 1 and parts[1].strip():
                action_response = await self._execute_note_action(parts[1].strip())
                intent = "note_created"
        
        elif intent == "open_app":
            words = text.lower().split()
            target = ""
            for idx, w in enumerate(words):
                if w in ("open", "launch", "start") and idx + 1 < len(words):
                    target = " ".join(words[idx + 1:])
                    break
            if target:
                action_result = execute_open_command(target)
                action_message = action_result.get("message", "")
                if action_result.get("success"):
                    action_response = f"[ACTION]: {action_message}"
                else:
                    action_response = f"[ACTION FAILED]: {action_message}"
            else:
                action_response = "[ACTION]: Tried to open, but no target specified"
        
        elif intent == "play_music":
            query = urllib.parse.quote(text.replace("play", "").replace("music", "").replace("song", "").strip())
            url = f"https://www.youtube.com/results?search_query={query}" if query else "https://music.youtube.com"
            webbrowser.open(url)
            action_response = f"[ACTION]: Playing music on YouTube"
        
        elif intent == "send_whatsapp":
            webbrowser.open("https://web.whatsapp.com")
            action_response = "[ACTION]: Opened WhatsApp Web"
        
        elif intent == "send_instagram":
            webbrowser.open("https://instagram.com")
            action_response = "[ACTION]: Opened Instagram"
        
        elif intent == "face_recognize":
            action_response = "[ACTION]: Face recognition is available via the /api/faces endpoint"
        
        elif intent == "daily_summary":
            action_response = "[ACTION]: Daily summary feature is available via the dashboard"
        
        elif intent == "file_manager":
            subprocess.Popen(["explorer.exe"])
            action_response = "[ACTION]: Opened File Explorer"
        
        elif intent == "screen_share":
            action_response = "[ACTION]: Screen sharing is not available in the current session"
        
        elif intent == "stop":
            self.is_running = False
            action_response = "[ACTION]: JARVIS voice assistant stopped"
        
        # Get LLM response
        response = await self.llm.chat(text)
        
        # If action was executed, append to response
        if action_response:
            response = f"{response}\n{action_response}"
        
        return {
            "intent": intent,
            "response": response,
            "user_text": text
        }
    
    async def _execute_reminder_action(self, title: str) -> str:
        """Actually create a reminder."""
        import urllib.request, json
        from datetime import datetime, timedelta
        try:
            remind_at = (datetime.now() + timedelta(hours=1)).isoformat()
            data = json.dumps({
                'title': title,
                'remind_at': remind_at,
                'description': 'From JARVIS chat'
            }).encode()
            req = urllib.request.Request(
                'http://localhost:8000/api/reminders',
                data=data,
                headers={'Content-Type': 'application/json'}
            )
            urllib.request.urlopen(req, timeout=5)
            return f"✓ Reminder set: {title}"
        except Exception as e:
            return f"Could not create reminder: {e}"
    
    async def _execute_note_action(self, content: str) -> str:
        """Actually create a note."""
        import urllib.request, json
        try:
            data = json.dumps({
                'title': content[:50],
                'content': content
            }).encode()
            req = urllib.request.Request(
                'http://localhost:8000/api/notes',
                data=data,
                headers={'Content-Type': 'application/json', 'Authorization': 'Bearer dev'}
            )
            urllib.request.urlopen(req, timeout=5)
            return f"✓ Note saved"
        except Exception as e:
            return f"Could not save note: {e}"
    
    def start_voice_loop(self, on_response=None):
        """Start continuous voice assistant loop."""
        self.is_running = True
        print("[JARVIS] Voice assistant started. Say 'Jarvis' to activate.")

        def handle_speech(text: str):
            text_lower = text.lower()
            if any(wake in text_lower for wake in self.wake_words):
                self.tts.speak_async("Yes?")
            elif self.is_running:
                response = self.llm.chat_sync(text)
                self.tts.speak_async(response)
                if on_response:
                    on_response(text, response)

        self.stt.start_continuous(handle_speech)

    def stop(self):
        self.is_running = False
        self.stt.stop()


# Singleton
jarvis = JarvisAssistant()
