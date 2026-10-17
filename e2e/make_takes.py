"""Fake-microphone WAVs for the e2e test, built from a clip's reference contour.

    ../.venv/bin/python make_takes.py [clip_id]      (default: $E2E_CLIP or synthetic-demo)

Chromium's fake capture device replays the file from its start each time a mic stream opens. Layout:
a LEAD-second prefix (a 1 s hum, so the setup mic check hears a voice), then the take from clip t=0.
The test clicks START so that clip t=0 lands at stream time LEAD (see sing.spec.ts).
Outputs to takes/<clip>/{good,wrong,silence}.wav (gitignored; synthetic tones, not music).
"""
import json, os, sys, wave
from pathlib import Path
import numpy as np

SR = 48000
LEAD = float(os.getenv("E2E_LEAD", "6.0"))
ROOT = Path(__file__).resolve().parent.parent


def find_song(clip):
    for p in (ROOT / "api/catalog" / clip / "song.json", ROOT / "ml/data" / clip / "song.json"):
        if p.exists():
            return json.loads(p.read_text())
    sys.exit(f"no song.json for {clip}")


def tone(freqs, voiced, n):
    """Harmonic tone following per-sample Hz (phase-continuous), silent where not voiced."""
    phase = 2 * np.pi * np.cumsum(freqs) / SR
    y = sum(a * np.sin(k * phase) for k, a in ((1, 1.0), (2, 0.4), (3, 0.2))) / 1.6
    gate = np.convolve(voiced.astype(float), np.ones(240) / 240, mode="same")  # 5 ms de-click
    return 0.3 * y * gate


def contour(song, wrong):
    ref = song["reference"]
    hop, hz = ref["hop_seconds"], np.array([np.nan if h is None else h for h in ref["hz"]])
    if wrong:  # alternate 0.5 s windows go +4 semitones: wrong notes, not a global shift
        win = int(0.5 / hop)
        for i in range(0, len(hz), 2 * win):
            hz[i + win : i + 2 * win] *= 2 ** (4 / 12)
    n = int(np.ceil(len(hz) * hop * SR))
    idx = np.minimum((np.arange(n) / SR / hop).astype(int), len(hz) - 1)
    f = hz[idx]
    voiced = ~np.isnan(f)
    return tone(np.where(voiced, f, 0), voiced, n)


def write(path, y):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(SR)
        w.writeframes((np.clip(y, -1, 1) * 32767).astype(np.int16).tobytes())


def main():
    clip = sys.argv[1] if len(sys.argv) > 1 else os.getenv("E2E_CLIP", "synthetic-demo")
    song = find_song(clip)
    t = np.arange(int(LEAD * SR)) / SR
    hum = np.where((t > 0.3) & (t < 1.3), 0.3 * np.sin(2 * np.pi * 220 * t), 0)  # mic-check voice
    tail = np.zeros(2 * SR)
    for name, body in (("good", contour(song, False)), ("wrong", contour(song, True)), ("silence", np.zeros(int(song["duration"] * SR)))):
        write(ROOT / "e2e/takes" / clip / f"{name}.wav", np.concatenate([hum, body, tail]))
    print(f"wrote e2e/takes/{clip}/ (lead {LEAD}s, {song['duration']}s clip)")


main()
