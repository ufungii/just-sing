"""Practice upload: validation, FFmpeg normalization, unavailable/error/busy states, temp cleanup."""
import os
import subprocess

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from api import practice
from api.db import get_engine
from api.main import app
from api.seed import seed

pytestmark = pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="needs DATABASE_URL")


def tone(path, seconds=1, fmt_args=()):
    subprocess.run(["ffmpeg", "-nostdin", "-y", "-f", "lavfi", "-i", f"sine=duration={seconds}", *fmt_args, str(path)],
                   check=True, capture_output=True)
    return path.read_bytes()


class FakeScorer:
    provider = "fake"

    def assess(self, wav, expected):
        assert wav.suffix == ".wav" and expected == "안녕 내 사랑"
        return [{"text": "안녕", "score": 90}]


@pytest.fixture
def env(tmp_path, monkeypatch):
    seed()
    monkeypatch.setattr("tempfile.tempdir", str(tmp_path))  # so we can prove cleanup
    c = TestClient(app)
    gid = c.post("/api/guests", json={"display_name": "speaker"}).json()["id"]
    yield c, tmp_path
    with get_engine().begin() as conn:
        conn.execute(text("delete from practice_attempt where guest_id=:g"), {"g": gid})
        conn.execute(text("delete from guest_session where id=:g"), {"g": gid})


def post(c, data, phrase="p1"):
    return c.post("/api/practice", data={"clip_id": "synthetic-demo", "phrase_id": phrase},
                  files={"audio": ("a.bin", data)})


def test_unavailable_without_scorer_and_temp_is_cleaned(env, tmp_path, monkeypatch):
    c, tmp = env
    monkeypatch.setattr(practice, "scorer", None)
    r = post(c, tone(tmp_path / "a.wav"))
    assert r.status_code == 200 and r.json()["status"] == "unavailable" and r.json()["words"] == []
    assert list(tmp.glob("tmp*")) == []  # TemporaryDirectory is gone


def test_ok_error_and_busy(env, tmp_path, monkeypatch):
    c, _ = env
    audio = tone(tmp_path / "a.wav")
    monkeypatch.setattr(practice, "scorer", FakeScorer())
    r = post(c, audio).json()
    assert r["status"] == "ok" and r["words"][0]["score"] == 90

    class Boom(FakeScorer):
        def assess(self, wav, expected):
            raise RuntimeError("secret provider detail")
    monkeypatch.setattr(practice, "scorer", Boom())
    r = post(c, audio)
    assert r.json()["status"] == "error" and "secret" not in r.text

    monkeypatch.setattr(practice, "scorer", FakeScorer())
    with practice._busy:
        r = post(c, audio)
    assert r.status_code == 429 and r.json()["error"]["retryable"] is True


def test_bad_input_is_rejected(env, tmp_path):
    c, _ = env
    assert post(c, b"not audio at all").json()["error"]["code"] == "unsupported_audio"
    assert post(c, tone(tmp_path / "long.wav", seconds=20)).json()["error"]["code"] == "audio_too_long"
    assert post(c, b"0" * (practice.MAX_BYTES + 1)).status_code == 413
    assert post(c, b"x", phrase="nope").status_code == 404


def streamed_webm(path, seconds):
    """Like Chrome's MediaRecorder: WebM written as a stream, so the header has no duration."""
    with path.open("wb") as f:
        subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-f", "lavfi", "-i", f"sine=duration={seconds}",
                        "-c:a", "libopus", "-f", "webm", "pipe:1"], stdout=f, check=True)
    return path.read_bytes()


def test_browser_style_webm_without_duration(env, tmp_path, monkeypatch):
    """Regression: the duration came from the container header, which is N/A for streamed WebM,
    so every browser recording was rejected as unreadable."""
    c, _ = env
    monkeypatch.setattr(practice, "scorer", FakeScorer())
    r = post(c, streamed_webm(tmp_path / "rec.webm", 2))
    assert r.status_code == 200 and r.json()["status"] == "ok", r.text
    assert post(c, streamed_webm(tmp_path / "long.webm", 20)).json()["error"]["code"] == "audio_too_long"


def test_oversize_upload_is_rejected_before_it_is_read_or_authenticated():
    """Regression: the size limit ran inside the handler, after Starlette had already received and
    parsed the whole multipart body (and after the login check), so a big upload cost full bandwidth."""
    from fastapi.testclient import TestClient
    r = TestClient(app).post("/api/practice", data={"clip_id": "synthetic-demo", "phrase_id": "p1"},
                             files={"audio": ("a.bin", b"0" * (practice.MAX_BYTES + 200_000))})  # no guest cookie
    assert r.status_code == 413 and r.json()["error"]["code"] == "audio_too_large"
