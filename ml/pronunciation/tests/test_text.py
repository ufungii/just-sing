import numpy as np
import pytest

pytest.importorskip("rapidfuzz")  # speech env only; skipped in the light scoring env

from ml.pronunciation.ctc import forced_align
from ml.pronunciation.text import score_words, split_words, to_jamo


def test_jamo_decomposition():
    assert to_jamo("한") == "ㅎㅏㄴ"
    assert to_jamo("사랑") == "ㅅㅏㄹㅏㅇ"
    assert to_jamo("안녕, 하세요!") == "ㅇㅏㄴㄴㅕㅇㅎㅏㅅㅔㅇㅛ"  # punctuation and spaces dropped


def test_identical_text_is_perfect():
    overall, words = score_words("사랑해요 정말 많이", "사랑해요 정말 많이")
    assert overall == 1.0 and all(w.score == 1.0 for w in words)


def test_spacing_in_transcript_is_ignored():
    overall, _ = score_words("사랑해요 정말 많이", "사랑해요정말많이")
    assert overall == 1.0


def test_near_miss_beats_wrong_word():
    # 사랑 vs 사람: only the final consonant differs
    _, near = score_words("사랑", "사람")
    _, wrong = score_words("사랑", "하늘")
    assert near[0].score > 0.7 > wrong[0].score


def test_substituted_word_gets_lowest_score():
    _, words = score_words("오늘 날씨가 정말 좋아요", "오늘 하늘이 정말 좋아요")
    assert min(words, key=lambda w: w.score).text == "날씨가"
    assert words[0].score == 1.0 and words[3].score == 1.0


def test_empty_transcript_scores_zero():
    overall, words = score_words("사랑해요", "")
    assert overall == 0.0 and words[0].score == 0.0


def test_split_words():
    assert split_words("  오늘  날씨 ,") == ["오늘", "날씨"]


# --- CTC forced alignment on hand-built posteriors (no model needed) ---
def _lp(rows):
    p = np.array(rows, dtype=float)
    return np.log(p / p.sum(axis=1, keepdims=True))


def test_forced_align_assigns_frames_in_order():
    B, A, C = 0, 1, 2
    # frames:  blank, A, A, blank, C, blank
    lp = _lp([[.9, .05, .05], [.05, .9, .05], [.05, .9, .05],
              [.9, .05, .05], [.05, .05, .9], [.9, .05, .05]])
    frames = forced_align(lp, [A, C], blank=B)
    assert frames == [[1, 2], [4]]


def test_forced_align_repeated_token_needs_a_blank_between():
    B, A = 0, 1
    lp = _lp([[.1, .9], [.9, .1], [.1, .9]])  # A, blank, A
    assert forced_align(lp, [A, A], blank=B) == [[0], [2]]
    # without room for the mandatory blank it must fail, not invent frames
    assert forced_align(_lp([[.1, .9], [.1, .9]]), [A, A], blank=B) is None


def test_forced_align_too_short_returns_none():
    assert forced_align(_lp([[.1, .9]]), [1, 1, 1], blank=0) is None


# --- syllable surgery used to synthesize near-miss speech ---
from ml.pronunciation.text import compose, decompose, mispronounce  # noqa: E402


def test_compose_decompose_round_trip():
    for ch in "가힣사랑해요정말많이":
        assert compose(*decompose(ch)) == ch


def test_mispronounce_changes_exactly_one_sound():
    assert mispronounce("사랑", "tail") == "사란"      # ㅇ -> ㄴ
    assert mispronounce("정말", "vowel") == "정멀"     # ㅏ -> ㅓ (middle syllable is 말)
    assert mispronounce("가다", "lead") == "가타"      # ㄷ -> ㅌ
    assert mispronounce("하나", "tail") is None        # 나 has no final consonant


def test_mispronounce_never_returns_the_same_word():
    for w in ["안녕하세요", "날씨가", "사랑해", "노래해요", "기억할게"]:
        for kind in ("lead", "vowel", "tail"):
            out = mispronounce(w, kind)
            assert out is None or (out != w and len(out) == len(w))
