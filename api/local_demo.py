"""Serve prepared audio and lyric timelines; playback time belongs to the browser."""

import os
from pathlib import Path
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, FiniteFloat

from .lyrics import Line, active_indices, to_vtt
from .songs import SongStore, fail
from ml.scoring.live import DEFAULT_CONFIG, SCORING_VERSION, aggregate, score_phrase


ROOT = Path(__file__).resolve().parents[1]


class Observation(BaseModel):
    time: Annotated[FiniteFloat, Field(ge=0)]
    hz: Annotated[FiniteFloat, Field(gt=0, le=2000)] | None = None


class PreviewPerformance(BaseModel):
    scoring_version: str = SCORING_VERSION
    register_semitones: Literal[-12, 0, 12] = Field(0, alias="register")
    latency_seconds: Annotated[FiniteFloat, Field(ge=-0.5, le=0.5)] = 0
    observations: Annotated[list[Observation], Field(max_length=30000)]


def create_app(data_dir: Path | None = None, allow_local_demo_audio: bool | None = None) -> FastAPI:
    store = SongStore(data_dir or Path(os.environ.get("JUST_SING_DATA_DIR", ROOT / "ml/data")))
    if allow_local_demo_audio is None:
        allow_local_demo_audio = os.environ.get("JUST_SING_LOCAL_DEMO_AUDIO") == "1"
    app = FastAPI(title="Just Sing prepared songs", version="0.1.0")
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                       allow_methods=["GET", "HEAD", "POST"], allow_headers=["Range", "Content-Type"],
                       expose_headers=["Content-Range", "Accept-Ranges"])

    @app.exception_handler(HTTPException)
    async def http_error(request, error):
        detail = error.detail if isinstance(error.detail, dict) else {
            "code": "http_error", "message": str(error.detail), "retryable": False,
        }
        return JSONResponse({"error": {**detail, "request_id": f"req_{uuid4().hex}"}}, status_code=error.status_code)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, error):
        return JSONResponse({"error": {"code": "invalid_request", "message": "Invalid request parameters.",
                                      "retryable": False, "request_id": f"req_{uuid4().hex}"}}, status_code=422)

    @app.get("/api/health")
    def health():
        return {"status": "ok", "local_demo_audio_enabled": allow_local_demo_audio}

    @app.get("/api/songs")
    def catalog(request: Request):
        prefix = request.scope.get("root_path", "")
        songs = store.catalog()
        for song in songs:
            for key in ("instrumental_url", "lyrics_url"):
                song[key] = prefix + song[key]
        return {"songs": songs}

    @app.get("/api/demo-handoff")
    def demo_handoff():
        if not allow_local_demo_audio:
            fail(403, "local_preview_disabled", "Local demo handoff downloads are disabled.")
        path = ROOT / "karaoke-demo-handoff.zip"
        if not path.is_file():
            fail(404, "handoff_unavailable", "Demo handoff has not been prepared.")
        return FileResponse(path, media_type="application/zip", filename=path.name,
                            headers={"Cache-Control": "private, no-store"})

    @app.get("/api/songs/{song_id}/manifest")
    def download_manifest(song_id: str):
        if not allow_local_demo_audio:
            fail(403, "local_preview_disabled", "Local song manifest downloads are disabled.")
        path = store.safe_path(song_id, "song.json")
        if not path.is_file():
            fail(404, "manifest_unavailable", "Song manifest is not prepared.")
        return FileResponse(path, media_type="application/json", filename=f"{song_id}.song.json",
                            headers={"Cache-Control": "private, no-store"})

    @app.get("/api/scoring-config")
    def scoring_config():
        return {"version": SCORING_VERSION, "status": "uncalibrated_baseline", "config": DEFAULT_CONFIG}

    @app.get("/api/songs/{song_id}/lyrics/preview")
    def preview_lyrics(song_id: str):
        if not allow_local_demo_audio:
            fail(403, "local_preview_disabled", "Unreviewed lyric preview is local-demo only.")
        return JSONResponse(store.preview_lyrics(song_id), headers={"Cache-Control": "no-store"})

    @app.get("/api/songs/{song_id}/reference")
    def reference(song_id: str):
        if not allow_local_demo_audio:
            fail(403, "local_preview_disabled", "Unreviewed reference preview is local-demo only.")
        return JSONResponse(store.reference(song_id), headers={"Cache-Control": "no-store"})

    @app.post("/api/songs/{song_id}/score-preview")
    def score_preview(song_id: str, performance: PreviewPerformance):
        if not allow_local_demo_audio:
            fail(403, "local_preview_disabled", "Provisional scoring is local-demo only.")
        if performance.scoring_version != SCORING_VERSION:
            fail(409, "scoring_version_mismatch", "Reload the current scoring configuration before starting a turn.")
        track, ref = store.preview_lyrics(song_id), store.reference(song_id)
        if not track["lines"]:
            fail(503, "lyrics_unavailable", "Lyric intervals are not prepared.")
        observations = [frame.model_dump() for frame in performance.observations]
        if any(frame["time"] > track["duration"] + 0.5 for frame in observations):
            fail(422, "invalid_observation", "Observation is outside the song timeline.")
        scores = [{"phrase_id": phrase["id"], "line_index": phrase["line_index"],
                   **score_phrase(ref, observations, phrase["start"], phrase["end"], register=performance.register_semitones,
                                  latency_seconds=performance.latency_seconds)} for phrase in store.scoring_phrases(song_id, track["lines"])]
        return {"scoring_version": SCORING_VERSION, "status": "provisional", "reviewed": False,
                "per_line": scores, **aggregate(scores)}

    @app.get("/api/songs/{song_id}/lyrics")
    def lyrics(song_id: str, response: Response):
        response.headers["Cache-Control"] = "no-store"
        return store.lyrics(song_id)

    @app.get("/api/songs/{song_id}/lyrics/at")
    def lyrics_at(song_id: str, time_seconds: Annotated[FiniteFloat, Query(ge=0)]):
        """Debug lookup; frontend fetches the full timeline once rather than polling."""
        track = store.lyrics(song_id)
        lines = [Line.model_validate(line) for line in track["lines"]]
        line_index, word_index = active_indices(lines, time_seconds)
        return {"status": track["status"], "time_seconds": time_seconds,
                "line_index": line_index, "word_index": word_index,
                "line": track["lines"][line_index] if line_index is not None else None}

    @app.get("/api/songs/{song_id}/lyrics.vtt")
    def subtitles(song_id: str):
        track = store.lyrics(song_id)
        if track["status"] != "ready":
            fail(503, "lyrics_unavailable", "Reviewed lyric timestamps have not been prepared.")
        return Response(to_vtt([Line.model_validate(line) for line in track["lines"]]),
                        media_type="text/vtt", headers={"Cache-Control": "no-store"})

    @app.api_route("/api/songs/{song_id}/audio/{role}", methods=["GET", "HEAD"])
    def audio(song_id: str, role: Literal["instrumental", "vocals"]):
        if not allow_local_demo_audio:
            fail(403, "local_audio_disabled", "Local demo audio serving is disabled on this instance.")
        path = store.audio_path(song_id, role)
        return FileResponse(path, content_disposition_type="inline", headers={"Cache-Control": "private, no-store"})

    live_directory = ROOT / "web/live"
    if live_directory.is_dir():
        app.mount("/live", StaticFiles(directory=live_directory, html=True), name="live-preview")
    return app


app = create_app()
