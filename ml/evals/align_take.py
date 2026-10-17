"""Line a player's recording up with its song, from the melody alone.

Run from the repo root:
  python -m ml.evals.align_take take.wav song.json [--backend crepe]

A phone recording of someone singing along never starts exactly at the song's time 0. This slides the
take's pitch track along the reference melody (and tries the three registers: original, octave down,
octave up) to find `lead_in_s`: the time in the RECORDING at which the song's t = 0 falls (negative if
the recording started after the song did). It reports how well the melodies agree at the best offset
and how far ahead that is of the best offset at least 2 s away, so a weak or ambiguous match is
visible instead of silently trusted. Only the take's own audio is used; no singer stems needed.
"""
import argparse
import json

import librosa
import numpy as np

from ml.scoring.config import PitchConfig
from ml.scoring.pitch import HOP_SECONDS, _frame_credit, pitch_contour, to_track

SR = 16_000


def align(take_hz: np.ndarray, ref_hz: np.ndarray, hop: float = HOP_SECONDS, step_s: float = 0.1,
          min_overlap: int = 250) -> dict:
    """Search every offset (coarse step, then refined to one frame) and register; return the best match."""
    cfg = PitchConfig()
    tv, rv = np.isfinite(take_hz), np.isfinite(ref_hz)
    t_c = np.where(tv, 1200 * np.log2(np.where(tv, take_hz, 1.0)), np.nan)
    r_c = np.where(rv, 1200 * np.log2(np.where(rv, ref_hz, 1.0)), np.nan)
    nt, nr = len(take_hz), len(ref_hz)

    def agreement(lag: int, reg: int) -> tuple[float, int]:
        # take frame (song frame + lag) is compared with song frame
        lo, hi = max(0, -lag), min(nr, nt - lag)
        if hi - lo < min_overlap:
            return -1.0, 0
        r = r_c[lo:hi] + reg * 100
        t = t_c[lo + lag:hi + lag]
        both = np.isfinite(r) & np.isfinite(t)
        if both.sum() < min_overlap // 2:
            return -1.0, int(both.sum())
        credit = _frame_credit(t[both] - r[both], cfg).sum()
        # normalise by reference-voiced frames in the overlap, so silence cannot win
        return float(credit / max(1, np.isfinite(r).sum())), int(both.sum())

    step = max(1, int(round(step_s / hop)))
    lags = range(-(nr - min_overlap), nt - min_overlap, step)
    coarse = {(lag, reg): agreement(lag, reg)[0] for reg in (0, -12, 12) for lag in lags}
    (lag0, reg0), _ = max(coarse.items(), key=lambda kv: kv[1])
    fine = {(lag, reg0): agreement(lag, reg0)[0] for lag in range(lag0 - step, lag0 + step + 1)}
    (best_lag, best_reg), best = max(fine.items(), key=lambda kv: kv[1])
    far = max((v for (lag, reg), v in coarse.items() if abs(lag - best_lag) * hop >= 2.0), default=0.0)
    return {"lead_in_s": round(best_lag * hop, 2), "register": best_reg, "agreement": round(best, 3),
            "runner_up_agreement": round(far, 3), "margin": round(best - far, 3),
            "overlap_frames": agreement(best_lag, best_reg)[1]}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("take")
    ap.add_argument("manifest")
    ap.add_argument("--backend", default="pyin", choices=["pyin", "crepe"])
    args = ap.parse_args()
    m = json.load(open(args.manifest, encoding="utf-8"))
    y, _ = librosa.load(args.take, sr=SR, mono=True)
    res = align(pitch_contour(y, SR, backend=args.backend), to_track(m["reference"]["hz"]), m["reference"]["hop_seconds"])
    print(json.dumps(res))
    verdict = ("confident" if res["agreement"] >= 0.3 and res["margin"] >= 0.1 else
               "weak: check by ear" if res["margin"] >= 0.05 else "ambiguous: do not trust this offset")
    print(f"song t=0 is at {res['lead_in_s']} s in the recording, register {res['register']:+d}; "
          f"melody agreement {res['agreement']:.2f} vs {res['runner_up_agreement']:.2f} elsewhere -> {verdict}")


if __name__ == "__main__":
    main()
