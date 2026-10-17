"""Check the preparation environment and optionally run real Demucs inference."""

import argparse
import importlib.metadata
import math
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import wave


ROOT = Path(__file__).resolve().parents[2]


def write_test_audio(path: Path) -> None:
    """Write ten seconds of synthetic tone; no song download is needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    sample_rate = 44100
    with wave.open(str(path), "wb") as output:
        # Demucs expects stereo. Its torchaudio mono fallback uses an expanded
        # tensor that cannot be normalized in place on older PyTorch versions.
        output.setparams((2, 2, sample_rate, 0, "NONE", "not compressed"))
        for second in range(10):
            frames = bytearray()
            for index in range(sample_rate):
                time = second + index / sample_rate
                sample = int(6000 * math.sin(2 * math.pi * 220 * time))
                frames.extend(struct.pack("<hh", sample, sample))
            output.writeframes(frames)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke-test", action="store_true")
    parser.add_argument("--component", choices=("pitch", "separation"), default="pitch")
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    args = parser.parse_args()

    print(f"Python: {sys.version.split()[0]} ({sys.executable})")
    ready = sys.version_info[:2] == (3, 11)
    if not ready:
        print("Use the project's Python 3.11 environment.")
    for name in ("ffmpeg", "ffprobe"):
        executable = shutil.which(name)
        print(f"{name}: {executable or 'MISSING from PATH'}")
    print("FFmpeg/ffprobe on PATH are optional for this synthetic WAV test.")

    # These are already declared in ml/requirements.txt. Do not install them here.
    packages = ("torch", "torchaudio", "soundfile") + (
        ("demucs",) if args.component == "separation" else ("torchcrepe",)
    )
    for name in packages:
        try:
            print(f"{name}: {importlib.metadata.version(name)}")
        except importlib.metadata.PackageNotFoundError:
            print(f"{name}: NOT INSTALLED")
            ready = False

    if not args.smoke_test:
        print("Dependency presence does not prove inference works.")
        return 0 if ready else 1
    if not ready:
        print("Smoke test blocked: resolve the environment checks first.")
        return 1

    if args.component == "pitch":
        return pitch_smoke_test(args.device)

    source = ROOT / "ml" / "data" / "smoke-test" / "dummy.wav"
    write_test_audio(source)
    command = [
        sys.executable, "-m", "demucs", "--two-stems=vocals",
        "-n", "htdemucs", "-d", args.device,
        "-o", str(source.parent / "separated"), str(source),
    ]
    print("Running real separation; the first run may download model weights.", flush=True)
    environment = os.environ.copy()
    environment["TORCH_HOME"] = str(ROOT / "ml/data/model-cache/torch")
    # Avoid oversubscribing laptop CPU cores during the smoke test.
    environment["OMP_NUM_THREADS"] = "4"
    environment["MKL_NUM_THREADS"] = "4"
    result = subprocess.run(command, check=False, env=environment)
    if result.returncode:
        return result.returncode
    for name in ("vocals.wav", "no_vocals.wav"):
        stem = source.parent / "separated" / "htdemucs" / "dummy" / name
        with wave.open(str(stem), "rb") as audio:
            duration = audio.getnframes() / audio.getframerate()
        print(f"{name}: {duration:.4f}s")
        if abs(duration - 10.0) > 1 / 44100:
            print("Unexpected stem duration.")
            return 1
    print("Separation passed. This synthetic test does not assess musical stem quality.")
    return 0


def pitch_smoke_test(device: str) -> int:
    """Verify the pretrained full model recovers a known A3 tone."""
    import json
    import numpy as np
    import torch
    import torchcrepe

    torch.set_num_threads(4)
    sample_rate = 16000
    time = torch.arange(sample_rate, dtype=torch.float32) / sample_rate
    audio = (0.25 * torch.sin(2 * math.pi * 220 * time)).unsqueeze(0)
    with torch.inference_mode():
        pitch, periodicity = torchcrepe.predict(
            audio, sample_rate, 320, 65, 1000, model="full", batch_size=128,
            device=device, return_periodicity=True,
        )
    values = pitch[periodicity >= 0.5].cpu().numpy()
    if not len(values):
        print("Pitch smoke test failed: no confident frames.")
        return 1
    median = float(np.median(values))
    error = abs(1200 * math.log2(median / 220))
    result = {"target_hz": 220, "median_hz": median,
              "absolute_error_cents": error, "confident_frames": len(values),
              "passed": error < 50, "model": "full", "device": device}
    destination = ROOT / "ml/data/smoke-test/pitch-result.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
