#!/usr/bin/env python
"""
soundtrack.py — deterministic 30s soundtrack for the GSA reel, synthesized
with numpy only (no samples, no network). Writes soundtrack.wav, 44.1kHz stereo.

Recipe (96 BPM, A minor):
  - kick on beats 1 & 3 (sine thump with pitch drop)
  - hats on offbeats (short noise bursts)
  - clap on beats 2 & 4 (noise burst + 180Hz body)
  - sawtooth bassline: Am - Am - F - G
  - triangle pluck melody on eighths, octave-up in the back half
  - white-noise riser into the 20s CTA drop
"""
import numpy as np
import wave

SR = 44100
DURATION = 30.0
N = int(SR * DURATION)
BPM = 96
BEAT = 60.0 / BPM

t_all = np.arange(N) / SR
mixL = np.zeros(N)
mixR = np.zeros(N)


def add(sig, at):
    """Mix a mono signal into the master at time `at` seconds."""
    i0 = int(at * SR)
    if i0 >= N:
        return
    seg = sig[: N - i0]
    mixL[i0:i0 + len(seg)] += seg
    mixR[i0:i0 + len(seg)] += seg


def add_stereo(sigL, sigR, at):
    i0 = int(at * SR)
    if i0 >= N:
        return
    segL = sigL[: N - i0]
    segR = sigR[: N - i0]
    mixL[i0:i0 + len(segL)] += segL
    mixR[i0:i0 + len(segR)] += segR


def env(n, a, d, sustain=0.0):
    tt = np.arange(n) / SR
    e = np.minimum(1, tt / max(a, 1e-4)) * np.exp(-np.maximum(tt - a, 0) / d)
    return e * (1 - sustain * np.clip(tt / (n / SR), 0, 1))


# ---------------------------------------------------------------- kick
def kick(v=0.55):
    n = int(0.30 * SR)
    tt = np.arange(n) / SR
    f = 120 * np.exp(-tt * 22) + 42
    ph = 2 * np.pi * np.cumsum(f) / SR
    return v * np.sin(ph) * env(n, 0.002, 0.10)


# ---------------------------------------------------------------- hat
def hat(v=0.10):
    n = int(0.06 * SR)
    rng = np.random.default_rng(4844)  # deterministic
    noise = rng.standard_normal(n)
    # crude one-pole highpass: subtract smoothed version
    smooth = np.convolve(noise, np.ones(6) / 6, mode="same")
    hp = noise - smooth
    return v * hp * env(n, 0.001, 0.018)


# ---------------------------------------------------------------- clap
def clap(v=0.22):
    n = int(0.22 * SR)
    rng = np.random.default_rng(4845)
    noise = rng.standard_normal(n)
    smooth = np.convolve(noise, np.ones(4) / 4, mode="same")
    band = noise - 0.5 * smooth
    body = 0.4 * np.sin(2 * np.pi * 185 * np.arange(n) / SR) * np.exp(-np.arange(n) / SR / 0.05)
    return v * (band + body) * env(n, 0.001, 0.05)


# ---------------------------------------------------------------- bass
def bass(freq, dur, v=0.16):
    n = int(dur * SR)
    tt = np.arange(n) / SR
    saw = 2 * ((tt * freq) % 1) - 1
    sub = np.sin(2 * np.pi * freq * 0.5 * tt)
    return v * (0.7 * saw + 0.6 * sub) * env(n, 0.008, dur * 0.7)


# ---------------------------------------------------------------- pluck
def pluck(freq, v=0.10):
    n = int(0.35 * SR)
    tt = np.arange(n) / SR
    tri = 2 * np.abs(2 * ((tt * freq) % 1) - 1) - 1
    return v * tri * env(n, 0.004, 0.10)


# ---------------------------------------------------------------- riser
def riser(start, dur=2.0, v=0.12):
    n = int(dur * SR)
    rng = np.random.default_rng(4846)
    noise = rng.standard_normal(n)
    tt = np.arange(n) / SR
    sweep_f = 300 + 2400 * (tt / dur) ** 2
    # ring-modulate noise with a rising sine for a "sweep" feel
    sig = noise * (0.4 + 0.6 * np.sin(2 * np.pi * np.cumsum(sweep_f) / SR))
    e = (tt / dur) ** 2.2
    add_stereo(v * sig * e, v * sig * e * 0.9, start)


# ================================================================ sequence
# chord roots per bar (Am, Am, F, G)
ROOTS = [110.0, 110.0, 87.31, 98.0]
MELODY = [0, 2, 4, 2, 5, 4, 2, 0, 1, 3, 5, 3, 6, 5, 3, 1]
SCALE = [220.0, 261.63, 293.66, 329.63, 392.0, 440.0, 523.25]

bars = int(DURATION / (BEAT * 4))
for bar in range(bars):
    t_bar = bar * BEAT * 4
    root = ROOTS[bar % 4]

    for beat in range(4):
        tb = t_bar + beat * BEAT
        if beat % 2 == 0:
            add(kick(), tb)
        if beat % 2 == 1:
            add(hat(), tb + BEAT / 2)
            add(hat(0.05), tb)
        if beat % 4 == 2:
            add(clap(), tb)
        # bass on eighths
        add(bass(root, BEAT * 0.9), tb)
        add(bass(root * 1.0, BEAT * 0.45), tb + BEAT / 2)

        # melody plucks
        for half in (0, 1):
            idx = (bar * 8 + beat * 2 + half) % len(MELODY)
            f = SCALE[MELODY[idx]]
            if bar >= bars // 2:
                f *= 2  # octave up in the back half
            pan = 0.5 + 0.3 * np.sin(idx * 1.7)
            sig = pluck(f, 0.09)
            add_stereo(sig * (1 - pan), sig * pan, tb + half * BEAT / 2)

# riser into the CTA at t=20s
riser(18.0, 2.0)

# final kick + shimmer accent on the last beat
add(kick(0.7), DURATION - BEAT)

# ---------------------------------------------------------------- master
mix = np.stack([mixL, mixR], axis=1)
# soft clip
mix = np.tanh(mix * 1.4) / 1.4
peak = np.max(np.abs(mix)) or 1.0
mix = mix / peak * 0.92
pcm = (mix * 32767).astype(np.int16)

with wave.open("soundtrack.wav", "w") as w:
    w.setnchannels(2)
    w.setsampwidth(2)
    w.setframerate(SR)
    w.writeframes(pcm.tobytes())

print(f"soundtrack.wav written: {DURATION}s, {SR}Hz, stereo, peak={peak:.3f}")
