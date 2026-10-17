"""The local karaoke mount must coexist with the canonical backend."""
from fastapi.testclient import TestClient
import pytest

from api.main import app


def test_karaoke_page_and_assets_are_served_without_shadowing_backend():
    client = TestClient(app)
    assert client.get("/api/health").json() == {"status": "ok"}
    assert client.get("/api/clips").status_code == 200
    page = client.get("/karaoke/live/")
    assert page.status_code == 200
    assert 'id="song"' in page.text
    assert client.get("/karaoke/live/urls.js").status_code == 200
    assert "local_demo_audio_enabled" in client.get("/karaoke/api/health").json()
    assert client.get("/api/nope").json()["error"]["code"] == "not_found"


def test_audio_and_draft_scoring_are_disabled_by_default():
    # CI/default deployment has no local-demo opt-in. Explicit standalone
    # enabled behavior is exercised with synthetic audio in test_lyrics_api.
    client = TestClient(app)
    health = client.get("/karaoke/api/health").json()
    if health["local_demo_audio_enabled"]:
        pytest.skip("Local audio is explicitly enabled in this process")
    response = client.get("/karaoke/api/songs/no-song/audio/instrumental")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "local_audio_disabled"
