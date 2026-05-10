"""
assistant/engine.py — Offline AI assistant (Vosk STT + Ollama LLM + pyttsx3 TTS)
"""
import asyncio
import json
import queue
import threading
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

    def chat(self, user_message: str, context: str = "") -> str:
        """Send a message and get a response from the local LLM."""
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
            response = requests.post(
                f"{base_url}/api/chat",
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            reply = response.json()["message"]["content"]
            self.conversation_history.append({"role": "assistant", "content": reply})
            return reply
        except Exception as e:
            # Fallback responses when LLM is unavailable
            return self._fallback_response(user_message)

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
        """Rule-based fallback when Ollama isn't running - with action execution!"""
        msg = message.lower()
        
        # Time
        if any(w in msg for w in ["time", "clock"]):
            from datetime import datetime
            return f"The current time is {datetime.now().strftime('%I:%M %p')}."
        
        # Greeting
        if any(w in msg for w in ["hello", "hi", "hey"]):
            return "Hello! I'm JARVIS. How can I assist you today?"
        
        # Reminder - CREATE IT!
        if any(w in msg for w in ["remind", "reminder", "alert"]):
            import re
            # Try to extract reminder text
            match = re.search(r'remind (.+) (to|at|on|in) (.+)', msg)
            if match:
                title = match.group(1).strip()
                return self._create_reminder_fallback(title)
            # Just "remind me to X"
            match2 = re.search(r'remind me to (.+)', msg)
            if match2:
                title = match2.group(1).strip()
                return self._create_reminder_fallback(title)
            return "I'll set a reminder. What should I remind you about?"
        
        # Note - CREATE IT!
        if any(w in msg for w in ["note", "write down", "remember this", "take note"]):
            import re
            match = re.search(r'(note|remember) (.+)', msg)
            if match:
                content = match.group(2).strip()
                return self._create_note_fallback(content)
            return "What would you like me to note down?"
        
        # Open apps
        if any(w in msg for w in ["open", "launch", "start"]):
            app = msg.replace("open", "").replace("launch", "").replace("start", "").strip()
            if "youtube" in app:
                return self._open_url_fallback("https://youtube.com")
            if "amazon" in app:
                return self._open_url_fallback("https://amazon.com")
            if "google" in app:
                return self._open_url_fallback("https://google.com")
            if "whatsapp" in app:
                return self._open_url_fallback("https://web.whatsapp.com")
            return f"I'll open {app} for you."
        
        # Weather
        if any(w in msg for w in ["weather"]):
            return "I need an internet connection to check the weather. Please connect Ollama for full AI features."
        
        return "I'm currently running in limited mode. Please start Ollama for full AI capabilities."

    def _create_reminder_fallback(self, title: str) -> str:
        """Create reminder via API."""
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
            return f"I understood: '{title}' - but couldn't create reminder right now."

    def _create_note_fallback(self, content: str) -> str:
        """Create note via API."""
        import urllib.request, json
        try:
            data = json.dumps({
                'title': content[:50],
                'content': content
            }).encode()
            req = urllib.request.Request(
                'http://localhost:8000/api/notes',
                data=data,
                headers={'Content-Type': 'application/json'}
            )
            urllib.request.urlopen(req, timeout=5)
            return f"✓ Note saved: {content[:30]}..."
        except Exception as e:
            return f"I understood: '{content[:30]}' - but couldn't save note right now."

    def _open_url_fallback(self, url: str) -> str:
        """Open URL in browser."""
        import webbrowser
        try:
            webbrowser.open(url)
            return f"✓ Opened {url}"
        except:
            return f"I'll open {url} for you."

    def clear_history(self):
        self.conversation_history = []


# ══════════════════════════════════════════════
#  INTENT DETECTOR (quick command parsing)
# ══════════════════════════════════════════════
INTENTS = {
    "set_reminder":    ["remind", "reminder", "alarm", "alert me", "set alarm"],
    "create_note":     ["note", "write down", "remember this", "take note"],
    "open_app":        ["open", "launch", "start"],
    "send_whatsapp":   ["whatsapp", "send whatsapp", "message on whatsapp"],
    "send_instagram":  ["instagram", "insta", "dm on insta"],
    "face_recognize":  ["who is", "recognize", "identify face"],
    "play_music":      ["play music", "play song", "music", "shuffle"],
    "daily_summary":   ["summary", "what did i do", "my day", "activity"],
    "file_manager":    ["file", "folder", "open folder", "find file"],
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
            # Extract what to remind
            match = re.search(r'remind me? (.+)', text.lower())
            if match:
                what = match.group(1).strip()
                action_response = await self._execute_reminder_action(what)
                intent = "reminder_created"
        
        elif intent == "create_note":
            # Extract note content
            parts = re.split(r'note|remember', text.lower(), maxsplit=1)
            if len(parts) > 1 and parts[1].strip():
                action_response = await self._execute_note_action(parts[1].strip())
                intent = "note_created"
        
        elif intent == "open_app":
            if "youtube" in text.lower():
                action_response = self._open_url_action("https://youtube.com")
            elif "amazon" in text.lower():
                action_response = self._open_url_action("https://amazon.com")
            else:
                action_response = f"I'll try to open that."
        
        # Get LLM response (or fallback)
        response = self.llm.chat(text)
        
        # If action was executed, prepend to response
        if action_response:
            response = f"{action_response}\n\n{response}"
        
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
    
    def _open_url_action(self, url: str) -> str:
        """Open URL in browser."""
        import webbrowser
        try:
            webbrowser.open(url)
            return f"✓ Opened {url}"
        except:
            return f"I'll open {url}."

    def start_voice_loop(self, on_response=None):
        """Start continuous voice assistant loop."""
        self.is_running = True
        print("[JARVIS] Voice assistant started. Say 'Jarvis' to activate.")

        def handle_speech(text: str):
            text_lower = text.lower()
            if any(wake in text_lower for wake in self.wake_words):
                self.tts.speak_async("Yes?")
            elif self.is_running:
                response = self.llm.chat(text)
                self.tts.speak_async(response)
                if on_response:
                    on_response(text, response)

        self.stt.start_continuous(handle_speech)

    def stop(self):
        self.is_running = False
        self.stt.stop()


# Singleton
jarvis = JarvisAssistant()
