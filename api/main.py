"""FastAPI entry point. Run from the repo root: uvicorn api.main:app --reload"""
import json
import uuid
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .models import ClipSummary, Song

CATALOG_DIR = Path(__file__).parent / "catalog"

app = FastAPI(title="K-Pop Karaoke API")


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, retryable: bool = False):
        self.status, self.code, self.message, self.retryable = status, code, message, retryable


def error_response(request: Request, e: ApiError) -> JSONResponse:
    """Error envelope from contracts/error.example.json. Never include provider details."""
    return JSONResponse(
        status_code=e.status,
        content={"error": {"code": e.code, "message": e.message, "retryable": e.retryable,
                           "request_id": request.headers.get("x-request-id", uuid.uuid4().hex)}},
    )


@app.exception_handler(ApiError)
async def api_error_handler(request: Request, e: ApiError):
    return error_response(request, e)


def load_catalog() -> dict[str, Song]:
    """Validate every manifest at load time; a bad one raises with its path."""
    songs = {}
    for path in sorted(CATALOG_DIR.glob("*/manifest.json")):
        song = Song.model_validate(json.loads(path.read_text(encoding="utf-8")))
        songs[song.id] = song
    return songs


CATALOG = load_catalog()  # ponytail: loaded once at startup, restart to pick up new manifests


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/ready")
def ready():
    # Database and pronunciation are reported separately; neither is a liveness dependency.
    return {"catalog": len(CATALOG) > 0, "database": "not_configured", "pronunciation": "unavailable"}


@app.get("/api/clips", response_model=list[ClipSummary])
def clips():
    return [
        ClipSummary(id=s.id, version=s.version, title=s.title, artist=s.artist,
                    duration=s.duration, synthetic=s.provenance.source_version == "synthetic")
        for s in CATALOG.values()
    ]


@app.get("/api/clips/{clip_id}/manifest", response_model=Song)
def manifest(clip_id: str):
    # Lookup by ID in the validated catalog, never by filesystem path.
    if clip_id not in CATALOG:
        raise ApiError(404, "clip_not_found", f"No clip with id '{clip_id}'.")
    return CATALOG[clip_id]
