"""Line-level lyric matching for SUNG audio: did the player sing this line's words?

Speech recognisers fail on singing (ml/evals/results/sung_lyrics.md), so this does not transcribe.
It compares how each sung line SOUNDS with the original singer's recording of the same song, using
speech-model features (wav2vec2, layer 6) aligned by DTW. A line is a "match" when both hold:
  1. it beats its own hum: we resynthesise the player's exact melody and loudness as a wordless "aah"
     and the real line must sound clearly closer to the original line than that hum does. The hum has
     the same tune, timing and length, so the only thing it lacks is the words;
  2. it is the right line: closer to the original's SAME line than to most other lines of the song
     (catches singing the wrong part of the song in tune).
Neither test can be passed by sounding like the original singer (the player is a different voice).

What it is not: a pronunciation grade. It says whether the sung line carries the right lyric, at line
level. Word-level flags are not reliable yet (ml/evals/results/no_rerecord_controls_*.md). Display
only; never part of the singing score. Evidence and limits: ml/pronunciation/LYRIC_MATCH.md.

Two steps:
  * once per song, offline:  reference_fingerprints(vocals, sr, manifest) -> save_fingerprints(...)
  * after a turn, on the server:  lyric_match(take, sr, load_fingerprints(...), offset_s=...)
CLI (pipeline step):
  python -m ml.pronunciation.lyric_match fingerprint --manifest song.json --vocals vocals.mp3 --out lyric_fingerprints.npz
"""
import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np

LYRIC_MATCH_VERSION = "0.1.0"
MODEL = "kresnik/wav2vec2-large-xlsr-korean"   # Apache-2.0; the same model as the spoken-practice scorer
LAYER = 6
SR = 16_000
FRAME_S = 0.02                                   # wav2vec2 feature frame period

Featurizer = Callable[[np.ndarray], np.ndarray]  # 16 kHz mono audio -> (frames, dims) at FRAME_S


@dataclass(frozen=True)
class LyricMatchConfig:
    min_gain: float = 0.06       # the line must be this much closer to the original than its own hum
                                 # (cosine-distance units; placeholder picked on two takes, see LYRIC_MATCH.md)
    match_share: float = 0.8     # ...and closer than this share of the song's other lines
    min_active: float = 0.3      # share of a line's frames with voice; below this the line is "not_sung"
    min_line_s: float = 0.8      # shorter lines are not graded (too little audio to compare)


def normalise(text: str) -> str:
    return re.sub(r"[\s\W_]+", "", text.lower())


def _cmvn(x: np.ndarray) -> np.ndarray:
    return (x - x.mean(0)) / (x.std(0) + 1e-6)


def _dtw_cost(a: np.ndarray, b: np.ndarray) -> float:
    """Mean cosine distance along the best DTW path. DTW is deliberate here: it removes tempo
    differences so only content is compared (timing is scored separately by the singing score)."""
    import librosa

    an = a / (np.linalg.norm(a, axis=1, keepdims=True) + 1e-9)
    bn = b / (np.linalg.norm(b, axis=1, keepdims=True) + 1e-9)
    D, wp = librosa.sequence.dtw(C=1.0 - an @ bn.T)
    return float(D[-1, -1] / len(wp))


def _resample(audio: np.ndarray, sr: int) -> np.ndarray:
    y = np.asarray(audio, dtype=np.float32)
    if y.ndim > 1:
        y = y.mean(axis=0)
    if sr != SR:
        import librosa
        y = librosa.resample(y, orig_sr=sr, target_sr=SR)
    return y


def _model():
    """The spoken-practice scorer's model (same weights), so a server running both loads it once."""
    from .baselines import CTC_MODEL, _ctc

    assert CTC_MODEL == MODEL, "lyric_match and baselines must use the same model"
    return _ctc()


def wav2vec2_features(y: np.ndarray, chunk_s: float = 20.0, context_s: float = 1.0) -> np.ndarray:
    """Layer-6 features for a whole recording, in chunks with context on each side (bounded memory)."""
    import torch

    proc, model = _model()
    hop, n = int(FRAME_S * SR), len(y)
    out = []
    for start in range(0, n, int(chunk_s * SR)):
        lo, hi = max(0, start - int(context_s * SR)), min(n, start + int((chunk_s + context_s) * SR))
        inp = proc(y[lo:hi], sampling_rate=SR, return_tensors="pt").input_values.to(model.device)
        with torch.no_grad():
            h = model(inp, output_hidden_states=True).hidden_states[LAYER][0].float().cpu().numpy()
        first = (start - lo) // hop
        keep = min(int(chunk_s * SR), n - start) // hop
        out.append(h[first:first + keep])
    return np.concatenate(out) if out else np.zeros((0, 1024), np.float32)


def reference_fingerprints(vocals: np.ndarray, sr: int, manifest: dict, *, featurizer: Featurizer | None = None,
                           cfg: LyricMatchConfig | None = None) -> dict:
    """Per lyric line: the original singer's features (float16) plus line timing and normalised text."""
    cfg = cfg or LyricMatchConfig()
    feats = (featurizer or wav2vec2_features)(_resample(vocals, sr))
    lines = []
    for index, line in enumerate(manifest["lines"]):
        start, end, text = line["start"], line["end"], normalise(line.get("text", ""))
        a, b = int(round(start / FRAME_S)), int(round(end / FRAME_S))
        if end - start < cfg.min_line_s or not text or b > len(feats):
            continue
        lines.append({"index": index, "start": start, "end": end, "text": text, "features": feats[a:b].astype(np.float16)})
    return {"version": LYRIC_MATCH_VERSION, "model": MODEL, "layer": LAYER, "frame_s": FRAME_S,
            "song_id": manifest.get("id"), "song_version": manifest.get("version"), "lines": lines}


def save_fingerprints(fp: dict, path: str | Path) -> None:
    meta = {k: v for k, v in fp.items() if k != "lines"}
    meta["lines"] = [{k: v for k, v in ln.items() if k != "features"} for ln in fp["lines"]]
    arrays = {f"line_{i}": ln["features"] for i, ln in enumerate(fp["lines"])}
    np.savez_compressed(path, meta=np.array(json.dumps(meta)), **arrays)


def load_fingerprints(path: str | Path) -> dict:
    data = np.load(path, allow_pickle=False)
    meta = json.loads(str(data["meta"]))
    for i, ln in enumerate(meta["lines"]):
        ln["features"] = data[f"line_{i}"]
    return meta


def hum(hz_track: np.ndarray, rms_track: np.ndarray, n_samples: int) -> np.ndarray:
    """A wordless sung "aah" following a pitch track (20 ms frames, NaN = silent) and loudness envelope.
    It keeps the tune, rhythm and loudness of the player's line and drops the words."""
    t = np.arange(n_samples) / SR
    frames = np.minimum((t / FRAME_S).astype(int), len(hz_track) - 1)
    f0 = np.nan_to_num(hz_track[frames], nan=0.0)
    amp = np.interp(t, np.arange(len(rms_track)) * FRAME_S, rms_track) * (f0 > 0)
    phase = 2 * np.pi * np.cumsum(f0) / SR
    out = np.zeros(n_samples)
    for k in range(1, 25):  # harmonics weighted by /a/ formants (~700, 1200, 2600 Hz)
        fk = k * np.maximum(f0, 1.0)
        env = sum(g * np.exp(-0.5 * ((fk - fc) / bw) ** 2) for fc, bw, g in ((700, 130, 1.0), (1200, 150, 0.6), (2600, 250, 0.25)))
        out += np.where(fk < SR / 2, env * np.sin(k * phase), 0.0)
    out *= amp / (np.sqrt(np.mean(out ** 2)) + 1e-9)
    return out.astype(np.float32)


def player_hum(y: np.ndarray, take_hz: np.ndarray | None = None) -> np.ndarray:
    """The hum of a whole take. take_hz (20 ms frames) can be the pitch track the app already measured;
    otherwise it is tracked here with pyin (CPU, no PyTorch)."""
    import librosa

    if take_hz is None:
        from ml.scoring.pitch import pitch_contour
        take_hz = pitch_contour(y, SR, backend="pyin", hop_seconds=FRAME_S)
    rms = librosa.feature.rms(y=y, frame_length=2 * int(FRAME_S * SR), hop_length=int(FRAME_S * SR))[0]
    return hum(np.asarray(take_hz, dtype=float), rms, len(y))


def _active_frames(y: np.ndarray) -> np.ndarray:
    """Per 20 ms frame: is there voice? (window RMS more than 10 dB above the take's own noise floor)."""
    hop = int(FRAME_S * SR)
    n = len(y) // hop
    if n == 0:
        return np.zeros(0, bool)
    rms = np.sqrt(np.mean(y[: n * hop].reshape(n, hop).astype(np.float64) ** 2, axis=1))
    db = 20 * np.log10(np.maximum(rms, 1e-9))
    floor = np.percentile(db, 10)
    return (db > floor + 10) & (db > -60)


def lyric_match(take: np.ndarray, sr: int, fingerprints: dict, *, offset_s: float = 0.0,
                take_hz: np.ndarray | None = None, featurizer: Featurizer | None = None,
                cfg: LyricMatchConfig | None = None) -> dict:
    """Score a player's recording line by line against a song's fingerprints.

    offset_s: time in the recording at which the clip's t = 0 falls, after removing the device latency.
              In the app this is known from the audio clock; offline it can come from ml/evals/align_take.py.
    take_hz:  optional pitch track of the take in 20 ms frames (Hz, NaN = unvoiced), used to build the hum.
    Returns {"version", "lines": [...], "summary": {...}}; each line has
      status       "match" | "unclear" | "not_sung" | "not_covered"
      gain         how much closer the line is to the original than its own hum (None when not graded)
      share        share of the song's other lines that sound farther than the right line (None when not graded)
    """
    cfg = cfg or LyricMatchConfig()
    featurize = featurizer or wav2vec2_features
    y = _resample(take, sr)
    feats = featurize(y)
    hum_feats = featurize(player_hum(y, take_hz))
    active = _active_frames(y)
    lines = fingerprints["lines"]
    refs = [_cmvn(np.asarray(ln["features"], dtype=np.float32)) for ln in lines]
    out = []
    for i, ln in enumerate(lines):
        a, b = int(round((ln["start"] + offset_s) / FRAME_S)), int(round((ln["end"] + offset_s) / FRAME_S))
        row = {"line_index": ln["index"], "status": "not_covered", "gain": None, "share": None}
        if a < 0 or b > min(len(feats), len(hum_feats), len(active)) or b - a < 10:
            out.append(row)
            continue
        if active[a:b].mean() < cfg.min_active:
            out.append({**row, "status": "not_sung"})
            continue
        others = [j for j in range(len(lines)) if lines[j]["text"] != ln["text"]]
        player = _cmvn(feats[a:b])
        own = _dtw_cost(player, refs[i])
        gain = _dtw_cost(_cmvn(hum_feats[a:b]), refs[i]) - own
        share = float(np.mean([_dtw_cost(player, refs[j]) > own for j in others])) if others else 1.0
        ok = gain >= cfg.min_gain and share >= cfg.match_share
        out.append({**row, "status": "match" if ok else "unclear", "gain": round(gain, 3), "share": round(share, 3)})
    graded = [r for r in out if r["status"] in ("match", "unclear")]
    summary = {"graded": len(graded), "match": sum(r["status"] == "match" for r in graded),
               "not_sung": sum(r["status"] == "not_sung" for r in out),
               "not_covered": sum(r["status"] == "not_covered" for r in out)}
    return {"version": LYRIC_MATCH_VERSION, "lines": out, "summary": summary}


def main() -> None:
    ap = argparse.ArgumentParser(description="Lyric-match fingerprints (pipeline step)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fingerprint", help="make a song's fingerprints from its original vocal stem")
    f.add_argument("--manifest", required=True)
    f.add_argument("--vocals", required=True)
    f.add_argument("--out", required=True)
    args = ap.parse_args()
    import librosa

    manifest = json.load(open(args.manifest, encoding="utf-8"))
    vocals, sr = librosa.load(args.vocals, sr=SR, mono=True)
    fp = reference_fingerprints(vocals, sr, manifest)
    save_fingerprints(fp, args.out)
    size = Path(args.out).stat().st_size / 1e6
    print(f"wrote {args.out}: {len(fp['lines'])} lines, {size:.1f} MB (lyric-match {LYRIC_MATCH_VERSION}, {MODEL} layer {LAYER})")


if __name__ == "__main__":
    main()
