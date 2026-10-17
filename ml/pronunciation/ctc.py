"""CTC forced alignment (Viterbi) in plain numpy.

We align the *expected* text to the audio instead of decoding freely, so a wrong
word cannot be "corrected" by the model: it is forced onto frames where its
posterior is low. Written out here (not torchaudio.functional.forced_align,
which is deprecated) so it has no framework dependency and is unit-testable.
"""
import numpy as np


def forced_align(log_probs: np.ndarray, targets: list[int], blank: int) -> list[list[int]] | None:
    """Best CTC path for `targets`. log_probs is (T, C). Returns, per target token,
    the frames assigned to it, or None if the audio is too short for the text."""
    T, L = len(log_probs), len(targets)
    if L == 0:
        return []
    S = 2 * L + 1
    ext = [blank if s % 2 == 0 else targets[s // 2] for s in range(S)]

    NEG = -1e30
    dp = np.full((T, S), NEG)
    back = np.zeros((T, S), dtype=np.int8)  # how far we stepped back: 0, 1 or 2
    dp[0, 0] = log_probs[0, blank]
    if S > 1:
        dp[0, 1] = log_probs[0, ext[1]]

    for t in range(1, T):
        for s in range(S):
            best, step = dp[t - 1, s], 0
            if s >= 1 and dp[t - 1, s - 1] > best:
                best, step = dp[t - 1, s - 1], 1
            if s >= 2 and ext[s] != blank and ext[s] != ext[s - 2] and dp[t - 1, s - 2] > best:
                best, step = dp[t - 1, s - 2], 2
            if best > NEG:
                dp[t, s] = best + log_probs[t, ext[s]]
                back[t, s] = step

    end = S - 1 if S == 1 or dp[T - 1, S - 1] >= dp[T - 1, S - 2] else S - 2
    if dp[T - 1, end] <= NEG / 2:
        return None

    frames: list[list[int]] = [[] for _ in range(L)]
    s = end
    for t in range(T - 1, -1, -1):
        if s % 2 == 1:
            frames[s // 2].append(t)
        s -= int(back[t, s])
    return [sorted(f) for f in frames]
