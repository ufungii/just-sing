"""Controls for "lyric feedback while singing" built from an EXISTING take (no re-recording).

Run from the repo root with the speech environment:
  ml/pronunciation/.venv/bin/python -m ml.evals.no_rerecord_controls take.wav ml/data/<song>/song.json ml/data/<song>/vocals.mp3

Two artificial versions of the player's own singing, each compared with the original singer's lines
using the same features as player_vs_singer.py (wav2vec2 layer 6 + DTW):
  1. SAME TUNE, NO WORDS: each line is resynthesised as a sung "aah" that follows the player's exact
     pitch and loudness. If the features still find the right original line, they are matching the
     tune; if retrieval collapses, they are matching the words.
  2. ONE WRONG WORD: in each line one word is replaced by a word the player sang elsewhere (pitch-shifted
     to the same median note, stretched to the same length, crossfaded). We check whether the per-word
     alignment cost flags that word, compared with how often the same word is flagged in the unedited line.
Edits are cleaner than real mistakes, so these are lower bounds on difficulty, not validation.
Writes ml/evals/results/no_rerecord_controls_<label>.md (numbers only).
"""
import argparse
import json
import re
from pathlib import Path

import librosa
import numpy as np
from scipy.stats import mannwhitneyu

from ml.evals.align_take import align
from ml.evals.sung_similarity import SR, W2V, cmvn
from ml.scoring.pitch import pitch_contour, to_track

RESULTS = Path(__file__).parent / "results"
FR = 0.02  # wav2vec2 frame period


def dtw(a, b):
    an = a / (np.linalg.norm(a, axis=1, keepdims=True) + 1e-9)
    bn = b / (np.linalg.norm(b, axis=1, keepdims=True) + 1e-9)
    C = 1.0 - an @ bn.T
    D, wp = librosa.sequence.dtw(C=C)
    return float(D[-1, -1] / len(wp)), C, wp


def word_costs(C, wp, spans):
    """Mean local cost on the reference frames of each word span (ref is the 2nd axis)."""
    per_ref = np.full(C.shape[1], np.nan)
    acc = {}
    for i, j in wp:
        acc.setdefault(j, []).append(C[i, j])
    for j, v in acc.items():
        per_ref[j] = np.mean(v)
    return [float(np.nanmean(per_ref[a:b])) if b - a >= 3 and np.isfinite(per_ref[a:b]).any() else np.nan for a, b in spans]


def aah(hz_track: np.ndarray, rms_track: np.ndarray, n_samples: int) -> np.ndarray:
    """A sung "aah" following a pitch track (20 ms frames, NaN = silent) and loudness envelope."""
    t = np.arange(n_samples) / SR
    frames = np.minimum((t / FR).astype(int), len(hz_track) - 1)
    f0 = np.nan_to_num(hz_track[frames], nan=0.0)
    amp = np.interp(t, np.arange(len(rms_track)) * FR, rms_track) * (f0 > 0)
    phase = 2 * np.pi * np.cumsum(f0) / SR
    out = np.zeros(n_samples)
    for k in range(1, 25):  # harmonics weighted by /a/ formants (~700, 1200, 2600 Hz)
        fk = k * np.maximum(f0, 1.0)
        env = sum(g * np.exp(-0.5 * ((fk - fc) / bw) ** 2) for fc, bw, g in ((700, 130, 1.0), (1200, 150, 0.6), (2600, 250, 0.25)))
        out += np.where(fk < SR / 2, env * np.sin(k * phase), 0.0)
    out *= amp / (np.sqrt(np.mean(out ** 2)) + 1e-9)
    return out.astype(np.float32)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("take"); ap.add_argument("manifest"); ap.add_argument("vocals")
    ap.add_argument("--label", default="take")
    ap.add_argument("--clean", action="store_true",
                    help="only use donor words already within 0.5 semitone and 10%% length: no pitch shift or stretch")
    args = ap.parse_args()
    m = json.load(open(args.manifest, encoding="utf-8"))
    ref_audio, _ = librosa.load(args.vocals, sr=SR, mono=True)
    take, _ = librosa.load(args.take, sr=SR, mono=True)
    hop = m["reference"]["hop_seconds"]
    take_hz = pitch_contour(take, SR, backend="crepe")
    a = align(take_hz, to_track(m["reference"]["hz"]), hop)
    lead = a["lead_in_s"]
    norm = lambda t: re.sub(r"[\s\W_]+", "", t.lower())
    rms = librosa.feature.rms(y=take, frame_length=640, hop_length=320)[0]

    lines = []
    for ln in m["lines"]:
        s, e = ln["start"], ln["end"]
        ps, pe = int((s + lead) * SR), int((e + lead) * SR)
        if e - s < 0.8 or not norm(ln["text"]) or ps < 0 or pe > len(take):
            continue
        kept = [w for w in ln.get("words", []) if w["end"] - w["start"] >= 0.25]
        words = [(w["start"] - s, w["end"] - s) for w in kept]
        word_texts = [norm(w["text"]) for w in kept]
        f0 = take_hz[int(round((s + lead) / FR)):int(round((e + lead) / FR))]
        lines.append({"text": norm(ln["text"]), "s": s, "e": e, "ps": ps, "pe": pe, "words": words, "word_texts": word_texts,
                      "ref": ref_audio[int(s * SR):int(e * SR)], "player": take[ps:pe],
                      "aah": aah(f0, rms[int((s + lead) / FR):int((e + lead) / FR) + 1], pe - ps), "f0": f0})
    n = len(lines)
    w2v = W2V()
    feat = lambda y: cmvn(w2v.features(y, [6])["wav2vec2 layer 6"])
    R = [feat(ln["ref"]) for ln in lines]
    same = np.array([[lines[i]["text"] == lines[j]["text"] for j in range(n)] for i in range(n)])
    dur = np.array([ln["e"] - ln["s"] for ln in lines])
    len_ok = np.abs(dur[:, None] - dur[None, :]) <= 0.2 * dur[:, None]

    def retrieval(P):
        costs = np.array([[dtw(P[i], R[j])[0] for j in range(n)] for i in range(n)])
        out = {}
        for cname, allowed in (("all lines", np.ones((n, n), bool)), ("length-matched", len_ok)):
            pos, neg, hits = [], [], 0
            for i in range(n):
                cand = allowed[i] | same[i]
                pos += list(-costs[i][same[i]]); neg += list(-costs[i][cand & ~same[i]])
                hits += int(same[i, int(np.argmin(np.where(cand, costs[i], np.inf)))])
            out[cname] = (mannwhitneyu(pos, neg).statistic / (len(pos) * len(neg)), hits / n)
        return out, costs

    real_P = [feat(ln["player"]) for ln in lines]
    real, real_costs = retrieval(real_P)
    aah_res, _ = retrieval([feat(ln["aah"]) for ln in lines])

    # ONE WRONG WORD
    donors = [(i, w) for i, ln in enumerate(lines) for w in ln["words"]]
    donors_t = [(i, w, ln["word_texts"][q]) for i, ln in enumerate(lines) for q, w in enumerate(ln["words"])]
    paired = []   # (wrong-word flagged, same-word flagged) on the same lines, clean mode only
    hits_edit = hits_base = hits_art = tried = 0
    chance, drops = 0.0, []
    for i, ln in enumerate(lines):
        if len(ln["words"]) < 2:
            continue
        k = int(np.argmax([b - a for a, b in ln["words"]]))
        ws, we = ln["words"][k]
        tgt = ln["player"][int(ws * SR):int(we * SR)]
        tgt_f0 = ln["f0"][int(ws / FR):int(we / FR)]
        if len(tgt) < 0.25 * SR or not np.isfinite(tgt_f0).any():
            continue
        best = None
        for j, (dws, dwe) in donors:
            if lines[j]["text"] == ln["text"]:
                continue
            d_f0 = lines[j]["f0"][int(dws / FR):int(dwe / FR)]
            if not np.isfinite(d_f0).any() or abs((dwe - dws) - (we - ws)) > 0.3 * (we - ws):
                continue
            semis = 12 * np.log2(np.nanmedian(tgt_f0) / np.nanmedian(d_f0))
            if args.clean and (abs(semis) > 0.5 or abs((dwe - dws) / (we - ws) - 1) > 0.1):
                continue
            if best is None or abs(semis) < abs(best[2]):
                best = (j, (dws, dwe), semis)
        if best is None:
            continue
        j, (dws, dwe), semis = best
        donor = lines[j]["player"][int(dws * SR):int(dwe * SR)]
        if not args.clean:
            donor = librosa.effects.pitch_shift(donor, sr=SR, n_steps=float(semis))
            donor = librosa.effects.time_stretch(donor, rate=len(donor) / len(tgt))
        donor = donor[:len(tgt)]
        donor = np.pad(donor, (0, len(tgt) - len(donor)))
        fade = np.minimum(1, np.minimum(np.arange(len(tgt)), np.arange(len(tgt))[::-1]) / (0.02 * SR))
        edited = ln["player"].copy()
        edited[int(ws * SR):int(ws * SR) + len(tgt)] = tgt * (1 - fade) + donor * fade
        # Artifact-only control: the line's OWN word round-tripped through the same processing
        # (pitch shift there and back, stretch there and back, same crossfade): same splice artifacts, right words.
        own = librosa.effects.pitch_shift(librosa.effects.pitch_shift(tgt, sr=SR, n_steps=float(semis)), sr=SR, n_steps=float(-semis))
        r = len(lines[j]["player"][int(dws * SR):int(dwe * SR)]) / len(tgt)
        own = librosa.effects.time_stretch(librosa.effects.time_stretch(own, rate=1 / r), rate=r)[:len(tgt)]
        own = np.pad(own, (0, len(tgt) - len(own)))
        artifact = ln["player"].copy()
        artifact[int(ws * SR):int(ws * SR) + len(tgt)] = tgt * (1 - fade) + own * fade
        spans = [(int(a / FR), int(b / FR)) for a, b in ln["words"]]
        _, Ca, wpa = dtw(feat(artifact), R[i])
        wca = word_costs(Ca, wpa, spans)
        c_edit, C, wp = dtw(feat(edited), R[i])
        wc = word_costs(C, wp, spans)
        c0, C0, wp0 = dtw(real_P[i], R[i])
        wc0 = word_costs(C0, wp0, spans)
        if np.isnan(wc[k]) or np.isnan(wc0[k]):
            continue
        if args.clean:
            # Same splice, RIGHT word: the same word text sung elsewhere in the take (another line), raw.
            same_word = None
            for jj, (sws, swe), txt in donors_t:
                if jj == i or txt != ln["word_texts"][k]:
                    continue
                sf0 = lines[jj]["f0"][int(sws / FR):int(swe / FR)]
                if not np.isfinite(sf0).any():
                    continue
                st = 12 * np.log2(np.nanmedian(tgt_f0) / np.nanmedian(sf0))
                if abs(st) <= 0.5 and abs((swe - sws) / (we - ws) - 1) <= 0.1:
                    same_word = lines[jj]["player"][int(sws * SR):int(swe * SR)][:len(tgt)]
                    break
            if same_word is not None:
                same_word = np.pad(same_word, (0, len(tgt) - len(same_word)))
                right = ln["player"].copy()
                right[int(ws * SR):int(ws * SR) + len(tgt)] = tgt * (1 - fade) + same_word * fade
                _, Cr, wpr = dtw(feat(right), R[i])
                wcr = word_costs(Cr, wpr, spans)
                paired.append((int(np.nanargmax(wc) == k), int(not np.isnan(wcr[k]) and np.nanargmax(wcr) == k)))
        hits_edit += int(np.nanargmax(wc) == k); hits_base += int(np.nanargmax(wc0) == k)
        hits_art += int(not np.isnan(wca[k]) and np.nanargmax(wca) == k)
        drops.append(c_edit - c0); chance += 1 / sum(np.isfinite(wc)); tried += 1

    md = [f"# Controls without re-recording: {args.label}", "",
          f"{n} sung lines (register {a['register']:+d}). Features: wav2vec2 layer 6 + DTW against the original vocal stem.", "",
          "## 1. Same tune, no words", "",
          "| Player audio | All lines: AUC / top-1 | Length-matched: AUC / top-1 |", "|---|---|---|",
          f"| real singing | {real['all lines'][0]:.2f} / {real['all lines'][1]:.0%} | {real['length-matched'][0]:.2f} / {real['length-matched'][1]:.0%} |",
          f"| resynthesised \"aah\" (same pitch + loudness, no words) | {aah_res['all lines'][0]:.2f} / {aah_res['all lines'][1]:.0%} | {aah_res['length-matched'][0]:.2f} / {aah_res['length-matched'][1]:.0%} |",
          "", "If the \"aah\" version still finds the right line, tune and rhythm explain the result; a large drop means the words matter.", "",
          "## 2. One wrong word", "",
          f"{tried} lines with one word replaced by a pitch- and length-matched word from elsewhere in the same take.", "",
          f"- The replaced word has the highest alignment cost (flagged) in **{hits_edit}/{tried} = {hits_edit / max(1, tried):.0%}** of lines; "
          f"the same word is flagged in the unedited line {hits_base}/{tried} = {hits_base / max(1, tried):.0%} of the time; chance ~{chance / max(1, tried):.0%}.",
          f"- **Artifact-only control** (the line's own word put through the same pitch-shift/stretch/crossfade, right words): "
          f"flagged {hits_art}/{tried} = {hits_art / max(1, tried):.0%}. The gap between this and the wrong-word rate is the part explained by the words, not the edit.",
          f"- The line's overall cost rises by {np.mean(drops):.4f} on average (median {np.median(drops):.4f}).",
          *( [f"- **Fair control (clean mode):** on the {len(paired)} lines where the same word was also sung elsewhere at the same note and length, "
              f"splicing in a WRONG word gets it flagged {sum(p[0] for p in paired)}/{len(paired)}, splicing in the RIGHT word (same kind of cut) "
              f"{sum(p[1] for p in paired)}/{len(paired)}. Only this gap is evidence that the words, not the cut, are detected."]
             if args.clean else [] ), "",
          "**Limits:** artificial edits on one take; a spliced word can carry splice artifacts that a real mistake would not. "
          "Real wrong-word takes remain the true test."]
    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / f"no_rerecord_controls_{re.sub(r'[^a-z0-9]+', '-', args.label.lower()).strip('-')}{'_clean' if args.clean else ''}.md"
    out.write_text("\n".join(md) + "\n")
    print("\n".join(md[4:]))


if __name__ == "__main__":
    main()
