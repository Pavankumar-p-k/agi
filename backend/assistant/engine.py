from __future__ import annotations

from datetime import datetime

import httpx

from core.config import OLLAMA_MODEL, OLLAMA_URL


class TTSEngine:
    def speak(self, text: str) -> None:
        print(f'[TTS] {text}')

    def speak_async(self, text: str) -> None:
        self.speak(text)


class LLMEngine:
    def __init__(self) -> None:
        self.base_url = OLLAMA_URL
        self.model = OLLAMA_MODEL

    def is_available(self) -> bool:
        try:
            response = httpx.get(f'{self.base_url}/api/tags', timeout=2.0)
            return response.status_code == 200
        except Exception:
            return False

    def chat(self, message: str, context: str = '') -> str:
        if self.is_available():
            try:
                payload = {
                    'model': self.model,
                    'messages': [
                        {'role': 'system', 'content': 'You are JARVIS. Be concise.'},
                        {'role': 'user', 'content': f'{context}\n{message}'.strip()},
                    ],
                    'stream': False,
                }
                response = httpx.post(f'{self.base_url}/api/chat', json=payload, timeout=20.0)
                response.raise_for_status()
                return response.json().get('message', {}).get('content', 'No response from model.')
            except Exception:
                pass

        if 'time' in message.lower():
            return f"Current time is {datetime.now().strftime('%I:%M %p')}"
        return "JARVIS backend is online. Start Ollama for full local LLM responses."


class JarvisAssistant:
    def __init__(self) -> None:
        self.tts = TTSEngine()
        self.llm = LLMEngine()

    async def process_text(self, message: str, user_id: int, context: str = '') -> dict:
        reply = self.llm.chat(message, context=context)
        return {
            'response': reply,
            'intent': 'general_chat',
            'user_id': user_id,
            'timestamp': datetime.utcnow().isoformat(),
        }


jarvis = JarvisAssistant()
