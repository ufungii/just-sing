"""FastAPI entry point. Run from the repo root: uvicorn api.main:app --reload"""
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse

from .clip_catalog import CATALOG, CATALOG_DIR
from .errors import ApiError, error_response
from .models import ClipSummary, Song
from .retention import cleanup_loop

@asynccontextmanager
async def lifespan(_):
    task = asyncio.create_task(cleanup_loop())
    yield
    task.cancel()


app = FastAPI(title="K-Pop Karaoke API", lifespan=lifespan)


@app.exception_handler(ApiError)
async def api_error_handler(request: Request, e: ApiError):
    return error_response(request, e.status, e.code, e.message, e.retryable)


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, e: RequestValidationError):
    return error_response(request, 422, "invalid_request", "The request body or parameters are invalid.")




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


@app.get("/api/clips/{clip_id}/audio")
def instrumental(clip_id: str):
    """Instrumental only (vocals stay offline). Path comes from the validated manifest, never the URL.
    FileResponse handles Range requests, which browsers use for seeking."""
    song = manifest(clip_id)
    path = (CATALOG_DIR / song.id / song.audio.instrumental).resolve()
    if not path.is_relative_to((CATALOG_DIR / song.id).resolve()) or not path.is_file():
        raise ApiError(404, "audio_missing", f"Instrumental for '{clip_id}' is not installed on this server.")
    return FileResponse(path)


from .play import router  # noqa: E402  (play.py imports CATALOG from this module)

app.include_router(router)

from .practice import router as practice_router  # noqa: E402

app.include_router(practice_router)
