import asyncio
import edge_tts
import io

_voice_cache = {}

class EdgeTTS:
    def __init__(self, voice: str = "en-US-AriaNeural"):
        self.voice = voice

    async def synthesize(self, text: str) -> bytes:
        communicate = edge_tts.Communicate(text, self.voice)
        audio_chunks = []
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_chunks.append(chunk["data"])
        if not audio_chunks:
            return b""
        return b"".join(audio_chunks)

    def synthesize_sync(self, text: str) -> bytes:
        return asyncio.run(self.synthesize(text))
