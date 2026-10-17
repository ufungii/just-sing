"""Every contracts/ example must load through its model, and the API must serve the catalog."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.models import ErrorEnvelope, Practice, Score, Song

CONTRACTS = Path(__file__).parents[2] / "contracts"


@pytest.mark.parametrize("name,model", [
    ("song", Song), ("score", Score), ("practice", Practice), ("error", ErrorEnvelope)])
def test_example_matches_model(name, model):
    model.model_validate(json.loads((CONTRACTS / f"{name}.example.json").read_text(encoding="utf-8")))


client = TestClient(app)


def test_endpoints():
    assert client.get("/api/health").json() == {"status": "ok"}
    assert client.get("/api/ready").json()["catalog"] is True
    clip = client.get("/api/clips").json()[0]
    assert clip["synthetic"] is True
    assert client.get(f"/api/clips/{clip['id']}/manifest").json()["id"] == clip["id"]


def test_unknown_clip_uses_error_envelope():
    r = client.get("/api/clips/nope/manifest")
    assert r.status_code == 404
    ErrorEnvelope.model_validate(r.json())


def test_audio_served_with_range_and_missing_is_actionable():
    from api.main import CATALOG_DIR
    r = client.get("/api/clips/synthetic-demo/audio")
    assert r.status_code == 404 and r.json()["error"]["code"] == "audio_missing"
    f = CATALOG_DIR / "synthetic-demo" / "instrumental.mp3"  # *.mp3 is gitignored
    f.write_bytes(b"0123456789")
    try:
        assert client.get("/api/clips/synthetic-demo/audio").content == b"0123456789"
        part = client.get("/api/clips/synthetic-demo/audio", headers={"Range": "bytes=2-4"})
        assert part.status_code == 206 and part.content == b"234"
    finally:
        f.unlink()


def test_ready_reports_real_state():
    import os
    body = client.get("/api/ready").json()
    assert body["database"] == ("ok" if os.getenv("DATABASE_URL") else "not_configured")
    assert body["pronunciation"] == "unavailable"  # no scorer attached yet


def test_frontend_is_served_same_origin(tmp_path, monkeypatch):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<html>app</html>")
    (tmp_path / "assets" / "app.js").write_text("console.log(1)")
    (tmp_path.parent / "secret.txt").write_text("nope")
    monkeypatch.setenv("WEB_DIST", str(tmp_path))
    assert client.get("/").text == "<html>app</html>"
    assert client.get("/assets/app.js").text == "console.log(1)"
    assert client.get("/lobby/ABCDE").text == "<html>app</html>"  # client-side route survives a reload
    assert client.get("/%2e%2e/secret.txt").text == "<html>app</html>"  # no escaping the build folder
    assert client.get("/api/health").json() == {"status": "ok"}  # API routes still win
    r = client.get("/api/nope")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"


def test_missing_frontend_build_is_an_actionable_error(tmp_path, monkeypatch):
    monkeypatch.setenv("WEB_DIST", str(tmp_path / "nothing"))
    r = client.get("/")
    assert r.status_code == 404 and r.json()["error"]["code"] == "frontend_not_built"


def test_scoring_numbers_come_from_the_shared_config():
    """The API must not hard-code scoring weights (CLAUDE.md): they live in contracts/scoring.config.json."""
    from api import play
    config = json.loads((CONTRACTS / "scoring.config.json").read_text(encoding="utf-8"))
    assert play.SCORING == config and play.SCORING_VERSION == config["scoring_version"]
    assert abs(sum(config["total_weights"].values()) - 1) < 1e-9
    source = (Path(play.__file__)).read_text(encoding="utf-8")
    assert "0.8" not in source and "PITCH_WEIGHT" not in source
