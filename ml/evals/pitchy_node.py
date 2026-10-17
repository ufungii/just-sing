"""Run the real Pitchy (Node) over audio; the ground truth for our browser-tracker emulation.

Needs Node and a Pitchy build: set PITCHY_PATH to a pitchy ESM file, or install the `pitchy`
npm package where Node can resolve it. (APR's branch vendors pitchy@4.1.0 at
web/live/vendor/pitchy.mjs; that file works unchanged.) Used by pitchy_parity.py and
`score_take --tracker pitchy`.
"""
import json
import os
import subprocess
import tempfile
from pathlib import Path

import librosa
import numpy as np

SCRIPT = Path(__file__).parent / "node" / "pitchy_track.mjs"
VENDORED = Path(__file__).resolve().parents[2] / "web" / "live" / "vendor" / "pitchy.mjs"
# A local copy kept in the gitignored data folder (e.g. extracted from the ml/pipeline branch).
LOCAL_COPY = Path(__file__).resolve().parents[1] / "data" / "vendor" / "pitchy.mjs"


def pitchy_track(audio: np.ndarray, sr: int, *, sample_rate: int = 48_000, window: int = 4096,
                 clarity: float = 0.8, gate: float = 0.008, pitchy_path: str | None = None) -> np.ndarray:
    """Hz track (NaN = unvoiced) from the real Pitchy at the scoring hop.

    `sample_rate` is what the live AudioContext runs at (the audio is resampled to it) and
    `window` is the detector length in samples there: 4096 at 48 kHz is an 85 ms window.
    """
    path = (pitchy_path or os.environ.get("PITCHY_PATH")
            or next((str(p) for p in (VENDORED, LOCAL_COPY) if p.exists()), None))
    if path is None:
        raise RuntimeError("Pitchy not found: set PITCHY_PATH to a pitchy ESM file, or `npm i pitchy` "
                           "(branch ml/pipeline vendors one at web/live/vendor/pitchy.mjs; copy it to ml/data/vendor/pitchy.mjs)")
    y = np.asarray(audio, dtype=np.float32)
    if sr != sample_rate:
        y = librosa.resample(y, orig_sr=sr, target_sr=sample_rate)
    with tempfile.TemporaryDirectory() as d:
        raw = Path(d) / "audio.f32"
        raw.write_bytes(y.astype("<f4").tobytes())
        out = subprocess.run(
            ["node", str(SCRIPT), "--in", str(raw), "--sr", str(sample_rate), "--window", str(window),
             "--clarity", str(clarity), "--gate", str(gate), "--pitchy", path],
            capture_output=True, text=True)
        if out.returncode != 0:
            raise RuntimeError(f"pitchy_track.mjs failed: {out.stderr.strip()[-800:]}")
    hz = json.loads(out.stdout)["hz"]
    return np.array([np.nan if v is None else v for v in hz], dtype=float)
