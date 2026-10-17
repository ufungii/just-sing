import numpy as np

from ml.evals.rough_reference import detune_alternate_notes, rough_phrases
from ml.evals.synthetic import example_melody, melody_track
from ml.scoring.timing import onset_times

HOP = 0.02


def test_rough_phrases_split_on_rests_and_stay_inside_the_clip():
    ref = melody_track(example_melody(), HOP)          # 3 phrases separated by 0.5 s rests
    duration = len(ref) * HOP - 0.01                    # contour runs slightly past the audio
    phrases = rough_phrases(ref, HOP, duration)
    assert len(phrases) == 3
    assert all(0 <= s < e <= duration for _, s, e in phrases)
    assert all(phrases[i][2] <= phrases[i + 1][1] for i in range(len(phrases) - 1))


def test_detune_alternate_notes_changes_only_every_other_note():
    ref = melody_track(example_melody(), HOP)
    ons = onset_times(ref, HOP)
    out = detune_alternate_notes(ref, ons, HOP, 100)
    first, second = int(round(ons[0] / HOP)), int(round(ons[1] / HOP))
    assert np.isclose(out[first] / ref[first], 2 ** (100 / 1200))
    assert np.isclose(out[second], ref[second])
