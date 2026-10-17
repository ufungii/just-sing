"""English singing is supported without sending empty prompts to the Korean scorer."""
from unittest.mock import Mock

import pytest
from api import practice
from api.errors import ApiError


def test_empty_practice_text_rejected_before_audio_or_database(monkeypatch):
    original = practice.CATALOG['synthetic-demo']
    song = original.model_copy(deep=True)
    song.lines[0].practice_text = ''
    monkeypatch.setitem(practice.CATALOG, 'english-song', song)
    normalize = Mock(side_effect=AssertionError('Must not normalize an ineligible upload'))
    monkeypatch.setattr(practice, '_normalize', normalize)
    with pytest.raises(ApiError) as error:
        practice.practice('english-song', song.phrases[0].id, audio=None, guest=None, s=None)
    assert error.value.code == 'practice_unavailable'
    normalize.assert_not_called()
