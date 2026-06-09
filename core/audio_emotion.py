# Copyright (c) 2024-2026 JARVIS Project
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
core/audio_emotion.py
Phase 10.2 — Audio Emotion Detector

Detects emotion/urgency from raw audio BEFORE STT conversion.
Runs in the voice pipeline between audio capture and Faster-Whisper STT.

Pipeline position:
    audio_capture → [AudioEmotionDetector] → STT → LLM (with emotion context)

How it works:
    1. Extract acoustic features: MFCCs, energy, pitch, speech rate, ZCR
    2. Rule-based classifier maps feature patterns to emotion labels
    3. Emotion + urgency injected into LLM context → adapts tone/priority

Design decisions:
    - librosa used for feature extraction (already common in audio stacks)
    - Rule-based classifier (no separate ML model needed — no VRAM)
    - All processing in run_in_executor (librosa.load blocks the loop)
    - Graceful ImportError fallback → returns NEUTRAL if librosa missing
    - AudioContext.emotion informs: system prompt selection, queue priority,
      TTS tone, response length limits

Cross-checks against your stack:
    - Injected into voice pipeline via lifespan.py (same pattern as Phase 9)
    - emotion → context dict → fed into brain.reason() as "user_emotion" key
    - Urgent emotion overrides queue priority in voice handler
    - Compatible with your Faster-Whisper STT (runs before STT, on same audio file)

Dependencies:
    pip install librosa soundfile   (librosa pulls numpy/scipy automatically)
    pip install speechbrain         (optional — better accuracy, heavier)
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Emotion taxonomy
# ─────────────────────────────────────────────────────────────────────────────

class Emotion(str, Enum):
    CALM      = "calm"
    URGENT    = "urgent"
    FRUSTRATED= "frustrated"
    EXCITED   = "excited"
    NEUTRAL   = "neutral"
    SAD       = "sad"

# Maps emotion → system prompt modifier injected into LLM context
EMOTION_PROMPT_HINTS: dict[Emotion, str] = {
    Emotion.URGENT:     "The user sounds urgent. Be concise and action-oriented. Prioritize this request.",
    Emotion.FRUSTRATED: "The user sounds frustrated. Be patient, clear, and avoid jargon. Acknowledge the difficulty.",
    Emotion.EXCITED:    "The user sounds excited. Match their energy. Be enthusiastic and forward-looking.",
    Emotion.SAD:        "The user sounds subdued. Be gentle, supportive, and thorough.",
    Emotion.CALM:       "The user sounds calm. Normal response tone.",
    Emotion.NEUTRAL:    "",   # no modification
}


# ─────────────────────────────────────────────────────────────────────────────
# Result dataclass
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class AudioContext:
    emotion:      Emotion       # primary detected emotion
    confidence:   float         # 0.0–1.0
    speech_rate:  float         # syllables/sec estimate
    energy_level: float         # RMS energy (normalized 0.0–1.0)
    pitch_mean:   float         # mean F0 in Hz (0 = unvoiced)
    duration_sec: float         # audio clip duration

    @property
    def is_urgent(self) -> bool:
        return self.emotion == Emotion.URGENT and self.confidence > 0.6

    @property
    def prompt_hint(self) -> str:
        return EMOTION_PROMPT_HINTS.get(self.emotion, "")

    def as_context_dict(self) -> dict:
        """Inject into brain.reason() context dict."""
        d = {
            "user_emotion":   self.emotion.value,
            "emotion_confidence": round(self.confidence, 2),
            "speech_energy":  round(self.energy_level, 2),
        }
        if self.prompt_hint:
            d["emotion_guidance"] = self.prompt_hint
        return d

    @classmethod
    def neutral(cls) -> AudioContext:
        """Fallback when analysis unavailable."""
        return cls(
            emotion      = Emotion.NEUTRAL,
            confidence   = 0.0,
            speech_rate  = 0.0,
            energy_level = 0.0,
            pitch_mean   = 0.0,
            duration_sec = 0.0,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Feature extractor (blocking — always run in executor)
# ─────────────────────────────────────────────────────────────────────────────

class AudioFeatureExtractor:
    """
    Extracts acoustic features from audio file using librosa.
    All methods are synchronous — call via run_in_executor.
    """

    def extract(self, audio_path: str) -> dict:
        """
        Returns feature dict:
            mfcc_mean, mfcc_std, energy_rms, pitch_mean,
            zcr_mean, speech_rate_est, duration
        """
        try:
            import librosa
            import numpy as np
        except ImportError:
            raise ImportError(
                "librosa not installed. Run: pip install librosa soundfile"
            )

        # Load audio (mono, 22050 Hz)
        y, sr = librosa.load(audio_path, sr=22050, mono=True)
        duration = librosa.get_duration(y=y, sr=sr)

        # MFCCs — 13 coefficients, captures timbre and articulation
        mfccs = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
        mfcc_mean = float(np.mean(mfccs))
        mfcc_std  = float(np.std(mfccs))

        # RMS energy — loudness proxy
        rms = librosa.feature.rms(y=y)[0]
        energy_rms = float(np.mean(rms))
        # Normalize to 0–1 against typical speech range
        energy_normalized = min(1.0, energy_rms / 0.1)

        # Zero-crossing rate — correlates with speech vs silence
        zcr = librosa.feature.zero_crossing_rate(y)[0]
        zcr_mean = float(np.mean(zcr))

        # Pitch (F0) estimation via pyin
        try:
            f0, voiced_flag, _ = librosa.pyin(
                y, fmin=librosa.note_to_hz("C2"),
                fmax=librosa.note_to_hz("C7")
            )
            pitch_mean = float(np.nanmean(f0[voiced_flag])) if any(voiced_flag) else 0.0
        except Exception as e:
            logger.exception("[AUDIO_EMOTION] Pitch estimation failed: %s", e)
            pitch_mean = 0.0

        # Speech rate estimate: onsets per second ≈ syllable rate
        onset_frames = librosa.onset.onset_detect(y=y, sr=sr)
        speech_rate  = len(onset_frames) / max(duration, 0.1)

        return {
            "mfcc_mean":        mfcc_mean,
            "mfcc_std":         mfcc_std,
            "energy_rms":       energy_rms,
            "energy_normalized":energy_normalized,
            "zcr_mean":         zcr_mean,
            "pitch_mean":       pitch_mean,
            "speech_rate":      speech_rate,
            "duration":         duration,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Rule-based classifier
# ─────────────────────────────────────────────────────────────────────────────

class EmotionClassifier:
    """
    Maps acoustic features to emotion labels via interpretable rules.
    No ML model needed — no VRAM, no training, instant startup.

    Rules derived from speech emotion research:
        Urgent:     high energy + fast speech rate
        Excited:    high energy + high pitch + fast speech
        Frustrated: high energy + variable pitch (high std) + fast speech
        Sad:        low energy + slow speech + low pitch
        Calm:       medium energy + medium speech rate + smooth pitch
    """

    def classify(self, features: dict) -> tuple[Emotion, float]:
        """Returns (emotion, confidence 0.0–1.0)."""

        energy  = features["energy_normalized"]   # 0–1
        rate    = features["speech_rate"]          # onsets/sec
        pitch   = features["pitch_mean"]           # Hz
        mfcc_std= features["mfcc_std"]             # variability

        # Score each emotion against feature patterns
        scores: dict[Emotion, float] = {}

        # URGENT: high energy, fast rate
        scores[Emotion.URGENT] = (
            self._score(energy, 0.7, 1.0) * 0.5 +
            self._score(rate,   8.0, 20.0) * 0.5
        )

        # EXCITED: high energy, high pitch, fast rate
        scores[Emotion.EXCITED] = (
            self._score(energy, 0.6, 1.0)  * 0.35 +
            self._score(pitch,  200, 400)   * 0.35 +
            self._score(rate,   7.0, 18.0)  * 0.30
        )

        # FRUSTRATED: high energy, high MFCC variability, fast rate
        scores[Emotion.FRUSTRATED] = (
            self._score(energy,   0.65, 1.0)  * 0.4 +
            self._score(mfcc_std, 30.0, 80.0) * 0.3 +
            self._score(rate,     7.0,  18.0) * 0.3
        )

        # SAD: low energy, slow rate, low pitch
        scores[Emotion.SAD] = (
            self._score(energy, 0.0, 0.25) * 0.4 +
            self._score(rate,   0.0,  4.0) * 0.4 +
            self._score(pitch,  80,   160) * 0.2
        )

        # CALM: medium energy + medium rate
        scores[Emotion.CALM] = (
            self._score(energy, 0.2, 0.55) * 0.5 +
            self._score(rate,   3.0,  7.0) * 0.5
        )

        # NEUTRAL fallback
        scores[Emotion.NEUTRAL] = 0.3

        # Pick highest-scoring emotion
        best       = max(scores, key=lambda e: scores[e])
        confidence = scores[best]

        # Require minimum confidence — fall back to NEUTRAL
        if confidence < 0.35:
            return Emotion.NEUTRAL, confidence

        return best, min(1.0, confidence)

    @staticmethod
    def _score(value: float, low: float, high: float) -> float:
        """
        Returns 0–1 score for how well `value` falls within [low, high].
        Sigmoid-shaped: full credit inside range, decays outside.
        """
        if low <= value <= high:
            # Normalize within range
            return 0.5 + 0.5 * (value - low) / max(high - low, 1e-6)
        elif value < low:
            gap = low - value
            return max(0.0, 0.5 - gap / max(low, 1e-6))
        else:
            gap = value - high
            return max(0.0, 0.5 - gap / max(high, 1e-6))


# ─────────────────────────────────────────────────────────────────────────────
# AudioEmotionDetector — main class
# ─────────────────────────────────────────────────────────────────────────────

class AudioEmotionDetector:
    """
    Async wrapper. Call before STT in your voice pipeline.

    Usage in voice pipeline:
        audio_ctx = await emotion_detector.analyze(audio_path)
        text      = await stt.transcribe(audio_path)
        context   = {**audio_ctx.as_context_dict(), "transcript": text}
        result    = await brain.reason(text, context)

    If librosa not installed → returns AudioContext.neutral() silently.
    Never raises — voice pipeline must never break due to emotion detection.
    """

    def __init__(self):
        self._extractor  = AudioFeatureExtractor()
        self._classifier = EmotionClassifier()
        self._available  = None   # lazy-check for librosa

    async def analyze(self, audio_path: str) -> AudioContext:
        """
        Main async entry point.
        Runs blocking librosa analysis in executor.
        Returns AudioContext.neutral() on any failure.
        """
        if not await self._is_available():
            return AudioContext.neutral()

        try:
            loop     = asyncio.get_event_loop()
            features = await loop.run_in_executor(
                None, self._extractor.extract, audio_path
            )
            emotion, confidence = self._classifier.classify(features)

            return AudioContext(
                emotion      = emotion,
                confidence   = confidence,
                speech_rate  = features["speech_rate"],
                energy_level = features["energy_normalized"],
                pitch_mean   = features["pitch_mean"],
                duration_sec = features["duration"],
            )

        except Exception as e:
            logger.debug("AudioEmotionDetector: analysis failed — %s", e)
            return AudioContext.neutral()

    async def _is_available(self) -> bool:
        if self._available is None:
            loop = asyncio.get_event_loop()
            self._available = await loop.run_in_executor(
                None, self._check_librosa
            )
        return self._available

    @staticmethod
    def _check_librosa() -> bool:
        try:
            import librosa  # noqa: F401
            return True
        except ImportError:
            logger.info(
                "AudioEmotionDetector: librosa not installed — running in neutral mode. "
                "Install with: pip install librosa soundfile"
            )
            return False


# ─────────────────────────────────────────────────────────────────────────────
# Singleton
# ─────────────────────────────────────────────────────────────────────────────
emotion_detector = AudioEmotionDetector()
