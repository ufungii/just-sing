"""Make gentle playback masters from separated stems without replacing originals."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess

import imageio_ffmpeg
import soundfile as sf


def run(arguments: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-nostats", *arguments],
        capture_output=True, text=True, check=True,
    )


def loudness_json(stderr: str) -> dict:
    return json.loads(stderr[stderr.rfind("{"):stderr.rfind("}") + 1])


def enhance(source: Path, destination: Path, target: int, cutoff: int) -> dict:
    info = sf.info(source)
    # Gentle subsonic/rumble removal; no noise gate or spectral denoising that
    # could remove breath, consonants, or instrumental transients.
    cleanup = f"highpass=f={cutoff}:p=2"
    settings = f"I={target}:TP=-2:LRA=14"
    first = loudness_json(run([
        "-i", str(source), "-af", f"{cleanup},loudnorm={settings}:print_format=json",
        "-f", "null", "-",
    ]).stderr)
    measured = ":".join([
        f"measured_I={first['input_i']}", f"measured_TP={first['input_tp']}",
        f"measured_LRA={first['input_lra']}",
        f"measured_thresh={first['input_thresh']}", f"offset={first['target_offset']}",
    ])
    # Normalize in two passes. FFmpeg may use dynamic limiting if the measured
    # peak prevents safe linear gain. Trim/pad after resampling to preserve the
    # exact original frame count in the lossless playback master.
    filters = (
        f"{cleanup},loudnorm={settings}:{measured}:linear=true:print_format=json,"
        f"aresample={info.samplerate},apad=whole_len={info.frames},atrim=end_sample={info.frames}"
    )
    wav = destination / f"{source.stem}-enhanced.wav"
    mp3 = destination / f"{source.stem}-enhanced.mp3"
    second = loudness_json(run([
        "-n", "-i", str(source), "-af", filters, "-ar", str(info.samplerate),
        "-c:a", "pcm_s24le", str(wav),
    ]).stderr)
    output = sf.info(wav)
    if (output.frames, output.samplerate, output.channels) != (
        info.frames, info.samplerate, info.channels
    ):
        raise ValueError(f"Timeline/format mismatch: {wav}")
    run(["-n", "-i", str(wav), "-c:a", "libmp3lame", "-b:a", "320k", str(mp3)])
    encoded = loudness_json(run([
        "-i", str(mp3), "-af", f"loudnorm={settings}:print_format=json", "-f", "null", "-",
    ]).stderr)
    if float(encoded["input_tp"]) > 0:
        raise ValueError(f"Encoded MP3 has insufficient peak headroom: {mp3}")
    # Decode the actual MP3, accounting for its gapless metadata, rather than
    # relying on the padded container duration reported by MP3 metadata tools.
    decoded = subprocess.run([
        imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-i", str(mp3),
        "-f", "s16le", "-acodec", "pcm_s16le", "-",
    ], capture_output=True, check=True)
    decoded_frames = len(decoded.stdout) // (2 * info.channels)
    if decoded_frames != info.frames:
        raise ValueError(f"Decoded MP3 frame count differs from source: {mp3}")
    return {
        "source": str(source), "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "wav": wav.name, "mp3": mp3.name, "duration_seconds": info.duration,
        "frames": info.frames, "sample_rate_hz": info.samplerate,
        "decoded_mp3_frames": decoded_frames,
        "highpass_hz": cutoff, "target_lufs": target, "target_true_peak_db": -2,
        "normalization_type": second["normalization_type"],
        "filtered_input_lufs": first["input_i"],
        "filtered_input_true_peak_db": first["input_tp"],
        "encoded_mp3_lufs": encoded["input_i"],
        "encoded_mp3_true_peak_db": encoded["input_tp"],
        "listening_review": "pending",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--instrumental-name", default="no_vocals.wav",
                        help="Instrumental filename inside input-dir (e.g. instrumental-residual.wav)")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    result = {"purpose": "Playback enhancement; retain raw stems for ML/reference analysis",
              "method": "Gentle high-pass filtering and two-pass loudness normalization",
              "limitations": "Does not repair vocal bleed, missing detail, or separation artifacts",
              "stems": {}}
    for name, filename, target, cutoff in (
        ("vocals", "vocals.wav", -18, 50),
        ("no_vocals", args.instrumental_name, -16, 25),
    ):
        print(f"Processing {name}...", flush=True)
        result["stems"][name] = enhance(args.input_dir / filename, args.output_dir, target, cutoff)
        print(f"Verified {name}: frame count preserved; encoded MP3 below 0 dBTP.", flush=True)
    (args.output_dir / "enhancement.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
