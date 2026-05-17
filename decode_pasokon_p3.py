#!/usr/bin/env python3
"""
SSTV Pasokon P3 decoder
Input:  WAV file (44100 Hz, 16-bit PCM, mono)
Output: PNG image (640×496)

Pipeline:
  1. Bandpass filter (1100–2400 Hz)
  2. Instantaneous frequency via Hilbert transform
  3. Locate VIS header (leader tones at 1900 Hz → VIS bits at 1100/1300 Hz)
  4. For each line: find sync pulse (1200 Hz / 20 ms), then decode R/G/B channels
"""

import sys
import numpy as np
import wave
from PIL import Image
from scipy.signal import hilbert, butter, sosfilt

# ── Pasokon P3 constants ──────────────────────────────────────────────────────
SAMPLE_RATE = 44100
VIS_CODE    = 113
WIDTH       = 640
HEIGHT      = 496
SYNC_MS     = 20.0
PORCH_MS    = 2.08333
SEP_MS      = 1.04167
CHANNEL_MS  = 128.45842
PIXEL_MS    = CHANNEL_MS / WIDTH   # ~0.200716 ms

LINE_MS = SYNC_MS + PORCH_MS + 3 * CHANNEL_MS + 2 * SEP_MS  # ~409.5 ms

FREQ_SYNC  = 1200.0
FREQ_BLACK = 1500.0
FREQ_WHITE = 2300.0
FREQ_LEAD  = 1900.0


def ms(t):
    return int(SAMPLE_RATE * t / 1000.0)


# ── I/O ───────────────────────────────────────────────────────────────────────

def load_wav(path: str) -> np.ndarray:
    with wave.open(path, "r") as wf:
        n_ch   = wf.getnchannels()
        width  = wf.getsampwidth()
        sr     = wf.getframerate()
        frames = wf.readframes(wf.getnframes())

    dtype = np.int16 if width == 2 else np.int8
    data  = np.frombuffer(frames, dtype=dtype).astype(np.float32)

    if n_ch == 2:           # stereo → take left channel
        data = data[::2]
    data /= np.iinfo(dtype).max

    if sr != SAMPLE_RATE:
        print(f"  Warning: sample rate is {sr} Hz (expected {SAMPLE_RATE}), "
              "results may be inaccurate.")
    return data


# ── DSP ───────────────────────────────────────────────────────────────────────

def bandpass(signal: np.ndarray, lo=1050, hi=2450) -> np.ndarray:
    sos = butter(5, [lo, hi], btype="band", fs=SAMPLE_RATE, output="sos")
    return sosfilt(sos, signal)


def inst_freq(signal: np.ndarray) -> np.ndarray:
    """
    Instantaneous frequency from the analytic signal (full-signal Hilbert).
    A single FFT over the whole file avoids chunk-boundary artifacts.
    Memory: ~16 bytes/sample (~150 MB for a 3.4-min file at 44 kHz).
    """
    analytic = hilbert(signal)
    phase    = np.unwrap(np.angle(analytic))
    freq     = np.diff(phase) * SAMPLE_RATE / (2 * np.pi)
    return np.append(freq, freq[-1]).astype(np.float32)


def smooth(freq: np.ndarray, window_ms=5) -> np.ndarray:
    w = ms(window_ms)
    return np.convolve(freq, np.ones(w) / w, mode="same")


# ── VIS header detection ──────────────────────────────────────────────────────

def find_vis_end(freq: np.ndarray) -> int | None:
    """
    Locate end of VIS header.
    Leader tone: ≥200 ms at ~1900 Hz
    VIS header total from leader start: ~910 ms
    Returns sample index just after the VIS stop bit.
    """
    sm = smooth(freq, window_ms=10)
    is_leader = ((sm > 1820) & (sm < 1980)).astype(np.float32)

    min_run = ms(200)
    kernel  = np.ones(min_run, dtype=np.float32)
    runs    = np.convolve(is_leader, kernel, mode="valid")

    hits = np.where(runs >= min_run * 0.70)[0]
    if len(hits) == 0:
        return None

    leader_start = int(hits[0])
    return leader_start + ms(910)    # leader + break + leader + VIS bits


def read_vis_bits(freq: np.ndarray, vis_start: int) -> int:
    """
    Read the 8-bit VIS code (7 data + parity) from vis_start.
    vis_start should point to the first data bit (after VIS start bit).
    Returns decoded VIS integer.
    """
    bit_ms = 30
    val = 0
    for i in range(7):
        s = vis_start + ms(i * bit_ms)
        e = s + ms(bit_ms)
        f = np.mean(freq[s:e])
        bit = 1 if f < 1200 else 0   # 1100 Hz = 1, 1300 Hz = 0
        val |= (bit << i)
    return val


# ── Sync detection ────────────────────────────────────────────────────────────

def find_sync_near(freq: np.ndarray, nominal: int, tol_ms=35) -> int:
    """
    Find a sync pulse (1200 Hz for ≥50% of SYNC_MS) within ±tol_ms of nominal.
    Returns start sample of sync, or nominal on failure.
    """
    half   = ms(tol_ms)
    s      = max(0, nominal - half)
    e      = min(len(freq), nominal + half + ms(SYNC_MS))
    region = freq[s:e]

    is_sync = ((region > 1050) & (region < 1350)).astype(np.float32)
    min_run = ms(SYNC_MS * 0.5)
    kernel  = np.ones(int(min_run), dtype=np.float32)
    runs    = np.convolve(is_sync, kernel, mode="valid")

    hits = np.where(runs >= min_run * 0.75)[0]
    if len(hits) == 0:
        return nominal          # fallback: trust nominal timing

    return s + int(hits[0])


# ── Pixel decoding ────────────────────────────────────────────────────────────

def decode_pixels(freq: np.ndarray, start: int, n: int = WIDTH) -> np.ndarray:
    """
    Decode n pixels from freq[start:].
    Per-pixel median over the central 60 % of each pixel window — avoids
    boundary ringing from the Hilbert transform at frequency step changes.
    """
    spp   = SAMPLE_RATE * PIXEL_MS / 1000.0        # samples per pixel (float)
    ispp  = int(spp)                                # integer samples per pixel
    trim  = max(1, int(ispp * 0.20))               # trim 20 % from each edge

    total = int(spp * n)
    end   = min(start + total, len(freq))
    chunk = freq[start:end]
    if len(chunk) < total:
        chunk = np.pad(chunk, (0, total - len(chunk)), constant_values=FREQ_BLACK)

    pixels = np.empty(n, dtype=np.float32)
    for i in range(n):
        s = int(i * spp) + trim
        e = int((i + 1) * spp) - trim
        if s >= e:          # fallback for very short windows
            s = int(i * spp)
            e = s + max(1, ispp)
        pixels[i] = np.median(chunk[s:e])

    values = (pixels - FREQ_BLACK) / (FREQ_WHITE - FREQ_BLACK) * 255.0
    return np.clip(values, 0, 255).astype(np.uint8)


# ── Main decoder ──────────────────────────────────────────────────────────────

def decode(wav_path: str, out_path: str) -> None:
    print(f"Loading  {wav_path} …")
    signal = load_wav(wav_path)
    dur = len(signal) / SAMPLE_RATE
    print(f"  Duration: {dur:.1f} s  ({dur/60:.1f} min)")

    print("Bandpass filtering (1050–2450 Hz) …")
    filtered = bandpass(signal)

    print("Instantaneous frequency (Hilbert) …")
    freq = inst_freq(filtered)

    print("Locating VIS header …")
    vis_end = find_vis_end(freq)
    if vis_end is None:
        print("  VIS header not found — trying without VIS detection.")
        vis_end = 0
    else:
        # Sanity-check: first data bit = vis_end - (7 data + parity + stop) × 30 ms
        detected_vis = read_vis_bits(freq, vis_end - ms(9 * 30))
        print(f"  VIS end at {vis_end/SAMPLE_RATE:.2f} s  "
              f"| decoded VIS = {detected_vis} "
              f"({'ok' if detected_vis == VIS_CODE else f'expected {VIS_CODE}'})")

    # ── line-by-line decode ───────────────────────────────────────────────────
    image       = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
    line_stride = ms(LINE_MS)

    for row in range(HEIGHT):
        nominal    = vis_end + row * line_stride
        sync_start = find_sync_near(freq, nominal, tol_ms=35)

        data_start = sync_start + ms(SYNC_MS + PORCH_MS)
        r_start    = data_start
        g_start    = r_start + ms(CHANNEL_MS + SEP_MS)
        b_start    = g_start + ms(CHANNEL_MS + SEP_MS)

        image[row, :, 0] = decode_pixels(freq, r_start)
        image[row, :, 1] = decode_pixels(freq, g_start)
        image[row, :, 2] = decode_pixels(freq, b_start)

        if (row + 1) % 100 == 0 or row + 1 == HEIGHT:
            print(f"\r  {row+1}/{HEIGHT} lines decoded", end="", flush=True)

    print()
    img = Image.fromarray(image, "RGB")
    img.save(out_path)
    print(f"Saved → {out_path}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <input.wav> <output.png>")
        sys.exit(1)
    decode(sys.argv[1], sys.argv[2])
