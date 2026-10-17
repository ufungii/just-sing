import numpy as np

from ml.evals.track_cleanup import fill_gaps, fix_octaves


def test_fill_gaps_fills_short_gaps_between_similar_pitches_only():
    t = np.array([220, 220, np.nan, np.nan, 222, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, 220.0])
    out = fill_gaps(t, max_gap_s=0.06)               # 3 frames
    assert np.isfinite(out[2:5]).all()                # 2-frame gap filled
    assert np.isnan(out[5:11]).all()                  # 6-frame gap left alone
    far = np.array([220, np.nan, 440.0])
    assert np.isnan(fill_gaps(far)[1])                # pitches too far apart: not filled


def test_fill_gaps_never_creates_sound_from_silence():
    assert np.isnan(fill_gaps(np.full(50, np.nan))).all()
    lead = np.array([np.nan, np.nan, 220.0])
    assert np.isnan(fill_gaps(lead)[:2]).all()


def test_fix_octaves_corrects_an_isolated_jump_but_not_a_real_leap_sustained():
    t = np.full(20, 220.0)
    t[10] = 440.0
    assert fix_octaves(t)[10] == 220.0
    leap = np.concatenate([np.full(10, 220.0), np.full(10, 262.0)])  # a real musical step
    assert np.allclose(fix_octaves(leap), leap)
