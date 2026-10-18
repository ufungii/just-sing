"""Spoken practice on a REAL voice: does the scorer separate the right text, and find a wrong word?

  ml/pronunciation/.venv/bin/python -m ml.evals.spoken_real_eval speech.wav "expected Korean text" \
      --wrong "a different Korean sentence" --label <name> [--end 12.2]

Three checks on one recording of someone reading Korean lyrics aloud:
  1. the recording scored against the right text, and against different text (overall 0-100);
  2. one word swapped IN THE TEXT, for every word in turn. To the scorer this is the same as the
     speaker saying a different word there: is the swapped word the lowest-scoring word?
Swapping a whole word is easier to catch than a subtle mispronunciation, and this is one speaker, so it
shows the scorer can find a wrong word; it does not validate accent. Writes results/spoken_real_<label>.md.
"""
import argparse
from pathlib import Path

import librosa
import numpy as np

from ml.pronunciation.baselines import assess

RESULTS = Path(__file__).parent / "results"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("speech"); ap.add_argument("expected")
    ap.add_argument("--wrong", required=True, help="different text of similar length (the mismatch control)")
    ap.add_argument("--label", default="speaker")
    ap.add_argument("--end", type=float, help="cut the recording here (seconds), e.g. before an English phrase")
    args = ap.parse_args()
    y, _ = librosa.load(args.speech, sr=16000, mono=True)
    if args.end:
        y = y[: int(args.end * 16000)]
    words = args.expected.split()
    right = assess(y, args.expected, 16000)
    wrong = assess(y, args.wrong, 16000)
    base = [w["score"] for w in right["words"]]
    # Donor words: from the mismatch text, the closest in length to the word they replace.
    donors = [d for d in args.wrong.split() if d not in words] or args.wrong.split()
    hits, ranks, drops = 0, [], []
    for k, w in enumerate(words):
        swapped = words.copy()
        swapped[k] = min(donors, key=lambda d: abs(len(d) - len(w)))
        sc = np.array([x["score"] if x["score"] is not None else np.nan for x in assess(y, " ".join(swapped), 16000)["words"]])
        rank = int(np.sum(sc < sc[k])) + 1
        ranks.append(rank); hits += rank == 1; drops.append(base[k] - sc[k])
    lines = [
        f"# Spoken practice on a real voice: {args.label}", "",
        f"{len(y) / 16000:.1f} s of speech, {len(words)} words, scored with the shipped scorer (wav2vec2 forced alignment).", "",
        "| Check | Result |", "|---|---|",
        f"| Overall, scored against the right text | {right['overall']:.1f} |",
        f"| Overall, scored against different text | {wrong['overall']:.1f} |",
        f"| One word swapped: the swapped word is the lowest in the phrase | {hits}/{len(words)} (chance {1 / len(words):.2f}) |",
        f"| One word swapped: median rank of the swapped word | {np.median(ranks):.0f} of {len(words)} |",
        f"| One word swapped: median score drop of that word | {np.median(drops):.0f} points |", "",
        "Word scores against the right text: " + ", ".join(f"{s:.0f}" for s in base) + ".",
        f"Correct words scoring under 20 (would be highlighted falsely): {sum(s < 20 for s in base)}/{len(base)}.", "",
        "One speaker; a swapped word is easier to catch than a subtle mispronunciation. Not validated by a fluent speaker.",
    ]
    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / f"spoken_real_{args.label}.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines)); print("wrote", out)


if __name__ == "__main__":
    main()
