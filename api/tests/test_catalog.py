"""Song loading from ML A's output: ml/pipeline writes ml/data/<id>/song.json plus song.review.json."""
import copy
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api import clip_catalog
from api.main import app
from api.models import Song

FIXTURE = Path(__file__).parents[1] / "catalog" / "synthetic-demo" / "song.json"
client = TestClient(app)


def write_song(base: Path, song_id: str, edit=None, review=None) -> Path:
    """A song folder shaped like ml.pipeline.manifest's output."""
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    data["id"] = song_id
    if edit:
        edit(data)
    folder = base / song_id
    folder.mkdir(parents=True)
    (folder / "song.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    if review is not None:
        (folder / "song.review.json").write_text(json.dumps(review), encoding="utf-8")
    return folder


def clip_edge_line(data):
    """ML A leaves practice_text empty for a line cut off at the clip edge and gives it no phrase."""
    data["lines"].append({"start": 20.0, "end": 24.0, "text": "cut off", "romanized": "", "translation": "",
                          "practice_text": "", "words": []})
    data["provenance"]["source_url"] = ""


def test_clip_edge_line_without_a_phrase_does_not_reject_the_song(tmp_path):
    """Regression: any empty practice_text rejected the whole manifest, so one clip-edge line
    made a song fail to load."""
    write_song(tmp_path, "ml-song", edit=clip_edge_line, review={"reviewed": False})
    songs, folders, reviewed = clip_catalog.load_catalog([tmp_path])
    assert "ml-song" in songs and folders["ml-song"] == tmp_path / "ml-song" and reviewed["ml-song"] is False


def test_singing_phrase_does_not_require_spoken_practice_text():
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    data["lines"][0]["practice_text"] = " "
    assert Song.model_validate(data).phrases


def test_reviewed_flag_comes_from_the_review_file(tmp_path):
    write_song(tmp_path, "done", review={"reviewed": True})
    write_song(tmp_path, "draft", review={"reviewed": False})
    write_song(tmp_path, "unknown")  # no review file: not claimed as reviewed
    _, _, reviewed = clip_catalog.load_catalog([tmp_path])
    assert reviewed == {"done": True, "draft": False, "unknown": False}


def test_duplicate_ids_and_bad_manifests_name_their_folder(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    write_song(a, "same")
    write_song(b, "same")
    with pytest.raises(ValueError, match="Duplicate song id 'same'"):
        clip_catalog.load_catalog([a, b])
    bad = write_song(tmp_path, "bad")
    (bad / "song.json").write_text('{"id": "bad"}', encoding="utf-8")
    with pytest.raises(ValueError, match="bad"):
        clip_catalog.load_catalog([tmp_path / "bad" / ".."])


def test_missing_folders_are_skipped(tmp_path):
    songs, _, _ = clip_catalog.load_catalog([tmp_path / "does-not-exist"])
    assert songs == {}


def test_clips_endpoint_reports_review_state():
    clip = next(c for c in client.get("/api/clips").json() if c["id"] == "synthetic-demo")
    assert clip["synthetic"] is True and clip["reviewed"] is False


def test_audio_is_served_from_the_songs_own_folder(tmp_path, monkeypatch):
    folder = write_song(tmp_path, "ml-audio")
    (folder / "instrumental.mp3").write_bytes(b"abc")
    songs, folders, reviewed = clip_catalog.load_catalog([tmp_path])
    monkeypatch.setitem(clip_catalog.CATALOG, "ml-audio", songs["ml-audio"])
    monkeypatch.setitem(clip_catalog.SONG_DIR, "ml-audio", folders["ml-audio"])
    monkeypatch.setitem(clip_catalog.REVIEWED, "ml-audio", False)
    assert client.get("/api/clips/ml-audio/audio").content == b"abc"


def test_guide_vocals_are_served_like_the_instrumental(tmp_path, monkeypatch):
    folder = write_song(tmp_path, "ml-vocals")
    songs, folders, reviewed = clip_catalog.load_catalog([tmp_path])
    monkeypatch.setitem(clip_catalog.CATALOG, "ml-vocals", songs["ml-vocals"])
    monkeypatch.setitem(clip_catalog.SONG_DIR, "ml-vocals", folders["ml-vocals"])
    monkeypatch.setitem(clip_catalog.REVIEWED, "ml-vocals", False)
    assert client.get("/api/clips/ml-vocals/vocals").json()["error"]["code"] == "audio_missing"
    (folder / "vocals.mp3").write_bytes(b"xyz")
    assert client.get("/api/clips/ml-vocals/vocals").content == b"xyz"
