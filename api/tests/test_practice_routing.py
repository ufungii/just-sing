"""Spoken-practice routing/normalization without touching a real database."""
import io
import json
import wave
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from api import practice
from api.main import app
from api.models import Song


@pytest.fixture
def isolated(monkeypatch):
    data = json.loads((Path(__file__).parents[1] / 'catalog/synthetic-demo/song.json').read_text())
    song = Song.model_validate(data)
    stored = []
    session = SimpleNamespace(add=stored.append, commit=lambda: None)
    monkeypatch.setitem(app.dependency_overrides, practice.current_guest, lambda: SimpleNamespace(id='unused'))
    monkeypatch.setitem(app.dependency_overrides, practice.get_db, lambda: session)
    monkeypatch.setitem(practice.CATALOG, song.id, song)
    return TestClient(app), song, stored


@pytest.mark.parametrize('expected', ['', ' ', 'hello', '안녕 hello'])
def test_unsupported_text_rejected_before_audio_or_model(isolated, monkeypatch, expected):
    client, song, stored = isolated
    phrase = song.phrases[0]
    song.lines[phrase.line_index].practice_text = expected
    monkeypatch.setattr(practice, '_normalize', lambda *a: pytest.fail('must not decode unsupported line'))
    response = client.post('/api/practice', data={'clip_id': song.id, 'phrase_id': phrase.id},
                           files={'audio': ('take.wav', b'invalid')})
    assert response.status_code == 422
    assert response.json()['error']['code'] == 'practice_not_supported'
    assert stored == []


def test_normalized_audio_and_feedback_reach_the_response(isolated, monkeypatch):
    client, song, stored = isolated
    phrase = song.phrases[0]
    expected = song.lines[phrase.line_index].practice_text
    normalized_paths = []

    class Scorer:
        provider = 'test'
        last_overall = 61.0
        def assess(self, wav, text):
            normalized_paths.append(wav)
            with wave.open(str(wav)) as f:
                assert (f.getframerate(), f.getnchannels()) == (16000, 1)
            assert text == expected
            return [{'text': expected.split()[0], 'score': 61.0}]

    monkeypatch.setattr(practice, 'scorer', Scorer())
    audio = io.BytesIO()
    with wave.open(audio, 'wb') as f:
        f.setnchannels(2)
        f.setsampwidth(2)
        f.setframerate(44100)
        f.writeframes(b'\0' * 44100 * 4)
    response = client.post('/api/practice', data={'clip_id': song.id, 'phrase_id': phrase.id},
                           files={'audio': ('take.wav', audio.getvalue())})
    assert response.status_code == 200
    assert response.json()['status'] == 'ok' and response.json()['overall'] == 61.0
    assert len(stored) == 1
    assert normalized_paths and all(not p.exists() for p in normalized_paths)
