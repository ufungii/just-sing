"""Extract a cached pitch reference from the selected original vocal MP3."""

import argparse
import hashlib
import json
from pathlib import Path

from .align_lyrics import decode_audio
from ml.scoring.pitch import pitch_contour


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Reference exists; use a new output path to preserve review changes")
    audio = decode_audio(args.audio).numpy()
    contour = pitch_contour(audio, progress=lambda seconds: print(f"Reference pitch: through {seconds:.1f}s", flush=True))
    result = {"status": "unreviewed", "reviewed": False,
              "duration": len(audio) / 16000, "source_audio_sha256": hashlib.sha256(args.audio.read_bytes()).hexdigest(),
              **contour, "excluded": [], "notes": [],
              "notes_for_review": "Inspect harmonies/octave errors and mark unusable regions before judging performance."}
    args.output.write_text(json.dumps(result, allow_nan=False, indent=2) + "\n", encoding="utf-8")
    print(f"Reference saved: {sum(hz is not None for hz in contour['hz'])}/{len(contour['hz'])} voiced frames.")


if __name__ == "__main__":
    main()
