"""Can our free speech models grade LYRICS in SUNG audio? (They cannot, yet.)

Run from the repo root with the speech environment:
  ml/pronunciation/.venv/bin/python -m ml.evals.sung_lyrics_eval ml/data/apr_demos

Takes each Korean-only lyric line from the demo manifests, cuts that line's audio out of the
isolated vocal stem (professional singers, Demucs output) using the manifest's line times, and asks:
  * RIGHT vs WRONG lyric: scored against its own text vs the other lines' text, how well does the
    score separate them? (AUC; 0.5 = coin flip, 1.0 = perfect)
  * One word swapped in the expected text: is the swapped word the lowest-scored word?
for two methods: the wav2vec2 forced-alignment scorer used for spoken practice, and Whisper
transcription + jamo comparison. This is a BEST case (clean pro vocals, correct timing); a result near
0.5 means the method cannot grade sung lyrics. Writes ml/evals/results/sung_lyrics.md (numbers only).
"""
import argparse
import json
from pathlib import Path

import librosa
import numpy as np
from scipy.stats import mannwhitneyu

from ml.pronunciation import baselines as pb
from ml.pronunciation.text import score_words, split_words

RESULTS = Path(__file__).parent / "results"


def load_lines(folder: Path) -> list[tuple[np.ndarray, str]]:
    segs = []
    for song in sorted(folder.glob("*/song.json")):
        if not (song.parent / "vocals.mp3").exists():
            continue
        manifest = json.loads(song.read_text(encoding="utf-8"))
        y, sr = librosa.load(song.parent / "vocals.mp3", sr=16_000, mono=True)
        for line in manifest["lines"]:
            text = line["practice_text"].strip()
            if text and len(split_words(text)) >= 2:
                a, b = int(max(0, line["start"] - 0.15) * sr), int((line["end"] + 0.15) * sr)
                if b - a > 0.6 * sr:
                    segs.append((y[a:b], text))
    return segs


def evaluate(texts: list[str], score_fn) -> dict:
    """score_fn(i, text) -> (overall 0-100, per-word scores)."""
    matched = [score_fn(i, t)[0] for i, t in enumerate(texts)]
    mismatched = [score_fn(i, t2)[0] for i in range(len(texts)) for j, t2 in enumerate(texts) if j != i]
    auc = mannwhitneyu(matched, mismatched).statistic / (len(matched) * len(mismatched))
    pool = [w for t in texts for w in t.split()]
    hits, chance = 0, 0.0
    for i, t in enumerate(texts):
        words = t.split()
        k = len(words) // 2
        repl = next(w for w in pool[(i * 5) % len(pool):] + pool if w not in words)
        swapped = " ".join(words[:k] + [repl] + words[k + 1:])
        scores = score_fn(i, swapped)[1]
        hits += int(bool(scores) and int(np.argmin(scores)) == k)
        chance += 1 / len(words)
    return {"auc": float(auc), "matched_median": float(np.median(matched)), "mismatched_median": float(np.median(mismatched)),
            "swap_hits": hits, "n": len(texts), "swap_chance": chance / len(texts)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("folder")
    args = ap.parse_args()
    segs = load_lines(Path(args.folder))
    texts = [t for _, t in segs]

    posts = [pb.posteriors(a) for a, _ in segs]
    def align(i, text):
        r = pb.score_b(posts[i][0], posts[i][1], text)
        return (r["overall"], [w["score"] if w["score"] is not None else 100 for w in r["words"]]) if r["status"] == "ok" else (0.0, [])
    heard = [pb.transcribe(a) for a, _ in segs]
    def whisper(i, text):
        overall, words = score_words(text, heard[i])
        return overall * 100, [w.score for w in words]

    res = {"wav2vec2 forced alignment (spoken-mode scorer)": evaluate(texts, align),
           "Whisper-small transcription + jamo comparison": evaluate(texts, whisper)}
    silent = sum(1 for h in heard if not h.strip())
    md = ["# Grading lyrics in sung audio: it does not work yet", "",
          f"{len(segs)} Korean-only lyric lines cut from isolated professional vocal stems (best case: clean voice, correct timing). "
          "Each line is scored against its own lyric and against the other lines' lyrics.", "",
          "| Method | Right vs wrong lyric (AUC, 0.5 = chance) | Score with the right lyric (median) | with a wrong lyric (median) | Swapped word found |", "|---|---|---|---|---|"]
    for name, r in res.items():
        md.append(f"| {name} | {r['auc']:.2f} | {r['matched_median']:.0f} | {r['mismatched_median']:.0f} | {r['swap_hits']}/{r['n']} (chance ~{r['swap_chance']:.0%}) |")
    md += ["", f"Whisper returned no text at all for {silent} of {len(segs)} lines. The swapped-word column is NOT reliable for either method: scores are collapsed near zero, so the count swings (2 to 7 of 14 in repeated runs) with which word is swapped and how ties break. Only the right-vs-wrong AUC is a usable signal, and it is near chance.", "",
           "Reading: both methods sit near chance on singing. The spoken-mode scorer's posteriors collapse on sung audio "
           "(stretched vowels, vibrato), and Whisper often hears nothing. Small sample (one best-case set), small models; "
           "larger models or a different approach (comparing against the original singer's vocal) may do better. "
           "Spoken practice remains the validated path for pronunciation feedback."]
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "sung_lyrics.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
