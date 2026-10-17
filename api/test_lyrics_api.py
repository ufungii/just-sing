import hashlib
import json
from pathlib import Path
from pathlib import Path
import sys
import subprocess
import wave

from fastapi.testclient import TestClient
import pytest

from api.main import create_app


@pytest.fixture
def song(tmp_path):
    folder = tmp_path / "test-song"
    folder.mkdir()
    with wave.open(str(folder / "instrumental.wav"), "wb") as audio:
        audio.setparams((1, 2, 8000, 0, "NONE", "not compressed"))
        audio.writeframes(b"\x00\x00" * 8000 * 6)
    metadata = {"id": "test-song", "version": 1, "title": "Test", "artist": "Test",
                "duration_seconds": 6.0, "audio": {"instrumental": "instrumental.wav", "vocals": "instrumental.wav"}}
    (folder / "preparation.json").write_text(json.dumps(metadata), encoding="utf-8")
    track = {"id": "test-song", "version": 1, "language": "ko", "duration": 6.0,
             "status": "ready", "reviewed": True,
             "audio_sha256": hashlib.sha256((folder / "instrumental.wav").read_bytes()).hexdigest(),
             "lines": [{"start": 1, "end": 3, "text": "First phrase",
                        "words": [{"text": "First", "start": 1, "end": 1.5},
                                  {"text": "phrase", "start": 2, "end": 3}]},
                       {"start": 3, "end": 4, "text": "Next phrase"}]}
    return tmp_path, folder, track


def publish(folder, track):
    (folder / "lyrics.reviewed.json").write_text(json.dumps(track), encoding="utf-8")


def test_rejected_drafts_never_become_lyrics(song):
    root, folder, track = song
    (folder / "lyrics").mkdir()
    (folder / "lyrics/lyrics.draft.json").write_text(json.dumps(track), encoding="utf-8")
    client = TestClient(create_app(root))
    result = client.get("/api/songs/test-song/lyrics")
    assert result.status_code == 200
    assert result.json()["status"] == "unavailable"
    assert result.json()["lines"] == []
    assert client.get("/api/songs/test-song/lyrics.vtt").status_code == 503
    assert client.get("/api/songs").json()["songs"][0]["lyrics_status"] == "unavailable"


@pytest.mark.parametrize("time,line,word", [
    (0, None, None), (1, 0, 0), (1.5, 0, None), (2, 0, 1),
    (3, 1, None), (4, None, None), (6, None, None), (8, None, None),
])
def test_clock_lookup_handles_boundaries_gaps_and_end(song, time, line, word):
    root, folder, track = song
    publish(folder, track)
    client = TestClient(create_app(root))
    response = client.get(f"/api/songs/test-song/lyrics/at?time_seconds={time}")
    assert response.status_code == 200
    assert (response.json()["line_index"], response.json()["word_index"]) == (line, word)


def test_pause_seek_lookups_have_no_server_timer_state(song):
    root, folder, track = song
    publish(folder, track)
    client = TestClient(create_app(root))
    for time in (3.5, 1.1, 3.5, 3.5, 0):
        response = client.get(f"/api/songs/test-song/lyrics/at?time_seconds={time}").json()
        assert response["line_index"] == (1 if time == 3.5 else 0 if time == 1.1 else None)


@pytest.mark.parametrize("bad_time", ["-1", "nan", "inf"])
def test_invalid_clock_values_rejected(song, bad_time):
    root, _, _ = song
    response = TestClient(create_app(root)).get(f"/api/songs/test-song/lyrics/at?time_seconds={bad_time}")
    assert response.status_code == 422


@pytest.mark.parametrize("problem", ["overlap", "outside_word", "nan", "wrong_version", "draft", "changed_audio"])
def test_invalid_or_stale_reviewed_track_rejected(song, problem):
    root, folder, track = song
    if problem == "overlap":
        track["lines"][1]["start"] = 2.5
    elif problem == "outside_word":
        track["lines"][0]["words"][0]["end"] = 5
    elif problem == "nan":
        track["lines"][0]["start"] = float("nan")
    elif problem == "wrong_version":
        track["version"] = 2
    elif problem == "draft":
        track["status"] = "rejected_asr_draft"
    else:
        track["audio_sha256"] = "0" * 64
    publish(folder, track)
    response = TestClient(create_app(root)).get("/api/songs/test-song/lyrics")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_lyric_track"


def test_audio_supports_seeking_and_explicit_local_opt_in(song):
    root, folder, _ = song
    assert TestClient(create_app(root, False)).get("/api/songs/test-song/audio/instrumental").status_code == 403
    client = TestClient(create_app(root, True))
    response = client.get("/api/songs/test-song/audio/instrumental", headers={"Range": "bytes=0-43"})
    assert response.status_code == 206
    assert response.content == (folder / "instrumental.wav").read_bytes()[:44]
    assert response.headers["accept-ranges"] == "bytes"
    assert client.head("/api/songs/test-song/audio/instrumental").content == b""


def test_audio_path_cannot_escape_song_directory(song):
    root, folder, _ = song
    path = folder / "preparation.json"
    metadata = json.loads(path.read_text(encoding="utf-8"))
    metadata["audio"]["instrumental"] = "../private.wav"
    path.write_text(json.dumps(metadata), encoding="utf-8")
    response = TestClient(create_app(root, True)).get("/api/songs/test-song/audio/instrumental")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_asset_path"


def test_subtitles_and_api_do_not_load_ml_stack(song):
    root, folder, track = song
    publish(folder, track)
    client = TestClient(create_app(root))
    result = client.get("/api/songs/test-song/lyrics.vtt")
    assert result.status_code == 200
    assert "00:00:01.000 --> 00:00:03.000" in result.text
    assert result.headers["content-type"].startswith("text/vtt")
    assert "torch" not in sys.modules and "demucs" not in sys.modules


def test_existing_final_manifest_lines_are_supported(song):
    root, folder, track = song
    manifest = {"id": "test-song", "version": 1, "title": "Test", "artist": "Test",
                "duration": 6, "lines": track["lines"], "reference": {"hz": []}}
    (folder / "song.json").write_text(json.dumps(manifest), encoding="utf-8")
    result = TestClient(create_app(root)).get("/api/songs/test-song/lyrics")
    assert result.status_code == 200
    assert result.json()["status"] == "ready"


def test_generated_manifest_matches_contract_and_does_not_promote_draft_lyrics(song):
    from ml.pipeline.manifest import write_manifest
    from api.lyrics import Timeline
    root, folder, track = song
    prepare_preview(folder, track)
    manifest = write_manifest(folder)
    contract = json.loads((Path(__file__).resolve().parents[1] / "contracts/song.example.json").read_text(encoding="utf-8"))
    assert set(manifest) == set(contract)
    Timeline.model_validate(manifest)
    assert len(manifest["phrases"]) == len(track["lines"])
    assert manifest["reference"]["notes"] == [{"start": 0.0, "end": 6.0, "hz": 220}]
    assert (folder / manifest["audio"]["vocals"]).is_file()
    client = TestClient(create_app(root, True))
    assert client.get("/api/songs/test-song/lyrics").json()["status"] == "unavailable"
    assert client.get("/api/songs/test-song/lyrics/preview").json()["status"] == "draft"
    download = client.get("/api/songs/test-song/manifest")
    assert download.json() == manifest and 'attachment;' in download.headers['content-disposition']
    assert TestClient(create_app(root, False)).get("/api/songs/test-song/manifest").status_code == 403
    assert write_manifest(folder) == manifest
    (folder / "song.json").write_text(json.dumps({**manifest, "title": "Manual edit"}))
    with pytest.raises(ValueError, match="manually edited"):
        write_manifest(folder)


def test_manifest_notes_respect_exclusions_and_rest_gaps():
    from ml.pipeline.manifest import display_notes
    ref = {"hop_seconds": 0.1, "hz": [220] * 3 + [None] + [440] * 4,
           "excluded": [{"start": 0.5, "end": 0.7}]}
    assert display_notes(ref, 0.8) == [
        {"start": 0.0, "end": 0.3, "hz": 220},
        {"start": 0.4, "end": 0.5, "hz": 440},
        {"start": 0.7, "end": 0.8, "hz": 440}]


def test_manifest_preserves_reviewed_lyric_corrections(song):
    from ml.pipeline.manifest import write_manifest
    _, folder, track = song
    prepare_preview(folder, track)
    track["lines"][0]["text"] = "Manually corrected phrase"
    publish(folder, track)
    manifest = write_manifest(folder)
    assert manifest["lines"][0]["text"] == "Manually corrected phrase"
    review = json.loads((folder / "song.review.json").read_text())
    assert review["lyrics_reviewed"] is True and review["reviewed"] is False


def test_short_unscoreable_lines_stay_visible_but_are_not_graded(song):
    from ml.pipeline.manifest import write_manifest
    root, folder, track = song
    prepare_preview(folder, track)
    path = folder / "reference.pitch.json"
    ref = json.loads(path.read_text())
    ref["hz"] = [None] * 60
    ref["hz"][10:14] = [220] * 4
    ref["hz"][30:40] = [220] * 10
    path.write_text(json.dumps(ref))
    manifest = write_manifest(folder)
    assert len(manifest["lines"]) == 2
    assert [p["id"] for p in manifest["phrases"]] == ["p2"]
    assert all(line["practice_text"] == "" for line in manifest["lines"])
    client = TestClient(create_app(root, True))
    assert len(client.get("/api/songs/test-song/lyrics/preview").json()["lines"]) == 2
    result = client.post("/api/songs/test-song/score-preview", json={"observations": []}).json()
    assert [p["phrase_id"] for p in result["per_line"]] == ["p2"]


def test_publish_command_binds_reviewed_text_to_audio_and_preserves_release(song):
    root, folder, track = song
    checked = folder / "checked.json"
    checked.write_text(json.dumps({"reviewed": True, "lines": track["lines"]}), encoding="utf-8")
    command = [sys.executable, "-m", "api.publish_lyrics", "--song", "test-song",
               "--input", str(checked), "--data-dir", str(root)]
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    published = (folder / "lyrics.reviewed.json").read_bytes()
    client = TestClient(create_app(root))
    assert client.get("/api/songs/test-song/lyrics").json()["status"] == "ready"
    assert subprocess.run(command, capture_output=True).returncode != 0
    assert (folder / "lyrics.reviewed.json").read_bytes() == published


def prepare_preview(folder, track):
    (folder / "alignment").mkdir()
    (folder / "alignment/lyrics.aligned.json").write_text(json.dumps({
        "status": "alignment_draft", "reviewed": False, "duration": 6,
        "source_audio_sha256": track["audio_sha256"], "lines": track["lines"],
    }), encoding="utf-8")
    (folder / "reference.pitch.json").write_text(json.dumps({
        "status": "unreviewed", "reviewed": False, "duration": 6,
        "source_audio_sha256": track["audio_sha256"], "hop_seconds": 0.1,
        "hz": [220] * 60, "excluded": [],
    }), encoding="utf-8")


def test_draft_preview_is_explicit_and_does_not_publish_reviewed_lyrics(song):
    root, folder, track = song
    prepare_preview(folder, track)
    client = TestClient(create_app(root, True))
    assert client.get("/api/songs/test-song/lyrics/preview").json()["status"] == "draft"
    assert client.get("/api/songs/test-song/lyrics").json()["status"] == "unavailable"
    assert TestClient(create_app(root, False)).get("/api/songs/test-song/lyrics/preview").status_code == 403


def test_preview_preserves_valid_section_breaks_and_rejects_invalid_ones(song):
    root, folder, track = song
    prepare_preview(folder, track)
    path = folder / "alignment/lyrics.aligned.json"
    data = json.loads(path.read_text())
    data["section_starts"] = [0]
    path.write_text(json.dumps(data))
    client = TestClient(create_app(root, True))
    assert client.get("/api/songs/test-song/lyrics/preview").json()["section_starts"] == [0]
    data["section_starts"] = [len(track["lines"])]
    path.write_text(json.dumps(data))
    assert client.get("/api/songs/test-song/lyrics/preview").status_code == 422


def test_backend_preview_score_matches_reference_and_silence_gets_zero(song):
    root, folder, track = song
    prepare_preview(folder, track)
    client = TestClient(create_app(root, True))
    result = client.post("/api/songs/test-song/score-preview", json={
        "observations": [{"time": i / 10, "hz": 220} for i in range(60)]}).json()
    assert result["total"] == pytest.approx(100)
    assert result["reviewed"] is False
    lower = client.post("/api/songs/test-song/score-preview", json={
        "register": -12, "observations": [{"time": i / 10, "hz": 110} for i in range(60)]}).json()
    assert lower["total"] == pytest.approx(100)
    assert client.post("/api/songs/test-song/score-preview", json={"observations": []}).json()["total"] == 0
    assert client.post("/api/songs/test-song/score-preview", json={"scoring_version": "stale", "observations": []}).status_code == 409


def test_preview_rejects_changed_source_and_invalid_reference(song):
    root, folder, track = song
    prepare_preview(folder, track)
    reference_path = folder / "reference.pitch.json"
    data = json.loads(reference_path.read_text())
    data["hz"][0] = float("nan")
    reference_path.write_text(json.dumps(data))
    assert TestClient(create_app(root, True)).get("/api/songs/test-song/reference").status_code == 422
    path = folder / "alignment/lyrics.aligned.json"
    data = json.loads(path.read_text())
    data["source_audio_sha256"] = "0" * 64
    path.write_text(json.dumps(data))
    assert TestClient(create_app(root, True)).get("/api/songs/test-song/lyrics/preview").status_code == 422
