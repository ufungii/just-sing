"""Lyric check upload: unavailable states, ok/error/busy, upload limits and temp cleanup.
Runs without a database or the speech model: the guest dependency and the checker are faked."""
import shutil
import subprocess

import pytest
from fastapi.testclient import TestClient

from api import lyric_check, practice
from api.main import app
from api.play import current_guest

CLIP = "synthetic-demo"

# Uploads are normalized with FFmpeg, and the test audio is generated with it.
pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg on PATH")


class FakeChecker:
    version = "test"

    def __init__(self, fail=False):
        self.fail, self.calls = fail, []

    def check(self, wav, fingerprints, offset_s):
        assert wav.suffix == ".wav" and wav.is_file()
        self.calls.append(offset_s)
        if self.fail:
            raise RuntimeError("model blew up")
        return [{"line_index": 0, "status": "match"}, {"line_index": 1, "status": "unclear"}]


def tone(path, seconds=1):
    subprocess.run(["ffmpeg", "-nostdin", "-y", "-f", "lavfi", "-i", f"sine=duration={seconds}", str(path)],
                   check=True, capture_output=True)
    return path.read_bytes()


@pytest.fixture
def client(tmp_path, monkeypatch):
    app.dependency_overrides[current_guest] = lambda: object()
    monkeypatch.setattr("tempfile.tempdir", str(tmp_path / "tmp"))
    (tmp_path / "tmp").mkdir()
    fp = tmp_path / "fp.npz"
    fp.write_bytes(b"x")
    monkeypatch.setattr(lyric_check, "fingerprint_path", lambda clip_id: fp)
    yield TestClient(app)
    app.dependency_overrides.clear()


def post(c, audio, clip=CLIP, offset="-1.5"):
    return c.post("/api/lyric-check", data={"clip_id": clip, "offset_s": offset}, files={"audio": ("take.wav", audio)})


def test_ok_passes_offset_and_cleans_up(client, tmp_path, monkeypatch):
    fake = FakeChecker()
    monkeypatch.setattr(lyric_check, "checker", fake)
    r = post(client, tone(tmp_path / "a.wav"))
    assert r.status_code == 200
    assert r.json() == {"clip_id": CLIP, "status": "ok", "lyric_match_version": "test",
                        "lines": [{"line_index": 0, "status": "match"}, {"line_index": 1, "status": "unclear"}]}
    assert fake.calls == [-1.5]
    assert list((tmp_path / "tmp").iterdir()) == []  # the upload is gone


def test_unavailable_without_checker_or_fingerprints(client, tmp_path, monkeypatch):
    audio = tone(tmp_path / "a.wav")
    monkeypatch.setattr(lyric_check, "checker", None)
    assert post(client, audio).json() == {"clip_id": CLIP, "status": "unavailable", "lyric_match_version": None, "lines": []}
    monkeypatch.setattr(lyric_check, "checker", FakeChecker())
    monkeypatch.setattr(lyric_check, "fingerprint_path", lambda clip_id: None)
    assert post(client, audio).json()["status"] == "unavailable"


def test_checker_failure_is_error_not_a_result(client, tmp_path, monkeypatch):
    monkeypatch.setattr(lyric_check, "checker", FakeChecker(fail=True))
    r = post(client, tone(tmp_path / "a.wav"))
    assert r.status_code == 200 and r.json()["status"] == "error" and r.json()["lines"] == []
    assert practice._busy.acquire(blocking=False)  # the lock was released
    practice._busy.release()


def test_busy_while_the_model_is_in_use(client, tmp_path, monkeypatch):
    monkeypatch.setattr(lyric_check, "checker", FakeChecker())
    practice._busy.acquire()
    try:
        r = post(client, tone(tmp_path / "a.wav"))
    finally:
        practice._busy.release()
    assert r.status_code == 429 and r.json()["error"]["code"] == "pronunciation_busy" and r.json()["error"]["retryable"]


def test_bad_requests(client, tmp_path, monkeypatch):
    monkeypatch.setattr(lyric_check, "checker", FakeChecker())
    audio = tone(tmp_path / "a.wav")
    assert post(client, audio, clip="nope").status_code == 404
    assert post(client, b"not audio at all").json()["error"]["code"] == "unsupported_audio"
    assert post(client, audio, offset="9999").status_code == 422
    big = b"\0" * (lyric_check.MAX_BYTES + 200 * 1024)
    assert post(client, big).json()["error"]["code"] == "audio_too_large"  # refused from Content-Length


def test_takes_longer_than_practice_are_accepted(client, tmp_path, monkeypatch):
    monkeypatch.setattr(lyric_check, "checker", FakeChecker())
    assert post(client, tone(tmp_path / "long.wav", seconds=40)).json()["status"] == "ok"  # practice caps at 15 s


# ---------- live path: one line at a time ----------

class FakeLineChecker(FakeChecker):
    def check(self, wav, fingerprints, offset_s, only=None):
        self.calls.append((offset_s, only))
        return [{"line_index": i, "status": "match"} for i in sorted(only or ())]


def post_line(c, audio, line=3, offset="-10.2"):
    return c.post("/api/lyric-check/line", data={"clip_id": CLIP, "line_index": str(line), "offset_s": offset},
                  files={"audio": ("line.wav", audio)})


def test_line_check_grades_only_that_line(client, tmp_path, monkeypatch):
    fake = FakeLineChecker()
    monkeypatch.setattr(lyric_check, "checker", fake)
    r = post_line(client, tone(tmp_path / "a.wav", seconds=3))
    assert r.status_code == 200 and r.json()["status"] == "ok"
    assert r.json()["lines"] == [{"line_index": 3, "status": "match"}]
    assert fake.calls == [(-10.2, {3})]
    assert list((tmp_path / "tmp").iterdir()) == []


def test_line_check_waits_briefly_then_answers_busy(client, tmp_path, monkeypatch):
    monkeypatch.setattr(lyric_check, "checker", FakeLineChecker())
    monkeypatch.setattr(lyric_check, "LINE_WAIT_S", 0.2)
    practice._busy.acquire()
    try:
        r = post_line(client, tone(tmp_path / "a.wav"))
    finally:
        practice._busy.release()
    assert r.status_code == 429 and r.json()["error"]["retryable"]


def test_line_check_limits_and_unavailable(client, tmp_path, monkeypatch):
    monkeypatch.setattr(lyric_check, "checker", FakeLineChecker())
    big = b"\0" * (lyric_check.LINE_MAX_BYTES + 200 * 1024)
    assert post_line(client, big).json()["error"]["code"] == "audio_too_large"
    long = tmp_path / "long.wav"  # 35 s at 8 kHz stays under the size cap, so the length check is what trips
    subprocess.run(["ffmpeg", "-nostdin", "-y", "-f", "lavfi", "-i", "sine=duration=35:sample_rate=8000", str(long)],
                   check=True, capture_output=True)
    assert post_line(client, long.read_bytes()).json()["error"]["code"] == "audio_too_long"
    assert post_line(client, tone(tmp_path / "a.wav"), line=-1).status_code == 422
    monkeypatch.setattr(lyric_check, "checker", None)
    assert post_line(client, tone(tmp_path / "a.wav")).json()["status"] == "unavailable"
