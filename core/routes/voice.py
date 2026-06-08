import asyncio
import logging

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, UploadFile, File
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import verify_token
from core.database import get_db, User

router = APIRouter(tags=["voice"])


@router.post("/stt")
async def speech_to_text(file: UploadFile = File(...), user: User = Depends(verify_token)):
    from assistant.stt import get_stt
    audio_data = await file.read()
    text = await get_stt().transcribe(audio_data)
    if not text:
        raise HTTPException(500, "Transcription failed")
    return {"transcript": text}


@router.post("/stt/local")
async def speech_to_text_local(file: UploadFile = File(...), user: User = Depends(verify_token)):
    from assistant.stt import get_stt
    audio_data = await file.read()
    text = await get_stt().transcribe(audio_data)
    if not text:
        raise HTTPException(500, "Transcription failed")
    return {"transcript": text}


@router.post("/stt/base64")
async def speech_to_text_base64(req: dict, user: User = Depends(verify_token)):
    """STT accepting JSON with base64 audio."""
    if "audio" not in req:
        raise HTTPException(400, "Missing 'audio' field (base64 WAV)")
    from assistant.stt import get_stt
    import base64
    audio_data = base64.b64decode(req["audio"])
    text = await get_stt().transcribe(audio_data)
    return {"transcript": text or ""}


@router.post("/tts")
async def text_to_speech(req: dict, user: User = Depends(verify_token)):
    from assistant.tts import get_tts
    text = req.get("text", "")
    if not text:
        raise HTTPException(400, "Text is required")
    loop = asyncio.get_running_loop()
    audio_bytes = await loop.run_in_executor(None, get_tts().synthesize, text)
    if not audio_bytes:
        raise HTTPException(500, "TTS generation failed")
    return Response(content=audio_bytes, media_type="audio/wav")


@router.post("/api/tts/chatterbox")
async def tts_chatterbox(req: dict):
    from assistant.edge_tts_module import EdgeTTS
    text = req.get("text", "")
    if not text:
        raise HTTPException(400, "Text is required")
    tts = EdgeTTS(voice="en-US-ChristopherNeural")
    loop = asyncio.get_event_loop()
    audio_bytes = await tts.synthesize(text)
    if not audio_bytes:
        raise HTTPException(500, "TTS generation failed")
    return Response(content=audio_bytes, media_type="audio/mpeg")


@router.post("/voice/test")
async def voice_test():
    from assistant.stt import get_stt
    from assistant.tts import get_tts
    import sounddevice as sd, numpy as np, io, soundfile as sf
    sr = 16000
    loop = asyncio.get_event_loop()

    def _run():
        print("[VoiceTest] Recording 3s...")
        recording = sd.rec(int(sr * 3), samplerate=sr, channels=1, dtype="float32")
        sd.wait()
        buf = io.BytesIO()
        sf.write(buf, recording, sr, format="WAV", subtype="PCM_16")
        audio_bytes = buf.getvalue()
        print(f"[VoiceTest] Recorded {len(audio_bytes)} bytes")
        text = get_stt().transcribe(audio_bytes)
        print(f"[VoiceTest] STT: {text}")
        response = f'I heard you say: {text}' if text else 'Sorry, I did not catch that.'
        tts_bytes = get_tts().synthesize(response)
        print(f"[VoiceTest] TTS: {len(tts_bytes)} bytes")
        data, play_sr = sf.read(io.BytesIO(tts_bytes))
        sd.play(data, play_sr)
        sd.wait()
        print("[VoiceTest] Playback done")
        return {"transcript": text, "response": response}

    return await loop.run_in_executor(None, _run)


@router.websocket("/tts/stream")
async def tts_stream_websocket(ws: WebSocket):
    from assistant.tts import get_tts
    await ws.accept()
    loop = asyncio.get_running_loop()
    try:
        while True:
            data = await ws.receive_json()
            text = data.get("text", "")
            if text:
                audio_bytes = await loop.run_in_executor(None, get_tts().synthesize, text)
                await ws.send_bytes(audio_bytes)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"[TTS Stream] Error: {e}")
        try:
            await ws.close()
        except Exception as _e:
            logger.debug("voice ws close failed: %s", _e)


@router.websocket("/voice")
async def voice_websocket(ws: WebSocket):
    """WebSocket voice endpoint: receives raw audio, returns WAV audio.
    Flow: mic audio -> STT -> llm_router -> TTS -> speaker audio
    """
    from assistant.voice_pipeline import get_pipeline
    await ws.accept()
    pipeline = get_pipeline()
    try:
        while True:
            audio_bytes = await ws.receive_bytes()
            if not audio_bytes or len(audio_bytes) < 1024:
                continue
            audio_out = await pipeline.process_audio(audio_bytes)
            if audio_out:
                await ws.send_bytes(audio_out)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"[Voice WS] Error: {e}")
        await ws.close()
