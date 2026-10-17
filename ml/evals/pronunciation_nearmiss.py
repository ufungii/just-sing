"""Near-miss pronunciation eval: does each scorer catch a ONE-SOUND mistake?

Run from the repo root with the pronunciation env:
  ml/pronunciation/.venv/bin/python -m ml.evals.pronunciation_nearmiss

The first pronunciation eval compared right text with completely different
text, which is too easy. A learner's real mistake is small: 사랑 said as 사란.
For each test phrase and word we change one sound (initial consonant, vowel, or
final consonant), synthesize that "mispronounced" speech with local TTS, and
score it against the CORRECT text.

Reported per method:
  * word AUC: is the changed word's score lower in the mispronounced audio than
    in the correct audio? (1.0 = always, 0.5 = cannot tell)
  * localization: in the mispronounced audio, is the changed word the
    lowest-scored word? (top-1 hit rate vs chance)
  * mean drop in that word's score
  * Whisper autocorrection (A only): did the transcript contain the CORRECT word
    even though the audio said the changed one?

Limits: TTS speech of the changed text stands in for a learner. It is clean,
single-speaker, and pronounces the changed text "perfectly wrong," unlike a real
learner. No fluent reviewer. Results show sensitivity to one-sound changes; they
do not validate pronunciation quality.
"""
import json
from pathlib import Path

import numpy as np
from scipy.stats import mannwhitneyu

from ml.evals.pronunciation_eval import PHRASES
from ml.evals.tts import speak
from ml.pronunciation import baselines as pb
from ml.pronunciation.text import mispronounce, to_jamo

RESULTS = Path(__file__).parent / "results"
KINDS = ("lead", "vowel", "tail")


def build_cases() -> list[dict]:
    """One case per (phrase, word): the first mutation kind that applies, cycling
    through kinds so all three are represented."""
    cases, turn = [], 0
    for pi, phrase in enumerate(PHRASES):
        words = phrase.split()
        for wi, word in enumerate(words):
            for k in range(len(KINDS)):
                kind = KINDS[(turn + k) % len(KINDS)]
                bad = mispronounce(word, kind)
                if bad:
                    turn += 1
                    said = " ".join(words[:wi] + [bad] + words[wi + 1:])
                    cases.append({"phrase": pi, "word": wi, "kind": kind, "correct_word": word,
                                  "said_word": bad, "said_text": said})
                    break
    return cases


def run_method(name: str, y: np.ndarray, expected: str, cache: dict) -> dict:
    """Score one audio against one text, reusing the model pass for that audio."""
    key = id(y)
    if key not in cache:
        cache[key] = {"heard": pb.transcribe(y), "post": pb.posteriors(y)}
    c = cache[key]
    if name == "A":
        return pb.score_a(c["heard"], expected)
    return pb.score_b(c["post"][0], c["post"][1], expected)


def word_score(res: dict, wi: int) -> float:
    if res["status"] != "ok":
        return 0.0
    s = res["words"][wi]["score"]
    return 100.0 if s is None else float(s)


def auc(pos, neg) -> float:
    return float(mannwhitneyu(pos, neg).statistic / (len(pos) * len(neg)))


def main() -> None:
    cases = build_cases()
    print(f"{len(cases)} near-miss cases over {len(PHRASES)} phrases", flush=True)
    correct_audio = {pi: speak(p)[0] for pi, p in enumerate(PHRASES)}
    for c in cases:
        c["audio"] = speak(c["said_text"])[0]

    cache: dict = {}
    # Reference renditions (different random seed) of each correct phrase, used to
    # normalize Baseline B per word. Never the same audio that is being scored.
    ref_audio = {pi: speak(p, variant=1)[0] for pi, p in enumerate(PHRASES)}
    ref_words = {pi: run_method("B", ref_audio[pi], p, cache) for pi, p in enumerate(PHRASES)}

    def bnorm(res: dict, pi: int, j: int) -> float:
        ref = max(word_score(ref_words[pi], j), 1.0)
        return min(100.0, 100.0 * word_score(res, j) / ref)

    methods = ("A", "B", "B-norm", "A+B", "A+B-norm")
    rows = {m: {"correct": [], "wrong": [], "hit": 0, "drop": []} for m in methods}
    by_kind = {m: {k: {"correct": [], "wrong": []} for k in KINDS} for m in methods}
    autocorrect = {"correct_word": 0, "said_word": 0, "other": 0}
    chance = 0.0

    for c in cases:
        expected = PHRASES[c["phrase"]]
        wi = c["word"]
        res_ok = {m: run_method(m, correct_audio[c["phrase"]], expected, cache) for m in ("A", "B")}
        res_bad = {m: run_method(m, c["audio"], expected, cache) for m in ("A", "B")}
        pi = c["phrase"]
        n_words = len(expected.split())
        for m in methods:
            if m == "B-norm":
                ok, bad = bnorm(res_ok["B"], pi, wi), bnorm(res_bad["B"], pi, wi)
                all_bad = [bnorm(res_bad["B"], pi, j) for j in range(n_words)]
            elif m == "A+B":  # simple ensemble: mean of the two word scores
                ok = (word_score(res_ok["A"], wi) + word_score(res_ok["B"], wi)) / 2
                bad = (word_score(res_bad["A"], wi) + word_score(res_bad["B"], wi)) / 2
                all_bad = [(word_score(res_bad["A"], j) + word_score(res_bad["B"], j)) / 2 for j in range(n_words)]
            elif m == "A+B-norm":
                ok = (word_score(res_ok["A"], wi) + bnorm(res_ok["B"], pi, wi)) / 2
                bad = (word_score(res_bad["A"], wi) + bnorm(res_bad["B"], pi, wi)) / 2
                all_bad = [(word_score(res_bad["A"], j) + bnorm(res_bad["B"], pi, j)) / 2 for j in range(n_words)]
            else:
                ok, bad = word_score(res_ok[m], wi), word_score(res_bad[m], wi)
                all_bad = [word_score(res_bad[m], j) for j in range(len(res_bad[m]["words"]))]
            rows[m]["correct"].append(ok)
            rows[m]["wrong"].append(bad)
            rows[m]["drop"].append(ok - bad)
            rows[m]["hit"] += int(bool(all_bad) and int(np.argmin(all_bad)) == wi)
            by_kind[m][c["kind"]]["correct"].append(ok)
            by_kind[m][c["kind"]]["wrong"].append(bad)
        chance += 1 / len(expected.split())

        heard = to_jamo(cache[id(c["audio"])]["heard"])
        if to_jamo(c["said_word"]) in heard:
            autocorrect["said_word"] += 1
        elif to_jamo(c["correct_word"]) in heard:
            autocorrect["correct_word"] += 1
        else:
            autocorrect["other"] += 1

    n = len(cases)
    summary = {m: {"word_auc": auc(r["correct"], r["wrong"]), "localization": r["hit"] / n,
                   "mean_drop": float(np.mean(r["drop"])),
                   "by_kind": {k: auc(v["correct"], v["wrong"]) if v["wrong"] else None
                               for k, v in by_kind[m].items()}}
               for m, r in rows.items()}
    for m, s in summary.items():
        print(f"{m:4s} word AUC={s['word_auc']:.3f}  localization={s['localization']:.2f}  "
              f"drop={s['mean_drop']:.1f}  by kind={ {k: round(v, 3) for k, v in s['by_kind'].items() if v is not None} }")
    print("chance localization:", round(chance / n, 2), "| whisper heard:", autocorrect)

    kinds_n = {k: sum(c["kind"] == k for c in cases) for k in KINDS}
    md = ["# Pronunciation: near-miss (one-sound) eval", "",
          f"{n} cases: in each, one word of a test phrase has ONE sound changed "
          f"(initial consonant {kinds_n['lead']}, vowel {kinds_n['vowel']}, final consonant {kinds_n['tail']}). "
          "That changed phrase is synthesized with local TTS and scored against the CORRECT text.",
          "**Limits:** TTS stands in for a learner (clean, single speaker, says the changed text perfectly). "
          "No fluent reviewer. This measures sensitivity to one-sound changes, not pronunciation quality.", "",
          "| Method | Word AUC (changed word, correct vs mispronounced audio) | Flags the changed word (top-1) | Mean score drop on that word |",
          "|---|---|---|---|"]
    for m, s in summary.items():
        md.append(f"| {m} | {s['word_auc']:.3f} | {s['localization']:.2f} | {s['mean_drop']:.1f} |")
    md += ["", f"Chance for top-1 flagging is about {chance / n:.2f}. A = Whisper + jamo; "
           "B = wav2vec2 forced alignment; B-norm = B divided per word by B's score on a separate TTS "
           "rendition of the correct phrase (computable offline per practice line); A+B and A+B-norm = "
           "mean of the two word scores.", "",
           "## Word AUC by kind of mistake", "", "| Method | initial consonant | vowel | final consonant |", "|---|---|---|---|"]
    for m, s in summary.items():
        bk = s["by_kind"]
        md.append(f"| {m} | " + " | ".join(f"{bk[k]:.3f}" if bk[k] is not None else "n/a" for k in KINDS) + " |")
    md += ["", "## Does Whisper autocorrect? (Baseline A)", "",
           f"On the {n} mispronounced clips, Whisper's transcript contained:", "",
           "| the word actually said (faithful) | the correct word (autocorrected) | neither |", "|---|---|---|",
           f"| {autocorrect['said_word']} | {autocorrect['correct_word']} | {autocorrect['other']} |", "",
           "Autocorrection is the failure mode where a learner's mistake goes unnoticed because the "
           "recognizer's language prior 'fixes' it."]
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "pronunciation_nearmiss.md").write_text("\n".join(md) + "\n")
    (RESULTS / "pronunciation_nearmiss.json").write_text(json.dumps(
        {"summary": summary, "autocorrect": autocorrect, "chance_localization": chance / n,
         "cases": [{k: v for k, v in c.items() if k != "audio"} for c in cases]},
        ensure_ascii=False, indent=2))
    print("wrote", RESULTS / "pronunciation_nearmiss.md")


if __name__ == "__main__":
    main()
