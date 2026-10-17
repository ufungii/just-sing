"""Korean text helpers: Hangul -> jamo and word-level scoring against a transcript.

Used by Baseline A (transcribe, then compare text). Comparing at jamo level means
"사랑" vs "사람" is a near miss (one final consonant) instead of a fully wrong word.
"""
from dataclasses import dataclass

from rapidfuzz.distance import Levenshtein

_LEAD = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
_VOWEL = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
_TAIL = ["", "ㄱ", "ㄲ", "ㄳ", "ㄴ", "ㄵ", "ㄶ", "ㄷ", "ㄹ", "ㄺ", "ㄻ", "ㄼ", "ㄽ", "ㄾ",
         "ㄿ", "ㅀ", "ㅁ", "ㅂ", "ㅄ", "ㅅ", "ㅆ", "ㅇ", "ㅈ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ"]


def is_syllable(ch: str) -> bool:
    return "가" <= ch <= "힣"


def to_jamo(text: str) -> str:
    """Decompose Hangul syllables into jamo. Spaces and punctuation are dropped;
    other letters/digits are kept so unexpected output is still compared."""
    out = []
    for ch in text:
        if is_syllable(ch):
            idx = ord(ch) - 0xAC00
            out += [_LEAD[idx // 588], _VOWEL[(idx % 588) // 28], _TAIL[idx % 28]]
        elif ch.isalnum():
            out.append(ch)
    return "".join(out)


def split_words(text: str) -> list[str]:
    return [w for w in text.split() if to_jamo(w)]


@dataclass(frozen=True)
class WordScore:
    text: str
    score: float  # 0-1: share of the word's jamo found in the transcript


def score_words(expected: str, heard: str) -> tuple[float, list[WordScore]]:
    """Align the heard jamo to the expected jamo; return (overall, per-word) scores.

    Spacing in the transcript is ignored (ASR places spaces unreliably). Only
    exactly matching jamo earn credit.
    """
    words = split_words(expected)
    exp_jamo, owner = [], []
    for wi, w in enumerate(words):
        j = to_jamo(w)
        exp_jamo.append(j)
        owner += [wi] * len(j)
    exp = "".join(exp_jamo)
    got = to_jamo(heard)
    if not exp:
        return 0.0, []

    matched = [0] * len(words)
    for op in Levenshtein.opcodes(exp, got):
        if op.tag == "equal":
            for i in range(op.src_start, op.src_end):
                matched[owner[i]] += 1

    scores = [WordScore(w, matched[i] / len(exp_jamo[i])) for i, w in enumerate(words)]
    overall = Levenshtein.normalized_similarity(exp, got)
    return float(overall), scores
