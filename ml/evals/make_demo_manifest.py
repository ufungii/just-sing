"""Generate a complete, valid SYNTHETIC demo manifest.

Run from the repo root:  python -m ml.evals.make_demo_manifest

The backend and frontend need a clip with a real reference contour to build and
test against before any real song is processed. This writes
contracts/fixtures/synthetic-demo.manifest.json: a 30 s clip with the synthetic
melody sung twice (6 phrases), generic original practice lines (not song lyrics),
and a contour that passes the manifest inspector with no failures or warnings.
It contains no audio; the instrumental for a real clip comes from ML A.
"""
import json
from pathlib import Path

import numpy as np

from ml.evals.synthetic import example_melody, example_phrases, melody_track, midi_to_hz
from ml.scoring.pitch import HOP_SECONDS, track_to_json

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "contracts" / "fixtures" / "synthetic-demo.manifest.json"
DURATION = 30.0
OFFSETS = (2.0, 14.0)  # start time of each repeat of the melody

# Generic practice lines written for this demo; not lyrics from any song.
LINES = [
    ("안녕 내 사랑", "annyeong nae sarang", "Hello, my love"),
    ("오늘도 너를 생각해", "oneuldo neoreul saenggakhae", "I think of you today too"),
    ("우리 함께 노래해요", "uri hamkke noraehaeyo", "Let's sing together"),
    ("별이 빛나는 밤에", "byeori binnaneun bame", "On the night when the stars shine"),
    ("내 마음을 받아줘요", "nae maeumeul badajwoyo", "Please accept my heart"),
    ("다시 한번 말해줘요", "dasi hanbeon malhaejwoyo", "Please say it once more"),
]


def build() -> dict:
    template = json.loads((ROOT / "contracts" / "song.example.json").read_text(encoding="utf-8"))
    notes_src, melody = example_melody(), melody_track(example_melody(), HOP_SECONDS)
    hz = np.full(int(round(DURATION / HOP_SECONDS)), np.nan)
    notes, phrases, lines = [], [], []

    for r, off in enumerate(OFFSETS):
        start = int(round(off / HOP_SECONDS))
        hz[start:start + len(melody)] = melody
        t = off
        for midi, dur in notes_src:
            if midi is not None:
                notes.append({"start": round(t, 3), "end": round(t + dur, 3), "hz": round(midi_to_hz(midi), 2)})
            t += dur
        for k, (_, s, e) in enumerate(example_phrases()):
            idx = r * 3 + k
            phrases.append({"id": f"p{idx + 1}", "line_index": idx, "start": round(off + s, 3), "end": round(off + e, 3)})
            text, romanized, translation = LINES[idx]
            words = text.split()
            span = (e - s) / len(words)
            lines.append({
                "start": round(off + s, 3), "end": round(off + e, 3), "text": text,
                "romanized": romanized, "translation": translation, "practice_text": text,
                "words": [{"text": w, "start": round(off + s + i * span, 3), "end": round(off + s + (i + 1) * span, 3)}
                          for i, w in enumerate(words)]})

    # Conventions the API relies on: source_version "synthetic" marks a test fixture, and
    # audio paths are relative to the clip's own catalog folder.
    return {**template, "id": "synthetic-demo", "title": "Synthetic Demo (no audio)", "artist": "Test Fixture",
            "provenance": {"source_url": None, "source_version": "synthetic", "crop_start": 0.0, "crop_end": DURATION},
            "audio": {"instrumental": "instrumental.mp3", "vocals": "vocals.mp3"},
            "duration": DURATION, "lines": lines, "phrases": phrases,
            "reference": {"hop_seconds": HOP_SECONDS, "hz": track_to_json(hz), "notes": notes, "excluded": []}}


def main() -> None:
    manifest = build()
    OUT.write_text(json.dumps(manifest, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print("wrote", OUT, f"({OUT.stat().st_size / 1024:.0f} KB,", len(manifest["phrases"]), "phrases)")


if __name__ == "__main__":
    main()
