"""Logic tests with a stand-in featurizer (no speech model needed). Each toy 'lyric line' is four
syllables; a syllable is a short noise burst (the 'consonant', different per syllable) followed by a
tone (the 'vowel' carrying the tune). The stand-in features are coarse spectra. A hum of the same tune
keeps the tones but loses the bursts, like a real hum loses the words."""
import numpy as np
import pytest

pytest.importorskip("librosa")

from ml.pronunciation.lyric_match import (FRAME_S, SR, LyricMatchConfig, load_fingerprints, lyric_match, player_hum,
                                          reference_fingerprints, save_fingerprints)

HOP = int(FRAME_S * SR)


def spectra(y: np.ndarray) -> np.ndarray:
    n = len(y) // HOP
    frames = y[: n * HOP].reshape(n, HOP)
    return np.log(np.abs(np.fft.rfft(frames * np.hanning(HOP), axis=1))[:, 1:161] + 1e-2)


def syllable(f0, band, rng):
    burst = rng.standard_normal(int(0.12 * SR))
    spec = np.fft.rfft(burst)
    freqs = np.fft.rfftfreq(len(burst), 1 / SR)
    spec[(freqs < band) | (freqs > band + 1500)] = 0           # band-limited noise: a toy consonant
    t = np.arange(int(0.38 * SR)) / SR
    return np.concatenate([0.5 * np.fft.irfft(spec, len(burst)) / (np.abs(np.fft.irfft(spec, len(burst))).max() + 1e-9),
                           0.3 * np.sin(2 * np.pi * f0 * t)])


def song(seed=0, tune_seed=None):
    """10 'lines' of 2 s (four syllables) with 0.5 s gaps. seed picks the consonants ('words');
    tune_seed picks the tones (defaults to seed), so a different seed with the same tune_seed is
    'the same tune, different words'."""
    words, tune = np.random.default_rng(seed), np.random.default_rng(seed if tune_seed is None else tune_seed)
    audio, lines, pos = [], [], 0.0
    for k in range(10):
        freqs = tune.choice(np.arange(150, 450, 13), size=4, replace=False)
        bands = words.choice(np.arange(2000, 6000, 250), size=4)
        seg = np.concatenate([syllable(f, b, words) for f, b in zip(freqs, bands)])
        audio += [seg, np.zeros(int(0.5 * SR))]
        lines.append({"start": pos, "end": pos + 2.0, "text": f"line {k}"})
        pos += 2.5
    return np.concatenate(audio).astype(np.float32), {"id": "toy", "version": 1, "lines": lines}


def test_the_same_singing_matches_every_line(tmp_path):
    y, m = song()
    fp = reference_fingerprints(y, SR, m, featurizer=spectra)
    save_fingerprints(fp, tmp_path / "fp.npz")
    fp = load_fingerprints(tmp_path / "fp.npz")          # round-trip through the saved file
    noisy = y + 0.002 * np.random.default_rng(1).standard_normal(len(y)).astype(np.float32)
    r = lyric_match(noisy, SR, fp, featurizer=spectra)
    assert r["summary"]["graded"] == 10 and r["summary"]["match"] == 10


def test_a_different_song_does_not_match():
    # Note: "same tune, different words" cannot be tested with this toy (its tones dominate the
    # spectra); on real singing that case is the open question in LYRIC_MATCH.md.
    y, m = song(0)
    other, _ = song(7)                                    # same timing, different tune and "words"
    r = lyric_match(other, SR, reference_fingerprints(y, SR, m, featurizer=spectra), featurizer=spectra)
    assert r["summary"]["match"] <= 2


def test_humming_the_right_tune_does_not_match():
    y, m = song()
    fp = reference_fingerprints(y, SR, m, featurizer=spectra)
    r = lyric_match(player_hum(y), SR, fp, featurizer=spectra)
    assert r["summary"]["match"] == 0
    assert all(x["gain"] < 0.06 for x in r["lines"] if x["gain"] is not None)


def test_silence_is_not_sung_and_never_matches():
    y, m = song()
    quiet = 0.001 * np.random.default_rng(2).standard_normal(len(y)).astype(np.float32)
    r = lyric_match(quiet, SR, reference_fingerprints(y, SR, m, featurizer=spectra), featurizer=spectra)
    assert r["summary"]["match"] == 0


def test_offset_and_coverage():
    y, m = song()
    fp = reference_fingerprints(y, SR, m, featurizer=spectra)
    late = np.concatenate([np.zeros(int(1.3 * SR), np.float32), y])        # recording started 1.3 s early
    assert lyric_match(late, SR, fp, offset_s=1.3, featurizer=spectra)["summary"]["match"] == 10
    short = y[: int(12 * SR)]                                               # recording stops after ~5 lines
    r = lyric_match(short, SR, fp, featurizer=spectra)
    assert r["summary"]["not_covered"] >= 4 and all(x["status"] in ("match", "not_covered") for x in r["lines"])


def test_config_threshold_is_respected():
    y, m = song()
    fp = reference_fingerprints(y, SR, m, featurizer=spectra)
    r = lyric_match(y, SR, fp, featurizer=spectra, cfg=LyricMatchConfig(match_share=1.01))
    assert r["summary"]["match"] == 0 and r["summary"]["graded"] == 10
