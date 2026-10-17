"""Validate a human-reviewed timeline and bind it to the chosen playback audio."""

import argparse
import hashlib
import json
from pathlib import Path

from .lyrics import ReviewedTrack
from .main import ROOT
from .songs import SongStore


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--song", required=True)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "ml/data")
    args = parser.parse_args()
    store = SongStore(args.data_dir)
    metadata = store.metadata(args.song)
    data = json.loads(args.input.read_text(encoding="utf-8"))
    if data.get("reviewed") is not True or data.get("status", "ready") != "ready":
        parser.error("Input must be explicitly reviewed and must not be an ASR draft/rejected result")
    track = ReviewedTrack.model_validate({
        "id": args.song, "version": metadata["version"], "language": metadata["language"],
        "duration": metadata["duration"], "status": "ready", "reviewed": True,
        "audio_sha256": hashlib.sha256(store.audio_path(args.song).read_bytes()).hexdigest(),
        "lines": data["lines"],
    })
    destination = store.safe_path(args.song, "lyrics.reviewed.json")
    if destination.exists():
        parser.error("A reviewed track already exists; preserve it and increment the song version before replacing it")
    temporary = destination.with_suffix(".json.tmp")
    temporary.write_text(track.model_dump_json(indent=2) + "\n", encoding="utf-8")
    temporary.replace(destination)
    print(f"Published {len(track.lines)} reviewed lines for {track.id} v{track.version}")


if __name__ == "__main__":
    main()
