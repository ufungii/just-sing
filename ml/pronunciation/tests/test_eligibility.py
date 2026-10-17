import numpy as np
import pytest

from ml.pronunciation.eligibility import is_spoken_korean


@pytest.mark.parametrize('text,expected', [
    ('안녕 내 사랑', True), ('  안녕, 사랑!  ', True), ('', False), ('  ', False),
    ('hello', False), ('안녕 hello', False), ('사랑 123', False), ('사랑é', False),
    ('ㄱㄴ', False), ('你好', False),
])
def test_korean_only_eligibility(text, expected):
    assert is_spoken_korean(text) is expected


def test_unsupported_text_fails_before_loading_audio_or_model(monkeypatch):
    pytest.importorskip('rapidfuzz')
    from ml.pronunciation import baselines
    monkeypatch.setattr(baselines, 'load_audio', lambda *a: pytest.fail('must not load audio'))
    for text in ('hello', '', '안녕 hello'):
        result = baselines.assess('unused.wav', text)
        assert result['status'] == 'error' and result['overall'] is None
        assert result['debug']['reason'] == 'unsupported_practice_text'


def test_nonfinite_audio_is_input_error_before_model(monkeypatch):
    pytest.importorskip('rapidfuzz')
    from ml.pronunciation import baselines
    monkeypatch.setattr(baselines, 'posteriors', lambda *a: pytest.fail('must not load model'))
    result = baselines.assess(np.full(16000, np.nan), '안녕')
    assert result['status'] == 'error' and result['debug']['reason'] == 'invalid_audio'
