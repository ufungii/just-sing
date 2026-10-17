"""Prepare stereo WAV audio, separate stems, and verify their shared timeline."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import imageio_ffmpeg
import soundfile as sf


ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default="htdemucs")
    parser.add_argument("--start", type=float, default=0)
    parser.add_argument("--duration", type=float)
    parser.add_argument("--overlap", type=float, default=0.25)
    parser.add_argument("--instrumental-method", choices=("predicted", "residual"), default="predicted")
    args = parser.parse_args()
    if args.start < 0 or (args.duration is not None and args.duration <= 0):
        parser.error("start must be nonnegative and duration must be positive")
    if not 0 <= args.overlap < 1:
        parser.error("overlap must be in [0, 1)")
    if Path(args.model).name != args.model or any(c in args.model for c in '/\\:'):
        parser.error("model must be a Demucs model name or signature")
    source = args.input.resolve(strict=True)
    destination = args.output.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    prepared = destination / "source-stereo.wav"
    # Refuse to silently reuse a WAV from a different recording on a rerun.
    crop = ["-ss", str(args.start)]
    if args.duration is not None:
        crop += ["-t", str(args.duration)]
    subprocess.run([
        imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error",
        "-n", "-i", str(source), *crop, "-vn", "-ar", "44100", "-ac", "2",
        "-c:a", "pcm_s16le", str(prepared),
    ], check=True)
    environment = os.environ.copy()
    environment["TORCH_HOME"] = str(ROOT / "ml/data/model-cache/torch")
    environment["OMP_NUM_THREADS"] = "4"
    environment["MKL_NUM_THREADS"] = "4"
    started = time.monotonic()
    subprocess.run([
        sys.executable, "-m", "demucs", "-n", args.model, "-d", "cpu",
        "--two-stems=vocals", "--shifts", "1", "--float32",
        "--overlap", str(args.overlap),
        "--filename", "{stem}.{ext}", "-o", str(destination / "stems"),
        str(prepared),
    ], env=environment, check=True)
    original = sf.info(prepared)
    files = {"vocals": destination / "stems" / args.model / "vocals.wav",
             "instrumental": destination / "stems" / args.model / "no_vocals.wav"}
    if args.instrumental_method == "residual":
        mixture, rate = sf.read(prepared, dtype="float32", always_2d=True)
        vocals, vocal_rate = sf.read(files["vocals"], dtype="float32", always_2d=True)
        if mixture.shape != vocals.shape or rate != vocal_rate:
            raise ValueError("Vocal estimate and source must share the exact timeline")
        residual = files["vocals"].with_name("instrumental-residual.wav")
        # An alternate backing estimate preserving mixture detail. This may
        # retain more vocal bleed; it is a listening comparison, not guaranteed
        # improvement. FLOAT avoids clipping before the playback mastering pass.
        sf.write(residual, mixture - vocals, rate, subtype="FLOAT")
        files["instrumental"] = residual
    for role, path in files.items():
        info = sf.info(path)
        if (info.frames, info.samplerate, info.channels) != (
            original.frames, original.samplerate, original.channels
        ):
            raise ValueError(f"{role} does not match the source frame count or format")
    result = {
        "source_file": str(source),
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "source_wav": prepared.name,
        "duration_seconds": original.duration,
        "sample_rate_hz": original.samplerate,
        "channels": original.channels,
        "model": args.model, "device": "cpu", "shifts": 1, "overlap": args.overlap,
        "clip_start_seconds": args.start,
        "requested_duration_seconds": args.duration,
        "instrumental_method": args.instrumental_method,
        "timeline": "Seconds from prepared clip start; add clip_start_seconds for source time",
        "audio": {role: path.relative_to(destination).as_posix()
                  for role, path in files.items()},
        "frame_counts_verified": True,
        "listening_review": "pending",
        "elapsed_seconds": round(time.monotonic() - started, 2),
    }
    (destination / "separation.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
