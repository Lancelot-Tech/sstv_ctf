#!/usr/bin/env python3
"""
SSTV Pasokon P3 encoder
Japanese format, VIS code 113 — rarely supported outside Japan.

Mode specs:
  Width:  640 px | Height:   496 lines
  Sync:   20 ms @ 1200 Hz
  Porch:  2.08333 ms @ 1500 Hz
  R/G/B:  128.458 ms each (640 px × ~0.200716 ms/px)
  Sep:    1.04167 ms @ 1500 Hz (between channels)
  Total:  ~203 s / ~3.4 min
"""

import sys
import numpy as np
import wave
from PIL import Image

SAMPLE_RATE = 44100

# Pasokon P3 timing (ms)
VIS_CODE   = 113
WIDTH      = 640
HEIGHT     = 496
SYNC_MS    = 20.0
PORCH_MS   = 2.08333
SEP_MS     = 1.04167
CHANNEL_MS = 128.45842        # per R / G / B scan
PIXEL_MS   = CHANNEL_MS / WIDTH   # ~0.200716 ms per pixel per channel


# ── audio primitives ──────────────────────────────────────────────────────────

def _tone(freq: float, duration_ms: float) -> np.ndarray:
    n = int(SAMPLE_RATE * duration_ms / 1000.0)
    t = np.linspace(0, duration_ms / 1000.0, n, endpoint=False)
    return np.sin(2.0 * np.pi * freq * t)


def _channel_audio(pixel_row: np.ndarray) -> np.ndarray:
    """Phase-continuous FM scan for one color channel row (640 pixels)."""
    samples_per_pixel = SAMPLE_RATE * PIXEL_MS / 1000.0
    total = int(samples_per_pixel * WIDTH)

    # Map each sample index to its pixel value → frequency
    idx = np.arange(total)
    px  = np.clip((idx / samples_per_pixel).astype(np.int32), 0, WIDTH - 1)
    freqs = 1500.0 + (2300.0 - 1500.0) * pixel_row[px] / 255.0

    # Phase accumulator (maintains continuity across pixels)
    phase = np.cumsum(2.0 * np.pi * freqs / SAMPLE_RATE)
    return np.sin(phase)


# ── VIS header ────────────────────────────────────────────────────────────────

def _vis_header() -> np.ndarray:
    bits = [(VIS_CODE >> i) & 1 for i in range(7)]
    parity = sum(bits) % 2   # even parity

    parts = [
        _tone(1900, 300),    # leader
        _tone(1200, 10),     # break
        _tone(1900, 300),    # leader
        _tone(1200, 30),     # VIS start bit
    ]
    for b in bits:
        parts.append(_tone(1100 if b else 1300, 30))
    parts.append(_tone(1100 if parity else 1300, 30))  # parity
    parts.append(_tone(1200, 30))                       # VIS stop bit
    return np.concatenate(parts)


# ── main encoder ─────────────────────────────────────────────────────────────

def encode(img_path: str, out_path: str) -> None:
    img = Image.open(img_path).convert("RGB").resize((WIDTH, HEIGHT), Image.LANCZOS)
    px  = np.array(img, dtype=np.uint8)   # (HEIGHT, WIDTH, 3)

    chunks = [_vis_header()]

    for row in range(HEIGHT):
        r, g, b = px[row, :, 0], px[row, :, 1], px[row, :, 2]

        chunks.append(_tone(1200, SYNC_MS))    # line sync
        chunks.append(_tone(1500, PORCH_MS))   # porch
        chunks.append(_channel_audio(r))
        chunks.append(_tone(1500, SEP_MS))     # separator R→G
        chunks.append(_channel_audio(g))
        chunks.append(_tone(1500, SEP_MS))     # separator G→B
        chunks.append(_channel_audio(b))

        if (row + 1) % 100 == 0 or row + 1 == HEIGHT:
            print(f"\r  {row+1}/{HEIGHT} lines", end="", flush=True)

    print()
    audio = np.concatenate(chunks)
    pcm   = np.clip(audio * 32767, -32768, 32767).astype(np.int16)

    with wave.open(out_path, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm.tobytes())

    duration = len(pcm) / SAMPLE_RATE
    print(f"  Saved → {out_path}")
    print(f"  Duration: {duration:.1f} s  ({duration/60:.1f} min)")
    print(f"  Mode: Pasokon P3  |  VIS: {VIS_CODE}  |  {WIDTH}×{HEIGHT}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <input_image> <output.wav>")
        sys.exit(1)
    encode(sys.argv[1], sys.argv[2])
